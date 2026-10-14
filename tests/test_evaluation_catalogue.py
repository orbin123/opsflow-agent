"""Saved-report boundaries and zero-execution Settings navigation."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient
import pytest

from app.evaluation import catalogue, runner
from app.evaluation.contracts import Metric
from app.main import app
from app.ui import evaluations, ui_client
from tests.test_evaluation import running_report
from tests.test_streamlit_ui import Response, send_message
from tests.test_workspace_navigation import workspace, open_chat


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "reports #local"
    monkeypatch.setenv("OPSFLOW_EVALUATIONS_DIR", str(root))
    # Separate the tracked baseline from local-storage tests.
    monkeypatch.setattr(catalogue, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_baseline", Mock(side_effect=AssertionError("Read executed evaluation")))
    return root


def seed(root, report=None):
    report = report or running_report()
    path = root / report.run_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json())
    return path


def test_missing_storage_is_empty_and_never_created(storage):
    client = TestClient(app)
    assert client.get("/api/v1/evaluations").json() == []
    assert not storage.exists()
    assert client.get("/api/v1/evaluations/" + "a" * 32).status_code == 404
    assert client.post("/api/v1/evaluations", json={}).status_code == 405
    assert not storage.exists()


def test_incomplete_and_interrupted_snapshots_are_literal_and_unchanged(storage):
    initial = running_report()
    path = seed(storage, initial)
    interrupted = initial.model_copy(update={"run_id": "b" * 32, "state": "interrupted",
                                            "finished_at": "2026-10-14T00:01:00Z", "failure_code": "interrupted"})
    other = seed(storage, interrupted)
    before = [path.read_bytes(), other.read_bytes()]
    client = TestClient(app)
    runs = client.get("/api/v1/evaluations").json()
    assert {run["state"] for run in runs} == {"running", "interrupted"}
    assert all(run["quality_verdict"] == "not_scored" and run["observed"] == 0 for run in runs)
    for report in (initial, interrupted):
        response = client.get("/api/v1/evaluations/" + report.run_id)
        assert response.status_code == 200
        assert response.json() == {"source": "local", "report": report.model_dump(mode="json")}
    assert [path.read_bytes(), other.read_bytes()] == before
    runner.run_baseline.assert_not_called()


@pytest.mark.parametrize("damage", ["missing", "json", "schema", "identity", "utf8", "directory_link", "file_link"])
def test_bad_records_remain_visible_without_leaking_or_following_paths(storage, tmp_path, damage):
    report = running_report()
    path = seed(storage, report)
    outside = tmp_path / "private-report.json"
    outside.write_text(report.model_dump_json())
    if damage == "missing":
        path.unlink()
    elif damage == "json":
        path.write_text("private corrupt input")
    elif damage == "schema":
        path.write_text(json.dumps({"private": "invalid schema"}))
    elif damage == "identity":
        path.write_text(report.model_copy(update={"run_id": "b" * 32}).model_dump_json())
    elif damage == "utf8":
        path.write_bytes(b"\xff")
    elif damage == "file_link":
        path.unlink()
        path.symlink_to(outside)
    else:
        path.unlink()
        path.parent.rmdir()
        path.parent.symlink_to(tmp_path, target_is_directory=True)
    client = TestClient(app)
    runs = client.get("/api/v1/evaluations").json()
    expected = "missing" if damage == "missing" else "invalid"
    assert runs[0]["report_status"] == expected and runs[0]["state"] is None
    response = client.get("/api/v1/evaluations/" + report.run_id)
    assert response.status_code == (404 if damage == "missing" else 422)
    assert "private" not in response.text
    assert outside.read_text() == report.model_dump_json()


@pytest.mark.parametrize("suffix", ["not-a-run", "a" * 31, "a" * 33, "%2e%2e%2fprivate", "a" * 32 + "?source=other"])
def test_invalid_ids_and_source_rejected(storage, suffix):
    assert TestClient(app).get("/api/v1/evaluations/" + suffix).status_code in {404, 422}
    assert not storage.exists()


def test_unavailable_storage_safe_and_not_repaired(storage, monkeypatch):
    storage.write_text("private invalid root")
    response = TestClient(app).get("/api/v1/evaluations")
    assert response.status_code == 503 and "private" not in response.text
    storage.unlink()
    path = seed(storage)
    original = Path.read_text
    def denied(current, *args, **kwargs):
        if current == path:
            raise PermissionError("private filesystem")
        return original(current, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", denied)
    assert TestClient(app).get("/api/v1/evaluations").json()[0]["report_status"] == "unavailable"
    assert TestClient(app).get("/api/v1/evaluations/" + "a" * 32).status_code == 503


def test_bundled_selected_report_is_exact_historical_evidence(storage, monkeypatch):
    monkeypatch.setattr(catalogue, "ROOT", Path(__file__).resolve().parents[1])
    original = (catalogue.ROOT / "var/evaluations" / catalogue.BUNDLED_ID / "report.json")
    tracked = catalogue.ROOT / "data/evaluation/baseline.json"
    if original.exists():
        assert original.read_bytes() == tracked.read_bytes()
    response = TestClient(app).get(f"/api/v1/evaluations/{catalogue.BUNDLED_ID}?source=bundled")
    saved = catalogue.SavedReport.model_validate_json(response.text)
    assert saved.source == "bundled" and len(saved.report.cases) == 224
    assert saved.report.provenance["source_commit"].startswith("140d8f6")
    assert not saved.report.provenance["working_tree_dirty"]
    assert saved.report.provenance["reference_status"] == "ai_authored_pending_human_review"
    assert saved.report.metrics["classifier.accuracy"].value == .88
    assert TestClient(app).get("/api/v1/evaluations/" + "b" * 32 + "?source=bundled").status_code == 404
    assert not storage.exists()


def test_reader_fresh_process_does_not_import_runner_or_side_effects(storage):
    seed(storage)
    script = """
