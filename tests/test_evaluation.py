"""Scorer truth, reference validation, read-only rescoring and durable reports."""

import json
from math import log
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.evaluation import reports, runner
from app.evaluation.contracts import Case, CaseResult, Metric, Observation, Report
from app.evaluation.scoring import classifier_scores, eligibility, ratio, score_case, summarize_cases


PILOT = runner.ROOT / "data/evaluation/local_pilot.json"
METADATA = json.loads((runner.ROOT / "artifacts/models/intent_router_svm_metadata.json").read_text())


def faq_case():
    return Case(case_id="faq-test", suite="faq_pilot", input="A synthetic question", reference_note="Fixture",
                expected_faq_status="matched", expected_policy_id="REMOTE-01", source_sufficiency="missing_detail")


def running_report():
    return Report(run_id="a" * 32, started_at="2026-10-14T00:00:00+00:00", provenance={},
                  cases=[CaseResult(case=faq_case())], limitations=["Fixture only"])


def test_hand_computable_classification_and_calibration():
    labels = ["faq_retrieval", "summarization"]
    metrics, details = classifier_scores(labels, labels, [[0.8, 0.2], [0.4, 0.6]], labels, 0.7)
    assert metrics["classifier.accuracy"].value == 1
    assert metrics["classifier.macro_f1"].value == 1
    assert metrics["classifier.log_loss"].value == pytest.approx(-(log(0.8) + log(0.6)) / 2)
    assert metrics["classifier.multiclass_brier_score"].value == pytest.approx(0.2)
    assert metrics["classifier.top_label_ece"].value == pytest.approx(0.3)
    assert metrics["classifier.threshold_precision"].denominator == 1
    assert metrics["classifier.threshold_coverage"].value == 0.5
    assert details["confusion_matrix"] == [[1, 0], [0, 1]]
    assert sum(item["count"] for item in details["calibration_bins"]) == 2


def test_wrong_classification_and_agent_only_acceptance_are_visible():
    labels = ["faq_retrieval", "summarization"]
    metrics, _ = classifier_scores(labels, labels[::-1], [[0.2, 0.8], [0.8, 0.2]], labels, 0.7)
    assert metrics["classifier.accuracy"].value == 0
    assert metrics["classifier.macro_f1"].value == 0
    assert metrics["classifier.multiclass_brier_score"].value == pytest.approx(1.28)
    assert metrics["classifier.agent_only_false_acceptance"].numerator == 1
    assert metrics["classifier.threshold_precision"].value == 0


@pytest.mark.parametrize(("probabilities", "threshold"), [
    ([[0.8, 0.3], [0.4, 0.6]], 0.7),  # Invalid probability sum.
    ([[float("nan"), 0.2], [0.4, 0.6]], 0.7),
    ([[0.2, 0.8], [0.4, 0.6]], 0.7),  # Prediction disagrees with its probabilities.
    ([[0.8, 0.2], [0.4, 0.6]], 0.0),
])
def test_invalid_classification_evidence_rejected(probabilities, threshold):
    labels = ["faq_retrieval", "summarization"]
    with pytest.raises(ValueError, match="Invalid classification"):
        classifier_scores(labels, labels, probabilities, labels, threshold)


def test_no_eligible_predictions_or_applicable_faqs_are_not_perfect_scores():
    metric = ratio(0, 0, "No applicable cases")
    assert metric.value is None and metric.status == "not_scored" and metric.interval_95 is None
    metrics, _ = classifier_scores(["faq_retrieval", "summarization"], ["faq_retrieval", "summarization"],
                                   [[0.6, 0.4], [0.4, 0.6]], ["faq_retrieval", "summarization"], 0.9)
    assert metrics["classifier.threshold_precision"].status == "not_scored"
    summary = summarize_cases([CaseResult(case=faq_case())])
    assert summary["execution.availability"].value == 0
    assert summary["faq.match_precision"].value is None


