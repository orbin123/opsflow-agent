import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest

from app import agent, runtime, sessions, sentiment_workflow
from app.api import chat
from app.main import app
from app.tools.email_drafting import EmailDraft, EmailDraftResult, _ACTION_INSTRUCTIONS


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch, sentiment_provider):
    monkeypatch.setattr(sessions, "_sessions", {})
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected provider initialization"))


def post(message, session_id="one"):
    return client.post("/api/v1/chat", json={"session_id": session_id, "message": message})


def final(status="completed", reply="Done"):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


def install_model(monkeypatch, responses):
    seen = []
    responses = iter(responses)

    def invoke(messages):
        seen.append(list(messages))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(agent, "_create_model", lambda: Mock(invoke=invoke))
    return seen


def test_sentiment_request_serializes_workflow_result_and_trace(sentiment_provider):
    sentiment_provider("I am happy", "VADER classified this text as positive.")
    response = post('Sentiment: "I am happy"')
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "one"
    assert data["status"] == "completed" and data["route"] == "llm_assisted"
    assert data["predicted_intent"] == "sentiment_analysis" and data["confidence"] >= 0.71
    assert data["reply"] == "VADER classified this text as positive." and data["agent_reason"] is None
    assert [stage["stage"] for stage in data["workflow_trace"]] == ["extract_source", "analyze_sentiment", "explain_result"]
    assert data["result"]["label"] == "positive"
    assert data["trace"][0]["result"] == data["result"]
    assert data["trace"][0]["arguments"] == {"text": "I am happy"}
    assert data["elapsed_ms"] >= data["trace"][0]["elapsed_ms"] >= 0


def test_http_followup_receives_history_and_other_session_isolated(monkeypatch, sentiment_provider):
    sentiment_provider("I am happy")
    monkeypatch.setattr(runtime, "classify_request", lambda message:
                        ("sentiment_analysis" if message.startswith("Sentiment:") else "email_drafting", 1, 0.71))
    post('Sentiment: "I am happy"')
    seen = install_model(monkeypatch, [final("needs_clarification", "Who is the recipient?"), final()])
    response = post("Draft about that result")
    assert response.status_code == 200 and response.json()["status"] == "needs_clarification"
    assert response.json()["reply"] == "Who is the recipient?"
    assert response.json()["trace"] == []
    previous = json.loads(seen[0][-2].content)
    assert previous["result"]["label"] == "positive"
    assert seen[0][-1].content == "Draft about that result"
    post("Draft about that result", "two")
    assert len(seen[1]) == 2
    assert len(sessions._sessions["one"].history.messages) == 4
    assert len(sessions._sessions["two"].history.messages) == 2


def test_agent_draft_response_preserves_nested_content_and_actions(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("email_drafting", 1, 0.71))
    draft = EmailDraftResult(email_draft=EmailDraft(recipient="Alex", subject="Maintenance",
                            body="Hi Alex,\n\nMaintenance is Friday."),
                            action_instructions=list(_ACTION_INSTRUCTIONS))
    monkeypatch.setitem(agent._TOOLS, "draft_email", (agent.DraftArguments, lambda **kwargs: draft, "draft"))
    install_model(monkeypatch, [AIMessage(content="", tool_calls=[{
        "name": "draft_email", "args": {"recipient": "Alex", "content": "Maintenance is Friday."},
        "id": "call1",
    }], response_metadata={"finish_reason": "tool_calls"}), final()])
    response = post("Draft an email to Alex about Friday maintenance")
    assert response.status_code == 200
    data = response.json()
    assert data["route"] == "agent" and data["result"] is None
    assert data["trace"][0]["result"] == draft.model_dump()
    assert all(action in data["reply"] for action in _ACTION_INSTRUCTIONS)


@pytest.mark.parametrize("body", [
    {}, {"session_id": "one"}, {"message": "Hello"},
    {"session_id": None, "message": "Hello"}, {"session_id": 12, "message": "Hello"},
    {"session_id": " \n", "message": "Hello"}, {"session_id": "x" * 129, "message": "Hello"},
    {"session_id": "one", "message": ""}, {"session_id": "one", "message": " \n"},
    {"session_id": "one", "message": 12}, {"session_id": "one", "message": "x" * 10001},
    {"session_id": "one", "message": "Hello", "confidence": 1},
])
def test_invalid_body_rejected_before_execution(body, monkeypatch):
    execute = Mock()
    monkeypatch.setattr(chat, "execute_session_request", execute)
    assert client.post("/api/v1/chat", json=body).status_code == 422
    execute.assert_not_called()
    assert sessions._sessions == {}


def test_exact_limits_and_whitespace_preserved_and_execute_once(monkeypatch):
    execution = runtime.ExecutionResult("completed", "out_of_scope", 1, "agent", "intent_requires_agent",
                                        None, [], 1, "Done", None)
    execute = Mock(return_value=execution)
    monkeypatch.setattr(chat, "execute_session_request", execute)
    session_id, message = " " + "s" * 126 + " ", " " + "m" * 9998 + " "
    response = post(message, session_id)
    assert response.status_code == 200 and response.json()["session_id"] == session_id
    execute.assert_called_once_with(session_id, message)


def test_runtime_failure_sanitized_and_remembered(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(side_effect=RuntimeError("private artifact")))
    response = post("Hello")
    assert response.status_code == 503
    assert response.json() == {"detail": "Intent classifier unavailable"}
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    assert saved["status"] == "error" and saved["trace"] == []


def test_sentiment_failure_503_with_failed_trace_without_agent(monkeypatch, sentiment_provider):
    sentiment_provider("I am sad")
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, 0.71))
    monkeypatch.setattr(sentiment_workflow, "analyze_sentiment", Mock(side_effect=RuntimeError("private source")))
    response = post('Sentiment: "I am sad"')
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "error" and data["result"] is None
    assert data["trace"][0]["status"] == "failed"
    assert "private source" not in response.text


@pytest.mark.parametrize("partial", [False, True])
def test_agent_failure_503_preserves_actual_observations(monkeypatch, partial):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("compound_request", 1, 0.71))
    responses = [RuntimeError("private credentials")]
    if partial:
        responses.insert(0, AIMessage(content="", tool_calls=[{
            "name": "analyze_sentiment", "args": {"text": "I am happy"}, "id": "call1",
        }], response_metadata={"finish_reason": "tool_calls"}))
    install_model(monkeypatch, responses)
    response = post("Analyze then draft")
    data = response.json()
    assert response.status_code == 503
    assert data["status"] == ("partial_failure" if partial else "error")
    assert data["agent_reason"] == "provider_unavailable"
    assert data["result"] is None and data["reply"]
    assert "private credentials" not in response.text
    if partial:
        trace = data["trace"][0]
        assert trace["status"] == "completed" and trace["reason"] is None
        assert trace["result"]["label"] == "positive"
        assert trace["arguments"] == {"text": "I am happy"}
    else:
        assert data["trace"] == []


def test_openapi_describes_request_and_response():
    schema = client.get("/openapi.json").json()
    endpoint = schema["paths"]["/api/v1/chat"]["post"]
    assert "503" in endpoint["responses"]
    assert schema["components"]["schemas"]["ChatRequest"]["additionalProperties"] is False
    assert "trace" in schema["components"]["schemas"]["ChatResponse"]["properties"]
    response_fields = schema["components"]["schemas"]["ChatResponse"]["properties"]
    assert "llm_assisted" in response_fields["route"]["enum"]
    assert "workflow_trace" in response_fields
