"""Recorded classifier results and read-only two-section Settings presentation."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import URLError

from fastapi.testclient import TestClient
import pytest

from app.evaluation import classifier_report, generation_quality
from app.main import app
from app.ui import evaluations, ui_client
from tests.test_streamlit_ui import Response, send_message
from tests.test_workspace_navigation import workspace, open_chat


@pytest.fixture
def recorded_model(tmp_path, monkeypatch):
    metadata = json.loads((classifier_report.MODEL_DIR / "intent_router_svm_metadata.json").read_text())
    model = tmp_path / "intent_router_svm.joblib"
    model.write_bytes(b"Test-only model bytes; must never be loaded")
    metadata["model_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    path = tmp_path / "intent_router_svm_metadata.json"
    path.write_text(json.dumps(metadata))
    monkeypatch.setattr(classifier_report, "MODEL_DIR", tmp_path)
    return metadata, path, model


@pytest.fixture(autouse=True)
def missing_generation_review(tmp_path, monkeypatch):
    monkeypatch.setattr(generation_quality, "REVIEW_PATH", tmp_path / "missing-review.json")


def connect_reads(monkeypatch):
    client = TestClient(app)
    reads = []

    def read(request, **kwargs):
        reads.append((request.method, request.full_url))
        response = client.get(request.full_url)
        return Response(response.json(), response.status_code)

    monkeypatch.setattr(evaluations, "urlopen", read)
    return reads


def test_report_preserves_saved_values_and_full_classification_rows(recorded_model):
    metadata, path, model = recorded_model
    original = path.read_bytes(), model.read_bytes()
    report = classifier_report.read_classifier_report()
    assert report.test_metrics.accuracy == .88
    assert report.test_metrics.per_label["faq_retrieval"].precision == pytest.approx(.724137931)
    rows = evaluations.classification_rows(report)
    assert len(rows) == 10 and {r["Support"] for r in rows[:8]} == {25}
    assert rows[2] == {"Intent": "FAQ retrieval", "Precision": "0.7241", "Recall": "0.8400",
                       "F1 score": "0.7778", "Support": 25}
    assert rows[-2] == {"Intent": "Macro average", "Precision": "0.8842", "Recall": "0.8800",
                        "F1 score": "0.8813", "Support": 200}
    assert rows[-1] == {**rows[-2], "Intent": "Weighted average"}
    assert (path.read_bytes(), model.read_bytes()) == original


def test_macro_and_weighted_averages_use_their_actual_denominators(recorded_model):
    metadata, path, _ = recorded_model
    # One class contributes 50 examples; each other class contributes 20.
    scores = metadata["test_metrics"]["per_label"]
    for score in scores.values():
        score.update(precision=.5, recall=.5, **{"f1-score": .5, "support": 20.0})
    scores["compound_request"].update(precision=1.0, recall=1.0, **{"f1-score": 1.0, "support": 50.0})
    metadata["split"]["test_rows"] = 190
    metadata["dataset"]["row_count"] = 990
    metadata["test_metrics"].update(accuracy=120/190, macro_f1=.5625, weighted_f1=120/190)
    path.write_text(json.dumps(metadata))
    macro, weighted = classifier_report.read_classifier_report().averages()
    assert macro == {name: .5625 for name in ("Precision", "Recall", "F1")}
    assert weighted == {name: 120/190 for name in ("Precision", "Recall", "F1")}


@pytest.mark.parametrize("damage", ["missing", "json", "labels", "support", "score", "average", "model"])
def test_invalid_results_never_become_a_score_or_leak_file_data(recorded_model, damage):
    metadata, path, model = recorded_model
    if damage == "missing":
        path.unlink()
    elif damage == "json":
        path.write_text("private invalid JSON")
    elif damage == "model":
        model.write_bytes(b"Changed model")
    else:
        if damage == "labels":
            metadata["dataset"]["labels"][-1] = metadata["dataset"]["labels"][0]
        elif damage == "support":
            metadata["test_metrics"]["per_label"]["summarization"]["support"] = 24.5
        elif damage == "score":
            metadata["test_metrics"]["per_label"]["summarization"]["precision"] = 1.1
        else:
            metadata["test_metrics"]["macro_f1"] = 1.0
        path.write_text(json.dumps(metadata))
    response = TestClient(app).get("/api/v1/evaluations")
    assert response.status_code == 503
    assert response.json() == {"detail": "Classifier results are unavailable"}


def test_api_has_only_the_single_read_contract(recorded_model):
    client = TestClient(app)
    response = client.get("/api/v1/evaluations")
    report = classifier_report.ClassifierReport.model_validate_json(response.text)
    assert response.status_code == 200 and len(report.test_metrics.per_label) == 8
    assert set(response.json()) == {"created_on", "dataset", "split", "pipeline", "test_metrics"}
    assert client.post("/api/v1/evaluations", json={}).status_code == 405
    assert client.get("/api/v1/evaluations/" + "a"*32).status_code == 404


def test_reader_in_fresh_process_never_imports_models_or_execution():
    script = """