import sys
class Guard:
    def find_spec(self, fullname, *args):
        if fullname in {'app.evaluation.runner', 'app.core.agent', 'app.core.runtime', 'app.tools.faq',
                        'app.tools.reminders', 'app.reminders.reminder_worker'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
from app.evaluation.catalogue import read_saved_report
assert read_saved_report('a' * 32).report.state == 'running'
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def connect_reads(monkeypatch):
    client = TestClient(app)
    seen = []
    def read(request, **kwargs):
        seen.append(request.method)
        response = client.get(request.full_url)
        if response.status_code != 200:
            raise HTTPError(request.full_url, response.status_code, "unavailable", {}, Response(response.json()))
        return Response(response.json())
    monkeypatch.setattr(evaluations, "urlopen", read)
    return seen


def test_evaluation_navigation_preserves_chat_draft_and_refresh_only_reads(workspace, storage, monkeypatch):
    recorded, execute = workspace
    seed(storage)
    seen = connect_reads(monkeypatch)
    ui = open_chat()
    send_message(ui, "Saved synthetic request")
    key = ui.session_state["session_id"]
    draft = "Unsent **literal**\nSecond line <detail>"
    ui.text_area(key="composer").set_value(draft).run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and not ui.text_area and not ui.chat_message
    assert ui.query_params["chat"] == key
    assert any("Incomplete saved snapshot" in item.value for item in ui.warning)
    assert any("Not scored" in item.value for item in ui.info)
    ui.button(key="refresh_evaluations").click().run()
    ui.selectbox(key="evaluation_case").select("faq-test").run()
    ui.run()
    assert not ui.exception and set(seen) == {"GET"}
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == draft
    assert len(recorded) == execute.call_count == 1
    runner.run_baseline.assert_not_called()


@pytest.mark.parametrize("state", ["pending", "running", "unknown"])
def test_unconfirmed_work_blocks_evaluation_navigation(workspace, storage, state):
    from app.chat import sessions
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    if state == "pending":
        ui.session_state["pending"] = True
    elif state == "running":
        sessions._get_store().begin(key, "Pending request", "in-progress")
    else:
        ui.session_state["uncertain"] = {key: dict(session_id=key, turn_id="unknown", message="Pending",
            execution=None, state="unknown", error="Unconfirmed")}
    ui.run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    workspace[1].assert_not_called()


@pytest.mark.parametrize("display", ["empty", "invalid", "unavailable", "partial"])
def test_page_failure_and_unscored_states_keep_return_available(workspace, storage, monkeypatch, display):
    if display in {"invalid", "partial"}:
        report = running_report()
        report.cases[0].case.input = "Literal **input**\n<second line>"
        report.metrics["faq.empty"] = Metric(value=None, numerator=0, denominator=0,
                                            status="not_scored", note="No observed matches")
        path = seed(storage, report)
        if display == "invalid":
            path.write_text("invalid private JSON")
    elif display == "unavailable":
        storage.write_text("invalid root")
    connect_reads(monkeypatch)
    ui = open_chat()
    ui.text_area(key="composer").set_value("Welcome draft").run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception
    if display == "empty":
        assert any("No local evaluation" in item.value for item in ui.info)
    elif display == "invalid":
        assert "invalid" in ui.warning[0].value
    elif display == "unavailable":
        assert "unavailable" in ui.error[0].value
    else:
        assert any("Not scored" in frame.value.to_string() for frame in ui.dataframe)
        assert "Literal **input**\n<second line>" in [item.value for item in ui.text]
    ui.run()
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == "Welcome draft"
    workspace[1].assert_not_called()


@pytest.mark.parametrize("failure", [URLError("private"), TimeoutError("private"), {"bad": "private"}])
def test_client_errors_are_safe_and_never_retried(monkeypatch, failure):
    send = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=Response(failure))
    monkeypatch.setattr(evaluations, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError) as error:
        evaluations.list_evaluations("http://localhost")
    assert "private" not in str(error.value) and send.call_count == 1