def test_perfect_sample_still_has_uncertainty():
    metric = ratio(47, 47, "Synthetic sample")
    assert metric.interval_95[0] == pytest.approx(0.924442, abs=0.000001)
    assert metric.interval_95[1] == pytest.approx(1)


@pytest.mark.parametrize("kwargs", [
    {"value": float("nan"), "status": "scored", "note": "Invalid"},
    {"value": 1.0, "numerator": 1, "denominator": 0, "status": "scored", "note": "Invalid"},
    {"value": 0.5, "numerator": 1, "denominator": 3, "status": "scored", "note": "Invalid"},
])
def test_corrupt_metric_values_rejected(kwargs):
    with pytest.raises(ValidationError):
        Metric(**kwargs)


def test_threshold_equality_and_agent_only_labels():
    assert eligibility("faq_retrieval", 0.71, 0.71) == "workflow_eligible"
    assert eligibility("faq_retrieval", 0.70, 0.71) == "agent_required"
    for intent in ("reminder_creation", "compound_request", "summarization", "email_drafting", "out_of_scope"):
        assert eligibility(intent, 1, 0.71) == "agent_required"


def test_faq_scorer_detects_wrong_policy_and_wrong_answer_without_scoring_missing_facts():
    case = faq_case()
    answers = {"REMOTE-01": "Eligible roles need approval."}
    actual = Observation(faq_status="matched", policy_id="PAYROLL-01", answer="Paid monthly.")
    checks = score_case(case, actual, answers)
    assert checks == {"status_correct": True, "policy_correct": False,
                      "stored_answer_exact": False, "answer_sufficiency": None}
    correct = Observation(faq_status="matched", policy_id="REMOTE-01", answer=answers["REMOTE-01"])
    assert score_case(case, correct, answers)["answer_sufficiency"] is None
    changed = correct.model_copy(update={"answer": "All contractors are eligible."})
    assert score_case(case, changed, answers)["stored_answer_exact"] is False


def test_false_acceptance_and_abstention_scored_separately():
    case = faq_case().model_copy(update={"expected_faq_status": "no_match", "expected_policy_id": None,
                                        "source_sufficiency": "not_applicable"})
    actual = Observation(faq_status="matched", policy_id="REMOTE-01", answer="Policy")
    item = CaseResult(case=case, execution="completed", actual=actual, checks=score_case(case, actual, {}))
    metrics = summarize_cases([item])
    assert metrics["faq.wrong_acceptance"].value == 1
    assert metrics["faq.match_precision"].value == 0
    assert metrics["faq.match_recall"].value is None
    assert metrics["faq_pilot.answer_sufficiency"].status == "not_scored"


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_policy", "indexed_question", "bad_hash", "bad_reference"])
def test_invalid_reference_pilot_rejected_before_execution(tmp_path, monkeypatch, mutation):
    data = json.loads(PILOT.read_text())
    if mutation == "duplicate":
        data["cases"].append(data["cases"][0])
    elif mutation == "unknown_policy":
        data["cases"][8]["expected_policy_id"] = "UNKNOWN"
    elif mutation == "indexed_question":
        data["cases"][8]["input"] = "How do I request annual leave?"
    elif mutation == "bad_hash":
        data["faq_sha256"] = "0" * 64
    else:
        data["cases"][8]["expected_policy_id"] = None
    path = tmp_path / "pilot.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(runner, "load_router", lambda: pytest.fail("Invalid pilot executed classifier"))
    with pytest.raises(ValueError):
        runner.run_baseline(tmp_path / "reports", pilot_path=path)
    assert not (tmp_path / "reports").exists()