import sys
class Guard:
    def find_spec(self, fullname, *args):
        if fullname.startswith(('app.core', 'app.tools', 'app.workflows', 'app.reminders',
                                'joblib', 'sklearn', 'langchain', 'groq')):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
from app.evaluation.classifier_report import read_classifier_report
assert read_classifier_report().test_metrics.accuracy == .88
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_page_has_only_two_reports_and_no_execution_controls(workspace, recorded_model, monkeypatch):
    reads = connect_reads(monkeypatch)
    ui = open_chat()
    ui.button(key="open_evaluations").click().run()
    ui.run()
    assert not ui.exception
    assert [h.value for h in ui.main.subheader] == ["Classifier report", "Generation quality"]
    assert [e.label for e in ui.expander] == ["How classifier results are calculated", "How generation quality is assessed"]
    assert len(ui.table) == 2 and not ui.dataframe and not ui.selectbox and not ui.json
    assert not ui.get("download_button")
    assert ui.metric[0].value == "88.0%"
    quality = ui.table[1].value
    assert quality["Dimension"].tolist() == [name for name, _ in evaluations.CRITERIA]
    assert quality["Rating (0–3)"].tolist() == ["Not scored"] * 6
    explanation = "\n".join(m.value for m in ui.markdown)
    assert "Saved automated sample ratings" in explanation
    assert "subagent" not in explanation.lower()
    assert "12.5%" in explanation and "no combined generation score" in explanation
    assert all(method == "GET" and "/api/v1/evaluations" in url for method, url in reads)
    workspace[1].assert_not_called()


def test_return_preserves_selected_chat_and_multiline_draft(workspace, recorded_model, monkeypatch):
    reads = connect_reads(monkeypatch)
    ui = open_chat()
    send_message(ui, "Saved request")
    chat = ui.session_state["session_id"]
    draft = "Unsent **literal**\nSecond line <detail>"
    ui.text_area(key="composer").set_value(draft).run()
    ui.button(key="open_evaluations").click().run()
    ui.run()
    ui.button(key="return_to_chat").click().run()
    assert not ui.exception and ui.text_area(key="composer").value == draft
    assert ui.query_params["chat"] == chat
    assert len(workspace[0]) == workspace[1].call_count == 1
    assert {method for method, _ in reads} == {"GET"}


def test_missing_classifier_still_shows_pending_quality_and_return(workspace, recorded_model, monkeypatch):
    recorded_model[1].unlink()
    connect_reads(monkeypatch)
    ui = open_chat()
    ui.text_area(key="composer").set_value("Keep my draft").run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and "unavailable" in ui.error[0].value
    assert not ui.metric and len(ui.table) == 1
    assert ui.table[0].value["Rating (0–3)"].tolist() == ["Not scored"]*6
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == "Keep my draft"
    workspace[1].assert_not_called()


@pytest.mark.parametrize("state", ["pending", "running", "unknown"])
def test_unconfirmed_chat_work_blocks_evaluation_navigation(workspace, state):
    from app.chat import sessions
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    chat = ui.session_state["session_id"]
    if state == "pending":
        ui.session_state["pending"] = True
    elif state == "running":
        sessions._get_store().begin(chat, "Pending request", "in-progress")
    else:
        ui.session_state["uncertain"] = {chat: dict(session_id=chat, turn_id="unknown", message="Pending",
            execution=None, state="unknown", error="Unconfirmed")}
    ui.run()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    workspace[1].assert_not_called()


@pytest.mark.parametrize("failure", [URLError("private"), TimeoutError("private"), {"bad": "private"}])
def test_transport_failure_is_safe_and_never_retried(monkeypatch, failure):
    read = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=Response(failure))
    monkeypatch.setattr(evaluations, "urlopen", read)
    with pytest.raises(ui_client.ChatClientError, match="Classifier results are unavailable"):
        evaluations.get_classifier_report("http://localhost")
    assert read.call_count == 1
