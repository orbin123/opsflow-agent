"""Observable scorer defects, genuine application execution, and isolated budgets."""

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
from unittest.mock import Mock

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.evaluation import runtime_runner
from app.evaluation.catalogue import SavedRun
from app.evaluation.contracts import Metric
from app.evaluation.reports import ReportWriter, load_report, parse_report
from app.evaluation.runtime_contracts import RuntimeCase, RuntimeObservation, RuntimePilot, RuntimeReport
from app.evaluation.runtime_scoring import match_calls, score_runtime, summarize_runtime
from app.main import app
from app.ui import evaluations
from tests.test_streamlit_ui import Response
from tests.test_workspace_navigation import workspace, open_chat


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    path = runtime_runner.run_runtime(tmp_path_factory.mktemp("runtime-reports"))
    return load_report(path)


def item(report, case_id):
    return next(result for result in report.cases if result.reference_case_id == case_id)


def rescored(result, mutate):
    actual = deepcopy(result.actual)
    mutate(actual)
    return score_runtime(result.case, actual)


def test_all_scenarios_use_real_paths_and_honest_scripted_evidence(report):
    assert report.state == "completed" and len(report.cases) == 24
    assert report.provenance["execution_mode"] == "scripted"
    assert report.provenance["reference_status"] == "ai_authored_pending_human_review"
    assert all(result.execution == "completed" for result in report.cases)
    assert sum(result.actual.model_requests for result in report.cases) <= 60
    assert report.metrics["runtime.contract_success"].value == 1
    assert report.metrics["runtime.application_availability"].numerator == 22
    assert report.metrics["runtime.application_availability"].denominator == 24
    assert report.metrics["runtime.generated_answer_semantics"].value is None
    assert all(not call["provider_invoked"] for result in report.cases for call in result.actual.request_records)
    assert all(result.actual.storage_isolated and result.actual.smtp_attempts == result.actual.worker_import_attempts == 0 for result in report.cases)
    for result in report.cases:
        for call in result.actual.request_records:
            assert not set(call).intersection({"messages", "reasoning", "api_key", "system_prompt", "provider_response"})


@pytest.mark.parametrize("case_id", ["extract-literal-multiline", "extract-keyword-literal"])
def test_changed_literal_payload_fails_without_normalizing(report, case_id):
    result = item(report, case_id)
    checks, _ = rescored(result, lambda actual: actual.turns[0].execution["trace"][0]["arguments"].update(text="Changed payload"))
    assert checks["turn_1.literal_arguments"] is False and checks["turn_1.required_calls"] is False


def test_independent_order_is_flexible_but_multiplicity_is_strict(report):
    result = item(report, "agent-independent-tools")
    checks, _ = rescored(result, lambda actual: actual.turns[0].execution["trace"].reverse())
    assert checks["turn_1.required_calls"] and checks["turn_1.no_extra_calls"] and checks["turn_1.order"] is None
    checks, evidence = rescored(result, lambda actual: actual.turns[0].execution["trace"].append(deepcopy(actual.turns[0].execution["trace"][0])))
    assert checks["turn_1.no_extra_calls"] is False and evidence["turns"][0]["extra"] == 1


def test_dependency_wrong_content_wrong_policy_or_order_cannot_pass(report):
    result = item(report, "agent-policy-to-draft")
    checks, evidence = rescored(result, lambda actual: actual.turns[0].execution["trace"][1]["arguments"].update(content="Invented policy"))
    assert checks["turn_1.dependency_values"] is False and evidence["turns"][0]["matched"] == 1
    checks, _ = rescored(result, lambda actual: actual.turns[0].execution["trace"][0]["result"].update(policy_id="PAYROLL-01"))
    assert checks["turn_1.call_outcomes"] is False
    checks, _ = rescored(result, lambda actual: actual.turns[0].execution["trace"].reverse())
    assert checks["turn_1.order"] is False and checks["turn_1.dependency_values"] is False


def test_completed_tool_without_result_does_not_establish_success(report):
    result = item(report, "agent-summary-source")
    checks, _ = rescored(result, lambda actual: actual.turns[0].execution["trace"][0].update(result=None))
    assert checks["turn_1.call_outcomes"] is False