def test_classifier_dataset_fingerprint_mismatch_rejected(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "data").mkdir(parents=True)
    (root / "artifacts/models").mkdir(parents=True)
    (root / "data/company_faq.json").write_bytes((runner.ROOT / "data/company_faq.json").read_bytes())
    (root / "data/tasks_benchmark.csv").write_text("text,label\nChanged,summarization\n")
    (root / "artifacts/models/intent_router_svm_metadata.json").write_text(json.dumps(METADATA))
    monkeypatch.setattr(runner, "ROOT", root)
    with pytest.raises(ValueError, match="dataset fingerprint"):
        runner.load_cases(PILOT)


def test_model_fingerprint_mismatch_rejected_before_loading_even_with_existing_cache(tmp_path, monkeypatch):
    runner.load_router()  # Exercise the previously loaded artifact boundary.
    root = tmp_path / "source"
    for name in ("data/company_faq.json", "data/tasks_benchmark.csv",
                 "artifacts/models/intent_router_svm_metadata.json"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((runner.ROOT / name).read_bytes())
    (root / "artifacts/models/intent_router_svm.joblib").write_bytes(b"untrusted pickle")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "load_router", lambda: pytest.fail("Corrupt artifact loaded"))
    with pytest.raises(ValueError, match="model fingerprint"):
        runner.run_baseline(tmp_path / "reports", pilot_path=PILOT)
    assert not (tmp_path / "reports").exists()


def test_exclusive_run_writer_and_final_report_cannot_be_overwritten(tmp_path):
    report = running_report()
    with pytest.raises(ValueError, match="Invalid run ID"):
        reports.ReportWriter(tmp_path, "../escape")
    writer = reports.ReportWriter(tmp_path, report.run_id)
    with pytest.raises(FileExistsError):
        reports.ReportWriter(tmp_path, report.run_id)
    writer.save(report)
    report.state = "interrupted"
    report.failure_code = "interrupted"
    report.finished_at = report.started_at
    writer.save(report)
    original = writer.path.read_bytes()
    with pytest.raises(ValueError, match="finished"):
        writer.save(report)
    assert writer.path.read_bytes() == original


def test_atomic_write_failure_preserves_previous_valid_snapshot(tmp_path, monkeypatch):
    report = running_report()
    writer = reports.ReportWriter(tmp_path, report.run_id)
    writer.save(report)
    before = writer.path.read_bytes()
    def unavailable(*args):
        raise OSError("Controlled replace failure")
    monkeypatch.setattr(reports.os, "replace", unavailable)
    with pytest.raises(OSError):
        writer.save(report)
    assert writer.path.read_bytes() == before
    assert reports.load_report(writer.path).state == "running"
    assert list(writer.path.parent.iterdir()) == [writer.path]


def test_corrupt_report_and_fabricated_completion_rejected(tmp_path):
    path = tmp_path / "report.json"
    path.write_text('{"unfinished":')
    with pytest.raises(ValidationError):
        reports.load_report(path)
    data = json.loads(running_report().model_dump_json())
    data.update(state="completed", finished_at=data["started_at"])
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError, match="all cases executed"):
        reports.load_report(path)


def test_interruption_retains_observed_case_and_leaves_rest_unscored(tmp_path, monkeypatch):
    real_model, threshold = runner.load_router()
    class InterruptedModel:
        classes_ = real_model.classes_
        calls = 0
        def predict_proba(self, inputs):
            self.calls += 1
            if self.calls == 2:
                raise KeyboardInterrupt
            return real_model.predict_proba(inputs)
    monkeypatch.setattr(runner, "load_router", lambda: (InterruptedModel(), threshold))
    path = runner.run_baseline(tmp_path)
    report = reports.load_report(path)
    assert report.state == "interrupted" and report.failure_code == "interrupted"
    assert report.cases[0].execution == "completed"
    assert all(item.execution == "not_run" for item in report.cases[1:])
    assert report.metrics["execution.availability"].value == 1 / 224
    assert "classifier.accuracy" not in report.metrics