def test_configured_directory_is_shared_and_resolves_relative_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPSFLOW_EVALUATIONS_DIR", "local reports")
    assert catalogue.report_directory() == tmp_path / "local reports"
    assert not (tmp_path / "local reports").exists()


def test_page_bundled_failures_and_missing_scores_are_honest(workspace, storage, monkeypatch):
    monkeypatch.setattr(catalogue, "ROOT", Path(__file__).resolve().parents[1])
    seen = connect_reads(monkeypatch)
    ui = open_chat()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception
    assert any("historical local execution" in item.value for item in ui.warning)
    assert "Quality verdict: has_failures" in "\n".join(item.value for item in ui.text)
    ui.selectbox(key="evaluation_case").select('faq-04').run()
    assert not ui.exception
    assert any("Fail" in frame.value.to_string() for frame in ui.dataframe)
    assert any("Not scored" in frame.value.to_string() for frame in ui.dataframe)
    assert set(seen) == {"GET"}
    workspace[1].assert_not_called()


def test_wrong_report_identity_is_not_displayed(monkeypatch):
    saved = catalogue.SavedReport(source="local", report=running_report())
    send = Mock(return_value=Response(saved.model_dump(mode="json")))
    monkeypatch.setattr(evaluations, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError, match="different evaluation"):
        evaluations.get_evaluation("http://localhost", catalogue.SavedRun(
            run_id="b" * 32, source="local", report_status="available"))
    assert send.call_count == 1


def test_other_tab_running_work_restores_recovery_from_evaluations(workspace, storage, monkeypatch):
    from app.chat import sessions
    connect_reads(monkeypatch)
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    ui.text_area(key="composer").set_value("Preserve me").run()
    ui.button(key="open_evaluations").click().run()
    ui.run()
    sessions._get_store().begin(key, "Started elsewhere", "other-tab")
    ui.run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    assert ui.button(key="recover_chat") and ui.text_area(key="composer").value == "Preserve me"
    workspace[1].assert_not_called()