def test_missing_or_cross_chat_history_is_detected_even_with_correct_output(report):
    result = item(report, "agent-history-source")
    def strip(actual):
        for request in actual.request_records:
            if request["turn"] == 2 and request["component"] == "agent":
                request["user_inputs"] = [result.case.turns[1].input]
    checks, _ = rescored(result, strip)
    assert checks["turn_2.context_transport"] is False
    assert checks["turn_2.literal_arguments"] is True


def test_unwanted_calls_smtp_worker_or_storage_escape_are_critical_failures(report):
    result = item(report, "agent-source-injection")
    def unwanted(actual):
        actual.turns[0].execution["trace"].append(dict(tool="schedule_reminder",arguments={},status="failed",result=None))
        actual.smtp_attempts = actual.worker_import_attempts = 1
        actual.storage_isolated = False
    checks, _ = rescored(result, unwanted)
    assert not checks["turn_1.no_forbidden_calls"] and not checks["turn_1.no_extra_calls"]
    assert not checks["no_smtp"] and not checks["no_worker"] and not checks["storage_isolated"]


@pytest.mark.parametrize("damage", ["task", "instant", "zone", "state", "duplicate", "clock", "malformed"])
def test_reminder_literals_instant_zone_state_and_single_creation(report, damage):
    result = item(report, "reminder-literal-time")
    def mutate(actual):
        record = actual.reminder_records[0]
        if damage == "task": record["task"] += " "
        elif damage == "instant": record["due_at"] = "2026-10-15T05:30:00+00:00"
        elif damage == "zone": record["timezone"] = "UTC"
        elif damage == "state": record["state"] = "accepted"
        elif damage == "duplicate": actual.reminder_records.append(deepcopy(record))
        elif damage == "clock": record["created_at"] = "2026-10-14T07:00:00+00:00"
        else: record["due_at"] = "not an instant"
    checks, _ = rescored(result, mutate)
    assert checks["reminder_frozen_clock" if damage == "clock" else "reminder_records_exact"] is False
    if damage == "duplicate": assert checks["reminder_keys_unique"] is False


def test_equivalent_due_timestamp_precision_is_same_instant(report):
    result = item(report, "reminder-literal-time")
    checks, _ = rescored(result, lambda actual: actual.reminder_records[0].update(due_at="2026-10-15T04:30:00Z"))
    assert checks["reminder_records_exact"] is True


def test_no_tool_cases_have_explicit_constraint_not_fake_precision(report):
    result = deepcopy(item(report, "agent-history-missing"))
    metrics = summarize_runtime([result])
    assert result.checks["turn_1.no_extra_calls"] is True
    assert metrics["runtime.tool_precision"].value is None
    assert metrics["runtime.required_tool_coverage"].value is None
    missing = result.model_copy(update={"execution": "not_run", "actual": None, "checks": {}, "evidence": {}})
    metrics = summarize_runtime([missing])
    assert metrics["runtime.observation_coverage"].value == metrics["runtime.contract_success"].value == 0
    assert metrics["runtime.p95_scenario_ms"].value is None


def test_http_and_sse_statuses_and_partial_success_are_distinct(report):
    sse = item(report, "agent-compound-partial-failure").actual.turns[0]
    assert sse.http_status == 200 and sse.outcome_http_status == 503 and sse.status == "partial_failure"
    assert sse.execution["trace"][0]["status"] == "completed"
    assert sse.execution["trace"][1]["status"] == "failed"
    http = item(report, "reminder-partial-failure").actual.turns[0]
    assert http.http_status == 503 and http.status == "partial_failure"
    assert http.execution["trace"][0]["result"]["task"] == "review the Orion checklist"
    assert "Reminder scheduled" in http.execution["reply"]
    assert "The email was delivered" not in item(report, "reminder-literal-time").actual.turns[0].execution["reply"]


def test_replay_and_interrupted_recovery_do_not_execute_or_duplicate(report):
    replay = item(report, "reminder-saved-replay")
    assert len(replay.actual.reminder_records) == 1 and all(replay.actual.recovery_evidence.values())
    assert replay.actual.model_requests == 2
    interrupted = item(report, "reminder-interrupted-recovery")
    assert interrupted.actual.model_requests == 0 and interrupted.actual.reminder_records == []
    assert interrupted.actual.turns[0].status == "interrupted" and all(interrupted.actual.recovery_evidence.values())
    checks, _ = rescored(replay, lambda actual: actual.recovery_evidence.update(zero_new_tools=False))
    assert checks["recovery.zero_new_tools"] is False


