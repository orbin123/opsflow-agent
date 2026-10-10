"""Verify classifier-first workflow dispatch and retained chat/history outcomes."""

import json
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
import pytest

from app.core import agent, runtime
from app.chat import sessions
from app.workflows import keyword_workflow as workflow
from app.core.agent import AgentResult, AgentTrace
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def offline(monkeypatch, keyword_provider):
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
    ("Find keywords in this The server failed after the deployment", "The server failed after the deployment"),
    ('Extract keywords from "  I am sad  "', "  I am sad  "),
    ("Find keywords in this I am NOT happy!\nThe service was poor.",
     "I am NOT happy!\nThe service was poor."),
])
def test_classifier_runs_first_and_workflow_executes_once_at_threshold(monkeypatch, keyword_provider, message, source):
    classifier = Mock(return_value=("keyword_extraction", 0.71, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    model = keyword_provider(source)

    def create(*args):
        classifier.assert_called_once_with(message)
        return model

    monkeypatch.setattr(workflow, "_create_model", create)
    extractor = Mock(wraps=workflow.extract_keywords)
    monkeypatch.setattr(workflow, "extract_keywords", extractor)
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message)
    assert result.route == "llm_assisted" and result.status == "completed"
    assert result.reason == "keyword_completed" and result.reply
    assert result.agent_reason is None
    assert result.trace[0].arguments == {"text": source}
    assert result.trace[0].result == result.result
    assert result.trace[0].elapsed_ms == result.workflow_trace[1].elapsed_ms
    assert result.elapsed_ms >= sum(stage.elapsed_ms for stage in result.workflow_trace)
    extractor.assert_called_once_with(source)
    assert model.invoke.call_count == 2
    handoff.assert_not_called()


@pytest.mark.parametrize("confidence,reason", [(0.70, "low_confidence"), (float("nan"), "invalid_confidence")])
def test_confidence_gate_never_starts_workflow(monkeypatch, confidence, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", confidence, 0.71))
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_keyword_workflow", workflow_call)
    handoff = Mock(return_value=AgentResult("needs_clarification", "Which text?", None, [], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request("Keywords: happy")
    assert result.route == "agent" and result.reason == reason
    assert result.workflow_trace == []
    workflow_call.assert_not_called()
    handoff.assert_called_once_with("Keywords: happy")


def test_invalid_threshold_stops_before_any_provider_call(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0))
    workflow_call, handoff = Mock(), Mock()
    monkeypatch.setattr(runtime, "run_keyword_workflow", workflow_call)
    monkeypatch.setattr(runtime, "run_agent", handoff)
    with pytest.raises(runtime.RuntimeUnavailable, match="Execution routing unavailable"):
        runtime.execute_request("Keywords: happy")
    workflow_call.assert_not_called()
    handoff.assert_not_called()


@pytest.mark.parametrize("message,reason", [
    ("Extract keywords from that message", "context_required"),
    ("Extract keywords and summarize this I am sad", "compound_request"),
    ("Send me an email", "unsupported_request"),
])
def test_extraction_abstention_hands_off_original_request_and_history_once(monkeypatch, message, reason):
    # Force a confident misclassification to check the second gate, independent
    # of the saved classifier's prediction for these examples.
    classifier = Mock(return_value=("keyword_extraction", 1, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    model = abstain(monkeypatch, "agent_required", reason)
    extractor = Mock()
    monkeypatch.setattr(workflow, "extract_keywords", extractor)
    history = [HumanMessage(content="Earlier source"), AIMessage(content="Earlier result")]
    observation = AgentTrace("extract_keywords", {"text": "Earlier source"}, "completed",
                             {"label": "neutral"}, None, 0)
    handoff = Mock(return_value=AgentResult("completed", "Agent reply", None, [observation], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message, history=history)
    assert result.route == "agent" and result.reason == reason and result.reply == "Agent reply"
    assert result.result is None and result.trace == [observation]
    assert len(result.workflow_trace) == 1 and result.workflow_trace[0].reason == reason
    classifier.assert_called_once_with(message)
    handoff.assert_called_once_with(message, history=history)
    extractor.assert_not_called()
    model.invoke.assert_called_once()


@pytest.mark.parametrize("reason", ["missing_source", "ambiguous_source"])
def test_http_clarification_is_saved_without_tool_or_agent_execution(monkeypatch, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0.71))
    model = abstain(monkeypatch, "needs_clarification", reason)
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = post("Extract keywords")
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


def test_clarification_followup_uses_history_and_pure_agent_tool(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda message:
                        ("keyword_extraction" if message == "Extract keywords" else "out_of_scope", 1, 0.71))
    extraction = abstain(monkeypatch, "needs_clarification", "missing_source")
    assert post("Extract keywords").json()["status"] == "needs_clarification"
    agent_model = Mock()
    agent_model.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "extract_keywords", "args": {"text": "I am not happy"}, "id": "call1"}],
                  response_metadata={"finish_reason": "tool_calls"}),
        response({"status": "completed", "reply": "YAKE returned keywords for the supplied text."}),
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
    assert result.json()["trace"][0]["tool"] == "extract_keywords"
    assert isinstance(result.json()["trace"][0]["result"], list)
    prior = json.loads(seen[0][-2].content)
    assert prior["status"] == "needs_clarification" and prior["reason"] == "missing_source"
    assert prior["workflow_trace"][0]["stage"] == "extract_source"
    extraction.invoke.assert_called_once()
    assert len(sessions._sessions["one"].history.messages) == 4


def test_http_extraction_failure_retains_failed_stage_and_never_hands_off(monkeypatch, keyword_provider):
    model = keyword_provider("fabricated source")
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = post("Find keywords in this The server failed after the deployment")
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


def test_faq_only_never_calls_keyword_workflow(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0.71))
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_keyword_workflow", workflow_call)
    result = client.post("/api/v1/faq", json={"message": "Keywords: happy"})
    assert result.status_code == 200
    assert result.json()["route"] == "agent" and result.json()["trace"] == []
    assert "workflow_trace" not in result.json()
    workflow_call.assert_not_called()


@pytest.mark.parametrize("failure,source", [
    ("tool", "The server failed"),
    ("presentation", "The server failed"),
    ("presentation", "!!!"),
])
def test_http_failures_preserve_actual_tool_result_and_history(monkeypatch, keyword_provider, failure, source):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0.71))
    model = keyword_provider(source)
    extractor = Mock(wraps=workflow.extract_keywords)
    monkeypatch.setattr(workflow, "extract_keywords", extractor)
    if failure == "tool":
        extractor.side_effect = RuntimeError("private credentials")
    else:
        extraction = response({"status": "ready", "source_text": source, "reason": "explicit_source"})
        model.invoke.side_effect = [extraction, RuntimeError("private credentials")]
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = post("Find keywords: " + source)
    data = result.json()
    assert result.status_code == 503 and data["route"] == "llm_assisted"
    assert data["status"] == ("error" if failure == "tool" else "partial_failure")
    assert data["reason"] == ("keyword_unavailable" if failure == "tool" else "presentation_failed")
    assert data["trace"][0]["arguments"] == {"text": source}
    assert data["trace"][0]["status"] == ("failed" if failure == "tool" else "completed")
    assert data["trace"][0]["result"] == data["result"]
    if failure == "tool":
        assert data["result"] is None and len(data["workflow_trace"]) == 2
    else:
        assert data["result"] is not None and len(data["workflow_trace"]) == 3
        assert "introduction is unavailable" in data["reply"]
        if source == "!!!":
            assert data["result"] == [] and "no keyword candidates" in data["reply"]
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    for field in ("result", "reply", "trace", "workflow_trace", "status"):
        assert saved[field] == data[field]
    assert "private credentials" not in result.text
    extractor.assert_called_once_with(source)
    assert model.invoke.call_count == (1 if failure == "tool" else 2)
    handoff.assert_not_called()


