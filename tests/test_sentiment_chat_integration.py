"""Verify classifier-first workflow dispatch and retained chat/history outcomes."""

import json
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
import pytest

from app import agent, runtime, sessions, sentiment_workflow as workflow
from app.agent import AgentResult, AgentTrace
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def offline(monkeypatch, sentiment_provider):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(sessions, "_sessions", {})
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected agent provider initialization"))


def response(payload):
    return AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "stop"})


def abstain(monkeypatch, status, reason):
    model = Mock()
    model.invoke.return_value = response({"status": status, "source_text": None, "reason": reason})
    monkeypatch.setattr(workflow, "_create_model", lambda *args: model)
    return model


def post(message):
    return client.post("/api/v1/chat", json={"session_id": "one", "message": message})


@pytest.mark.parametrize("message,source", [
    ("Just check the sentiment of this I am happy", "I am happy"),
    ('Analyze the sentiment of "  I am sad  "', "  I am sad  "),
    ("Check the sentiment of this I am NOT happy!\nThe service was poor.",
     "I am NOT happy!\nThe service was poor."),
])
def test_classifier_runs_first_and_workflow_executes_once_at_threshold(monkeypatch, sentiment_provider, message, source):
    classifier = Mock(return_value=("sentiment_analysis", 0.71, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    model = sentiment_provider(source)

    def create(*args):
        classifier.assert_called_once_with(message)
        return model

    monkeypatch.setattr(workflow, "_create_model", create)
    scorer = Mock(wraps=workflow.analyze_sentiment)
    monkeypatch.setattr(workflow, "analyze_sentiment", scorer)
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message)
    assert result.route == "llm_assisted" and result.status == "completed"
    assert result.reason == "sentiment_completed" and result.reply
    assert result.agent_reason is None
    assert result.trace[0].arguments == {"text": source}
    assert result.trace[0].result == result.result
    assert result.trace[0].elapsed_ms == result.workflow_trace[1].elapsed_ms
    assert result.elapsed_ms >= sum(stage.elapsed_ms for stage in result.workflow_trace)
    scorer.assert_called_once_with(source)
    assert model.invoke.call_count == 2
    handoff.assert_not_called()


@pytest.mark.parametrize("confidence,reason", [(0.70, "low_confidence"), (float("nan"), "invalid_confidence")])
def test_confidence_gate_never_starts_workflow(monkeypatch, confidence, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", confidence, 0.71))
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_sentiment_workflow", workflow_call)
    handoff = Mock(return_value=AgentResult("needs_clarification", "Which text?", None, [], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request("Check sentiment: happy")
    assert result.route == "agent" and result.reason == reason
    assert result.workflow_trace == []
    workflow_call.assert_not_called()
    handoff.assert_called_once_with("Check sentiment: happy")


def test_invalid_threshold_stops_before_any_provider_call(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, 0))
    workflow_call, handoff = Mock(), Mock()
    monkeypatch.setattr(runtime, "run_sentiment_workflow", workflow_call)
    monkeypatch.setattr(runtime, "run_agent", handoff)
    with pytest.raises(runtime.RuntimeUnavailable, match="Execution routing unavailable"):
        runtime.execute_request("Check sentiment: happy")
    workflow_call.assert_not_called()
    handoff.assert_not_called()


@pytest.mark.parametrize("message,reason", [
    ("Analyze the sentiment of that message", "context_required"),
    ("Analyze the sentiment and summarize this I am sad", "compound_request"),
    ("Send me an email", "unsupported_request"),
])
def test_extraction_abstention_hands_off_original_request_and_history_once(monkeypatch, message, reason):
    # Force a confident misclassification to check the second gate, independent
    # of the saved classifier's prediction for these examples.
    classifier = Mock(return_value=("sentiment_analysis", 1, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    model = abstain(monkeypatch, "agent_required", reason)
    scorer = Mock()
    monkeypatch.setattr(workflow, "analyze_sentiment", scorer)
    history = [HumanMessage(content="Earlier source"), AIMessage(content="Earlier result")]
    observation = AgentTrace("analyze_sentiment", {"text": "Earlier source"}, "completed",
                             {"label": "neutral"}, None, 0)
    handoff = Mock(return_value=AgentResult("completed", "Agent reply", None, [observation], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message, history=history)
    assert result.route == "agent" and result.reason == reason and result.reply == "Agent reply"
    assert result.result is None and result.trace == [observation]
    assert len(result.workflow_trace) == 1 and result.workflow_trace[0].reason == reason
    classifier.assert_called_once_with(message)
    handoff.assert_called_once_with(message, history=history)
    scorer.assert_not_called()
    model.invoke.assert_called_once()


@pytest.mark.parametrize("reason", ["missing_source", "ambiguous_source"])
def test_http_clarification_is_saved_without_tool_or_agent_execution(monkeypatch, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, 0.71))
    model = abstain(monkeypatch, "needs_clarification", reason)
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = post("Check the sentiment")
    data = result.json()
    assert result.status_code == 200
    assert data["route"] == "llm_assisted" and data["status"] == "needs_clarification"
    assert data["reason"] == reason and data["reply"]
    assert data["trace"] == [] and data["result"] is None
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    assert saved["workflow_trace"] == data["workflow_trace"]
    assert saved["reply"] == data["reply"]
    assert len(sessions._sessions["one"].history.messages) == 2
    handoff.assert_not_called()
    model.invoke.assert_called_once()


def test_clarification_followup_uses_history_and_pure_agent_scorer(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda message:
                        ("sentiment_analysis" if message == "Check the sentiment" else "out_of_scope", 1, 0.71))
    extraction = abstain(monkeypatch, "needs_clarification", "missing_source")
    assert post("Check the sentiment").json()["status"] == "needs_clarification"
    agent_model = Mock()
    agent_model.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "analyze_sentiment", "args": {"text": "I am not happy"}, "id": "call1"}],
                  response_metadata={"finish_reason": "tool_calls"}),
        response({"status": "completed", "reply": "Negative sentiment."}),
    ]
    monkeypatch.setattr(agent, "_create_model", lambda: agent_model)
    seen = []
    responses = iter(agent_model.invoke.side_effect)

    def invoke(messages):
        seen.append(list(messages))
        return next(responses)

    agent_model.invoke.side_effect = invoke
    result = post("I am not happy")
    assert result.status_code == 200 and result.json()["route"] == "agent"
    assert result.json()["trace"][0]["result"]["label"] == "negative"
    prior = json.loads(seen[0][-2].content)
    assert prior["status"] == "needs_clarification" and prior["reason"] == "missing_source"
    assert prior["workflow_trace"][0]["stage"] == "extract_source"
    extraction.invoke.assert_called_once()
    assert len(sessions._sessions["one"].history.messages) == 4


def test_http_extraction_failure_retains_failed_stage_and_never_hands_off(monkeypatch, sentiment_provider):
    model = sentiment_provider("fabricated source")
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = post("Just check the sentiment of this I am happy")
    data = result.json()
    assert result.status_code == 503 and data["status"] == "error"
    assert data["route"] == "llm_assisted" and data["reason"] == "extraction_failed"
    assert data["trace"] == [] and data["result"] is None
    assert data["workflow_trace"][0]["status"] == "failed"
    assert data["workflow_trace"][0]["reason"] == "non_verbatim_source"
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    assert saved["workflow_trace"] == data["workflow_trace"]
    assert saved["status"] == "error"
    handoff.assert_not_called()
    model.invoke.assert_called_once()


def test_faq_only_never_calls_sentiment_workflow(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, 0.71))
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_sentiment_workflow", workflow_call)
    result = client.post("/api/v1/faq", json={"message": "Check sentiment: happy"})
    assert result.status_code == 200
    assert result.json()["route"] == "agent" and result.json()["trace"] == []
    assert "workflow_trace" not in result.json()
    workflow_call.assert_not_called()