def test_isolated_runner_preserves_parent_databases_and_metrics(tmp_path, monkeypatch):
    from app.observability.monitoring import registry
    from prometheus_client import generate_latest
    chats, reminders = tmp_path / "private-chats.sqlite3", tmp_path / "private-reminders.sqlite3"
    chats.write_bytes(b"existing chat bytes"); reminders.write_bytes(b"existing reminder bytes")
    monkeypatch.setenv("OPSFLOW_CHATS_DB", str(chats)); monkeypatch.setenv("OPSFLOW_REMINDERS_DB", str(reminders))
    before = generate_latest(registry)
    saved = load_report(runtime_runner.run_runtime(tmp_path / "reports", case_ids=["reminder-saved-replay"]))
    assert len(saved.cases[0].actual.reminder_records) == 1
    assert chats.read_bytes() == b"existing chat bytes" and reminders.read_bytes() == b"existing reminder bytes"
    assert generate_latest(registry) == before


@pytest.mark.parametrize("budget", ["requests", "cases"])
def test_budget_stops_run_and_retains_all_planned_cases(tmp_path, budget):
    saved = load_report(runtime_runner.run_runtime(tmp_path, case_ids=["agent-summary-source", "reminder-literal-time"],
                max_requests=1 if budget == "requests" else 60, max_cases=1 if budget == "cases" else 24))
    assert saved.state == "failed" and saved.failure_code == "budget_exhausted" and len(saved.cases) == 2
    assert saved.cases[1].execution == "not_run"
    if budget == "requests":
        assert saved.cases[0].actual.model_requests == 1 and saved.cases[0].actual.budget_exhausted
        assert saved.cases[0].checks["within_budget"] is False
    assert saved.metrics["runtime.contract_success"].denominator == 2


@pytest.mark.parametrize("failure", ["timeout", "worker_error", "interrupted"])
def test_runner_failures_never_resume_and_leave_honest_records(tmp_path, monkeypatch, failure):
    original = runtime_runner.subprocess.run
    calls = 0
    def run(args, **kwargs):
        nonlocal calls
        if "--worker" not in args:
            return original(args, **kwargs)
        calls += 1
        if failure == "timeout": raise subprocess.TimeoutExpired(args, 300)
        if failure == "interrupted": raise KeyboardInterrupt
        return subprocess.CompletedProcess(args, 1)
    monkeypatch.setattr(runtime_runner.subprocess, "run", run)
    saved = load_report(runtime_runner.run_runtime(tmp_path, case_ids=["agent-summary-source", "reminder-literal-time"]))
    assert calls == 1 and saved.state in {"failed", "interrupted"}
    assert saved.cases[1].execution == "not_run" and saved.metrics["runtime.observation_coverage"].value == 0


def test_repeated_scripted_samples_remain_distinct_not_live_stability(tmp_path):
    saved = load_report(runtime_runner.run_runtime(tmp_path, case_ids=["extract-missing-source"], repeats=3))
    assert [result.sample for result in saved.cases] == [1, 2, 3]
    assert len({result.case.case_id for result in saved.cases}) == 3
    assert all(result.reference_case_id == "extract-missing-source" for result in saved.cases)
    assert saved.provenance["execution_mode"] == "scripted"


@pytest.mark.parametrize("damage", ["duplicate", "dependency", "transport", "clock", "missing_args", "schema"])
def test_malformed_references_rejected_before_execution(damage):
    data = json.loads(runtime_runner.PILOT.read_text())
    if damage == "duplicate": data["cases"].append(data["cases"][0])
    elif damage == "dependency": data["cases"][0]["turns"][0]["calls"][0]["dependency_call"] = "absent"
    elif damage == "transport": data["cases"][0]["turns"][0]["expected_http_status"] = 200
    elif damage == "clock": data["cases"][0]["frozen_now"] = "2026-10-14T06:00:00"
    elif damage == "missing_args": data["cases"][0]["turns"][0]["calls"][0]["arguments"] = {}
    else: data["schema_version"] = 3
    with pytest.raises(ValidationError): RuntimePilot.model_validate_json(json.dumps(data))


def test_changed_reference_fingerprint_rejected_before_subprocess(tmp_path, monkeypatch):
    data = json.loads(runtime_runner.PILOT.read_text()); data["faq_sha256"] = "0" * 64
    path = tmp_path / "pilot.json"; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        runtime_runner.load_runtime_cases(path)