def test_saved_classifier_langchain_example_uses_fixed_workflow(keyword_provider):
    source = ("Langchain is a framework that helps developers build applications with language "
              "models including chat bots and question answering systems.")
    model = keyword_provider(source, "YAKE keywords include question answering systems.")
    result = post('Extract the keywords from this text: "' + source + '"')
    data = result.json()
    assert result.status_code == 200 and data["route"] == "llm_assisted"
    assert data["predicted_intent"] == "keyword_extraction" and data["confidence"] >= 0.71
    assert data["trace"][0]["arguments"] == {"text": source}
    assert data["result"][0]["phrase"] == "question answering systems"
    assert data["reply"] == "YAKE keywords include question answering systems."
    assert [stage["stage"] for stage in data["workflow_trace"]] == [
        "extract_source", "extract_keywords", "explain_result",
    ]
    assert model.invoke.call_count == 2


def test_openapi_allows_keyword_tool_stage():
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert "extract_keywords" in schema["KeywordStage"]["properties"]["stage"]["enum"]
    alternatives = schema["ChatResponse"]["properties"]["workflow_trace"]["items"]["anyOf"]
    assert {option["$ref"] for option in alternatives} == {
        "#/components/schemas/SentimentStage", "#/components/schemas/KeywordStage",
        "#/components/schemas/FAQStage",
    }
