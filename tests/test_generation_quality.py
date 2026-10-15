"""AI sample arithmetic, honest denominators and saved-only presentation."""

from copy import deepcopy
import json
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import URLError

from fastapi.testclient import TestClient
import pytest

from app.evaluation import generation_quality as quality
from app.main import app
from app.ui import evaluations, ui_client
from tests.test_evaluation import recorded_model, connect_reads
from tests.test_streamlit_ui import Response
from tests.test_workspace_navigation import workspace, open_chat


@pytest.fixture
def sample(tmp_path, monkeypatch):
    case = {"case_id": "summary-a", "input": "Summarize this fictional update.",
            "source": "Orion shipped 12 sensors; two checks remain.",
            "required_facts": ["12 sensors shipped", "Two checks remain"],
            "answer": "Orion shipped 12 sensors; two checks remain.", "application_status": "completed",
            "ratings": {name: {"score": 3, "applicable": True, "reason": "Synthetic test annotation, not model evidence."}
                        for name in quality.DIMENSIONS}, "critical_findings": []}
    omitted = deepcopy(case)
    omitted.update(case_id="summary-b", answer="Orion shipped 12 sensors.")
    omitted["ratings"]["coverage"]["score"] = 1
    absent = deepcopy(case)
    absent.update(case_id="unavailable", answer=None, application_status="error")
    for rating in absent["ratings"].values():
        rating.update(score=None, reason="Output unavailable.")
    for reviewed in (case, omitted, absent):
        reviewed["ratings"]["status_accuracy"].update(score=None, applicable=False, reason="No action/status claim requested.")
    data = {"schema_version": 1, "reviewer_type": "ai_subagent", "reviewed_at": "2026-10-14T18:00:00+05:30",
            "source_commit": "a"*40, "models": {"generation": "synthetic-test-fixture"}, "provider_attempts": 0,
            "cases": [case, omitted, absent], "limitations": ["Synthetic scorer fixture, not actual review evidence."]}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(quality, "REVIEW_PATH", path)
    return data, path


def test_mean_excludes_missing_and_inapplicable_but_retains_planned_counts(sample):
    before = sample[1].read_bytes()
    review = quality.read_generation_review()
    result = review.dimension_scores()
    assert result["coverage"] == {"mean": 2, "scored": 2, "applicable": 3, "planned": 3}
    assert result["status_accuracy"] == {"mean": None, "scored": 0, "applicable": 0, "planned": 3}
    assert sample[1].read_bytes() == before
    rows = evaluations.generation_rows(review)
    assert rows[1] == {"Dimension": "Coverage", "Rating (0–3)": "2.00", "Reviewed answers": "2 / 3"}
    assert rows[4]["Rating (0–3)"] == "Not scored"


@pytest.mark.parametrize("damage", ["missing", "malformed", "score", "absent_scored", "inapplicable_scored",
                                    "dimension", "duplicate", "human", "naive_date", "budget"])
def test_invalid_review_is_unavailable_without_fabricated_scores(sample, damage):
    data, path = sample
    if damage == "missing":
        path.unlink()
    elif damage == "malformed":
        path.write_text("private invalid JSON")
    else:
        if damage == "score": data["cases"][0]["ratings"]["faithfulness"]["score"] = 4
        elif damage == "absent_scored": data["cases"][2]["ratings"]["faithfulness"]["score"] = 3
        elif damage == "inapplicable_scored": data["cases"][0]["ratings"]["status_accuracy"]["score"] = 3
        elif damage == "dimension": del data["cases"][0]["ratings"]["coverage"]
        elif damage == "duplicate": data["cases"][1]["case_id"] = "summary-a"
        elif damage == "human": data["reviewer_type"] = "human"
        elif damage == "naive_date": data["reviewed_at"] = "2026-10-14T18:00:00"
        else: data["provider_attempts"] = 21
        path.write_text(json.dumps(data))
    response = TestClient(app).get("/api/v1/evaluations/generation")
    assert response.status_code == 503 and response.json() == {"detail": "Generation review is unavailable"}


def test_read_only_api_and_ui_show_actual_sample_means(workspace, recorded_model, sample, monkeypatch):
    reads = connect_reads(monkeypatch)
    before = sample[1].read_bytes()
    ui = open_chat()
    ui.button(key="open_evaluations").click().run()
    ui.run()
    assert not ui.exception and len(ui.table) == 2
    assert ui.table[1].value["Rating (0–3)"].tolist() == ["3.00", "2.00", "3.00", "3.00", "Not scored", "3.00"]
    assert any("Automated sample review" in c.value and "2 of 3" in c.value for c in ui.caption)
    assert "**Method**" in "\n".join(m.value for m in ui.markdown)
    assert not ui.selectbox and not ui.json and not ui.get("download_button")
    assert {method for method, _ in reads} == {"GET"} and sample[1].read_bytes() == before
    client = TestClient(app)
    assert client.post("/api/v1/evaluations/generation", json={}).status_code == 405
    workspace[1].assert_not_called()


def test_critical_findings_are_not_hidden_by_high_average_scores(workspace, recorded_model, sample, monkeypatch):
    data, path = sample
    data["cases"][0]["critical_findings"] = ["Synthetic fixture: fabricated delivery claim."]
    path.write_text(json.dumps(data))
    connect_reads(monkeypatch)
    ui = open_chat()
    ui.button(key="open_evaluations").click().run()
    assert not ui.exception and any("critical finding" in w.value for w in ui.warning)
    assert any("fabricated delivery claim" in t.value for t in ui.text)


def test_fresh_process_read_never_imports_execution_or_providers(sample):
    script = """
import sys
from pathlib import Path
class Guard:
    def find_spec(self, name, *args):
        if name.startswith(('app.core', 'app.tools', 'app.workflows', 'app.reminders', 'groq', 'langchain')):
            raise AssertionError(name)
sys.meta_path.insert(0, Guard())
from app.evaluation import generation_quality
generation_quality.REVIEW_PATH = Path(sys.argv[1])
assert generation_quality.read_generation_review().dimension_scores()['coverage']['mean'] == 2
"""
    result = subprocess.run([sys.executable, "-c", script, str(sample[1])], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("failure", [URLError("private"), TimeoutError("private"), {"bad": "private"}])
def test_generation_transport_failure_never_retries(monkeypatch, failure):
    read = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=Response(failure))
    monkeypatch.setattr(evaluations, "urlopen", read)
    with pytest.raises(ui_client.ChatClientError, match="Generation review is unavailable"):
        evaluations.get_generation_review("http://localhost")
    assert read.call_count == 1