def test_schema_versions_roundtrip_and_finished_writer_stays_immutable(report, tmp_path):
    assert parse_report(report.model_dump_json()) == report
    writer = ReportWriter(tmp_path, report.run_id); writer.save(report)
    assert load_report(writer.path) == report
    with pytest.raises(ValueError, match="finished"): writer.save(report)
    data = report.model_dump(mode="json"); data["cases"][0]["actual"]["model_requests"] += 1
    with pytest.raises(ValidationError): parse_report(json.dumps(data))


def test_fresh_reader_cannot_import_runtime_runner_or_tools(report, tmp_path):
    path = tmp_path / "report.json"; path.write_text(report.model_dump_json())
    code = """
import sys
class Guard:
    def find_spec(self, name, *args):
        if name in {'app.evaluation.runtime_runner', 'app.core.agent', 'app.core.runtime'} or name.startswith('app.tools.'):
            raise AssertionError(name)
sys.meta_path.insert(0, Guard())
from pathlib import Path
from app.evaluation.reports import load_report
assert load_report(Path(sys.argv[1])).schema_version == 2
"""
    process = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr


def test_runtime_page_and_api_read_only_retain_old_baseline(workspace, tmp_path, monkeypatch, report):
    monkeypatch.setenv("OPSFLOW_EVALUATIONS_DIR", str(tmp_path))
    path = tmp_path / report.run_id / "report.json"; path.parent.mkdir(); path.write_text(report.model_dump_json())
    original = path.read_bytes()
    client = TestClient(app); reads = []
    def read(request, **kwargs):
        reads.append(request.method)
        response = client.get(request.full_url)
        return Response(response.json(), response.status_code)
    monkeypatch.setattr(evaluations, "urlopen", read)
    monkeypatch.setattr(runtime_runner, "run_runtime", Mock(side_effect=AssertionError("Read executed runtime")))
    ui = open_chat(); ui.text_area(key="composer").set_value("Unsent runtime draft").run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and any("Scripted provider" in warning.value for warning in ui.warning)
    ui.selectbox(key="evaluation_case").select("reminder-partial-failure-r1").run()
    assert not ui.exception and "Turn 1: partial_failure" in [element.value for element in ui.text]
    assert any("SMTP attempts: 0" in element.value for element in ui.text)
    ui.button(key="refresh_evaluations").click().run(); ui.run()
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == "Unsent runtime draft"
    assert set(reads) == {"GET"} and path.read_bytes() == original
    assert any(run["source"] == "bundled" for run in client.get("/api/v1/evaluations").json())
    workspace[1].assert_not_called(); runtime_runner.run_runtime.assert_not_called()


def test_missing_dependency_calls_have_zero_matches_not_negative_scores(report):
    result = item(report, "agent-policy-to-draft")
    checks, evidence = rescored(result, lambda actual: actual.turns[0].execution.update(trace=[]))
    assert checks["turn_1.required_calls"] is False and checks["turn_1.dependency_values"] is False
    assert evidence["turns"][0]["matched"] == 0


@pytest.mark.parametrize("kwargs", [{"mode": "automatic"}, {"max_requests": 61}, {"max_requests": 0},
                                    {"repeats": 4}, {"case_ids": ["missing"]}])
def test_invalid_selection_or_budget_never_executes(tmp_path, monkeypatch, kwargs):
    worker = Mock(side_effect=AssertionError("Unexpected subprocess"))
    monkeypatch.setattr(runtime_runner.subprocess, "run", worker)
    with pytest.raises(ValueError): runtime_runner.run_runtime(tmp_path, **kwargs)
    worker.assert_not_called()


def test_failed_atomic_checkpoint_is_reported_without_reexecuting(tmp_path, monkeypatch):
    from app.evaluation import reports
    saved = reports.ReportWriter.save
    calls = 0
    def fail(writer, report):
        nonlocal calls
        calls += 1
        if calls == 2: raise OSError("controlled storage failure")
        return saved(writer, report)
    monkeypatch.setattr(reports.ReportWriter, "save", fail)
    path = runtime_runner.run_runtime(tmp_path, case_ids=["extract-missing-source", "reminder-literal-time"])
    report = load_report(path)
    assert report.state == "failed" and report.failure_code == "evaluation_failed"
    assert report.cases[0].actual.model_requests == 1 and report.cases[1].execution == "not_run"
