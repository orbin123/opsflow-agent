from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app import runtime
from app.main import app
from app.routes import faq_route
from app.tools.faq import FAQCandidate, FAQResult


client = TestClient(app)


@pytest.mark.parametrize(("message", "status", "policy_id"), [
    ("What is the remote-work policy?", "matched", "REMOTE-01"),
    ("What is the cafeteria policy?", "no_match", None),
    ("What is the public holidays policy?", "ambiguous", None),
])
def test_real_classifier_to_retrieval(message, status, policy_id):
    response = client.post("/api/v1/faq", json={"message": message})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed" and data["route"] == "direct"
    assert data["predicted_intent"] == "faq_retrieval"
    assert 0.71 <= data["confidence"] <= 1
    assert data["faq"]["status"] == status
    assert data["faq"]["policy_id"] == policy_id
    assert data["faq"]["is_demo"] is True
    assert len(data["trace"]) == 1
    trace = data["trace"][0]
    assert trace["tool"] == "retrieve_faq"
    assert trace["arguments"] == {"question": message}
    assert trace["result"] == data["faq"]
    assert trace["status"] == "completed"
    assert data["elapsed_ms"] >= trace["elapsed_ms"] >= 0


def test_ambiguity_response_preserves_candidates(monkeypatch):
    # Isolate serialization from the retriever's independently tested heuristics.
    result = FAQResult("ambiguous", (FAQCandidate("LEAVE-01", "How do I request annual leave?", 0.5),))
    monkeypatch.setattr(faq_route, "retrieve_faq", Mock(return_value=result))
    response = client.post("/api/v1/faq", json={"message": "What is the leave policy?"})
    data = response.json()
    assert response.status_code == 200
    assert data["faq"]["status"] == "ambiguous"
    assert data["faq"]["answer"] is None
    assert data["faq"]["candidates"][0]["policy_id"] == "LEAVE-01"
    assert data["trace"][0]["result"] == data["faq"]


@pytest.mark.parametrize("message", [
    "Remind me tomorrow to check the remote-work policy",
    "What is the remote-work policy? Then draft an email.",
    "What about that policy?",
])
def test_real_requests_requiring_agent_have_no_trace_or_execution(message, monkeypatch):
    tool = Mock()
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    response = client.post("/api/v1/faq", json={"message": message})
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "agent_required" and data["route"] == "agent"
    assert data["trace"] == [] and data["faq"] is None
    tool.assert_not_called()


def test_server_prediction_gates_low_confidence(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("faq_retrieval", 0.70, 0.71)))
    tool = Mock()
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    data = client.post("/api/v1/faq", json={"message": "What is the remote-work policy?"}).json()
    assert data["reason"] == "low_confidence" and data["status"] == "agent_required"
    assert data["trace"] == []
    tool.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": " \n"}, {"message": 12},
    {"message": None}, {"message": ["leave"]}, {"message": "a" * 10001},
    {"message": "What is the leave policy?", "confidence": 1},
    {"message": "What is the leave policy?", "intent": "faq_retrieval"}])
def test_invalid_input_does_not_classify(body, monkeypatch):
    classifier = Mock()
    monkeypatch.setattr(runtime, "classify_request", classifier)
    assert client.post("/api/v1/faq", json=body).status_code == 422
    classifier.assert_not_called()


def test_classifier_failure_is_503_without_sensitive_details(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(side_effect=RuntimeError("private path and input")))
    tool = Mock()
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    response = client.post("/api/v1/faq", json={"message": "What is the leave policy?"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Intent classifier unavailable"}
    tool.assert_not_called()


def test_tool_failure_is_not_reported_as_no_match_or_success(monkeypatch):
    tool = Mock(side_effect=RuntimeError("private policy data"))
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    response = client.post("/api/v1/faq", json={"message": "What is the remote-work policy?"})
    data = response.json()
    assert response.status_code == 503
    assert data["status"] == "error" and data["reason"] == "faq_unavailable"
    assert data["faq"] is None
    assert data["trace"][0]["status"] == "failed"
    assert data["trace"][0]["result"] is None
    assert "private" not in response.text
    tool.assert_called_once()


def test_openapi_documents_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/v1/faq" in schema["paths"]
    assert "FAQResponse" in schema["components"]["schemas"]


def test_non_faq_prediction_preserves_faq_only_endpoint(monkeypatch):
    from app.routes import sentiment_route

    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("sentiment_analysis", 1, 0.71)))
    tool = Mock()
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", tool)
    response = client.post("/api/v1/faq", json={"message": 'Sentiment: "sad"'})
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "agent_required" and data["reason"] == "intent_not_faq"
    assert data["faq"] is None and data["trace"] == []
    tool.assert_not_called()


def test_routing_unavailability_preserves_generic_503(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("faq_retrieval", 1, 0.71)))
    monkeypatch.setattr(runtime, "try_direct_faq", Mock(side_effect=RuntimeError("private FAQ path")))
    response = client.post("/api/v1/faq", json={"message": "What is the remote-work policy?"})
    assert response.status_code == 503
    assert response.json() == {"detail": "FAQ routing unavailable"}