def test_case_execution_failure_is_sanitized_and_not_quality_success(tmp_path, monkeypatch):
    def unavailable(_):
        raise RuntimeError("Sensitive provider text must not be retained")
    monkeypatch.setattr(runner, "retrieve_faq", unavailable)
    path = runner.run_baseline(tmp_path)
    report = reports.load_report(path)
    assert report.state == "failed" and report.failure_code == "case_execution_failed"
    assert report.metrics["execution.availability"].value == 208 / 224
    assert all(item.execution == "failed" and item.failure_code == "execution_failed"
               for item in report.cases if item.case.suite == "faq_pilot")
    assert report.metrics["faq.match_precision"].status == "not_scored"
    assert "Sensitive" not in path.read_text()


def test_unavailable_model_preserves_unexecuted_cases_without_fabricated_scores(tmp_path, monkeypatch):
    def unavailable():
        raise ValueError("Sensitive model error")
    monkeypatch.setattr(runner, "load_router", unavailable)
    path = runner.run_baseline(tmp_path)
    report = reports.load_report(path)
    assert report.state == "failed" and report.failure_code == "evaluation_failed"
    assert report.quality_verdict == "not_scored"
    assert all(item.execution == "not_run" for item in report.cases)
    assert report.metrics["execution.availability"].value == 0
    assert "classifier.accuracy" not in report.metrics
    assert "Sensitive" not in path.read_text()


def test_cli_storage_failure_returns_nonzero_before_classifier_execution(tmp_path, monkeypatch, capsys):
    from app.evaluation.__main__ import main
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("Existing file")
    monkeypatch.setattr(sys, "argv", ["app.evaluation", "--report-dir", str(blocked)])
    monkeypatch.setattr(runner, "load_router", lambda: pytest.fail("Storage failure executed classifier"))
    assert main() == 1
    assert "could not start or save" in capsys.readouterr().out


def test_offline_cli_reproduces_holdout_without_network_or_side_effect_imports(tmp_path):
    # Fresh process: fail if a network connection, model fit or side-effect module is reached.
    script = '''
import importlib.abc, runpy, socket, sys
class BlockSideEffects(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"app.core.agent", "app.core.runtime", "app.chat.sessions", "app.tools.reminders",
                        "app.tools.email_notifications", "app.reminders.reminder_worker", "langchain_groq", "groq"}:
            raise AssertionError("Unexpected side-effect/provider import: " + fullname)
sys.meta_path.insert(0, BlockSideEffects())
def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected network or classifier fitting")
socket.socket.connect = forbidden
from sklearn.pipeline import Pipeline
Pipeline.fit = forbidden
sys.argv = ["app.evaluation", "--report-dir", sys.argv[1]]
runpy.run_module("app.evaluation", run_name="__main__")
'''
    process = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=runner.ROOT,
                             capture_output=True, text=True, timeout=45)
    assert process.returncode == 0, process.stdout + process.stderr
    path, = tmp_path.glob("*/report.json")
    report = reports.load_report(path)
    assert report.state == "completed" and len(report.cases) == 224
    assert report.provenance["reference_status"] == "ai_authored_pending_human_review"
    assert len([item for item in report.cases if item.case.suite == "router_pilot"]) == 8
    assert len([item for item in report.cases if item.case.suite == "faq_pilot"]) == 16
    for name in ("accuracy", "macro_f1", "log_loss", "multiclass_brier_score", "top_label_ece"):
        assert report.metrics["classifier." + name].value == pytest.approx(METADATA["test_metrics"][name])
    assert report.metrics["classifier.threshold_precision"].numerator == 47
    assert report.metrics["classifier.threshold_precision"].denominator == 47
    assert report.metrics["classifier.threshold_coverage"].value == 0.235
    assert report.metrics["faq_pilot.answer_sufficiency"].status == "not_scored"
    before = path.read_bytes()
    # Reads and pure rescoring make no network/tool calls and cannot modify the saved run.
    for item in report.cases:
        if item.case.suite != "faq_pilot":
            assert score_case(item.case, item.actual, {}) == item.checks
    assert path.read_bytes() == before
