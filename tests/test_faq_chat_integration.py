"""FAQ workflow chat contracts; model doubles do not establish prose fidelity."""

import json
import socket
from unittest.mock import Mock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
import pytest

from app import agent, runtime, sessions, faq_workflow as workflow
from app.agent import AgentResult
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def offline(monkeypatch, faq_provider):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(sessions, "_sessions", {})
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected agent provider initialization"))


def response(payload):
    return AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "stop"})


def abstain(monkeypatch, status, reason):
    model = Mock()
    model.invoke.return_value = response({"status": status, "question": None, "reason": reason})
    monkeypatch.setattr(workflow, "_create_model", lambda *args: model)
    return model


def post(message):
    return client.post("/api/v1/chat", json={"session_id": "one", "message": message})


@pytest.mark.parametrize("message,question", [
    ("Please answer this FAQ: What is the remote-work policy?", "What is the remote-work policy?"),
    ('FAQ: "How do I request annual leave?"', "How do I request annual leave?"),
])
def test_classifier_first_at_threshold_with_exact_lookup_and_stages(monkeypatch, faq_provider, message, question):
    classifier = Mock(return_value=("faq_retrieval", 0.71, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    model = faq_provider(question)

    def create(*args):
        classifier.assert_called_once_with(message)
        return model

    monkeypatch.setattr(workflow, "_create_model", create)
    lookup = Mock(wraps=workflow.retrieve_faq)
    monkeypatch.setattr(workflow, "retrieve_faq", lookup)
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message)
    assert (result.route, result.status, result.reason) == ("llm_assisted", "completed", "faq_completed")
    assert result.reply and result.result.status == "matched"
    assert result.trace[0].arguments == {"question": question}
    assert result.trace[0].result is result.result
    assert result.trace[0].elapsed_ms == result.workflow_trace[1].elapsed_ms
    assert [stage.stage for stage in result.workflow_trace] == ["extract_question", "retrieve_faq", "explain_result"]
    assert result.elapsed_ms >= sum(stage.elapsed_ms for stage in result.workflow_trace)
    lookup.assert_called_once_with(question)
    assert model.invoke.call_count == 2
    handoff.assert_not_called()


@pytest.mark.parametrize("confidence,reason", [(0.70, "low_confidence"), (float("nan"), "invalid_confidence")])
def test_confidence_gate_preserves_agent_path_without_workflow(monkeypatch, confidence, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", confidence, 0.71))
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_faq_workflow", workflow_call)
    handoff = Mock(return_value=AgentResult("needs_clarification", "Which policy?", None, [], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request("What is the remote-work policy?")
    assert result.route == "agent" and result.reason == reason
    assert result.workflow_trace == []
    workflow_call.assert_not_called()
    handoff.assert_called_once_with("What is the remote-work policy?")


def test_invalid_threshold_prevents_workflow_and_agent(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0))
    workflow_call, handoff = Mock(), Mock()
    monkeypatch.setattr(runtime, "run_faq_workflow", workflow_call)
    monkeypatch.setattr(runtime, "run_agent", handoff)
    with pytest.raises(runtime.RuntimeUnavailable, match="Execution routing unavailable"):
        runtime.execute_request("What is the remote-work policy?")
    workflow_call.assert_not_called()
    handoff.assert_not_called()


@pytest.mark.parametrize("message,reason", [
    ("What about that policy?", "context_required"),
    ("Explain remote work and draft an email to Alex", "compound_request"),
])
def test_extraction_handoff_retains_stage_and_original_context_once(monkeypatch, message, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0.71))
    model = abstain(monkeypatch, "agent_required", reason)
    lookup = Mock()
    monkeypatch.setattr(workflow, "retrieve_faq", lookup)
    history = [HumanMessage(content="Earlier policy"), AIMessage(content="Earlier answer")]
    handoff = Mock(return_value=AgentResult("completed", "Agent reply", None, [], 0))
    monkeypatch.setattr(runtime, "run_agent", handoff)
    result = runtime.execute_request(message, history=history)
    assert result.route == "agent" and result.reason == reason
    assert result.reply == "Agent reply" and result.result is None
    assert len(result.workflow_trace) == 1 and result.workflow_trace[0].reason == reason
    handoff.assert_called_once_with(message, history=history)
    lookup.assert_not_called()
    model.invoke.assert_called_once()


@pytest.mark.parametrize("reason", ["missing_question", "ambiguous_question"])
def test_missing_question_http_clarification_is_saved_without_lookup(monkeypatch, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0.71))
    model = abstain(monkeypatch, "needs_clarification", reason)
    lookup, handoff = Mock(), Mock()
    monkeypatch.setattr(workflow, "retrieve_faq", lookup)
    monkeypatch.setattr(runtime, "run_agent", handoff)
    reply = post("Please answer a FAQ")
    data = reply.json()
    assert reply.status_code == 200 and data["route"] == "llm_assisted"
    assert data["status"] == "needs_clarification" and data["reason"] == reason
    assert data["trace"] == [] and data["result"] is None
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    assert saved["reply"] == data["reply"] and saved["workflow_trace"] == data["workflow_trace"]
    lookup.assert_not_called()
    handoff.assert_not_called()
    model.invoke.assert_called_once()


@pytest.mark.parametrize("question,raw_status", [
    ("How do I request leave?", "ambiguous"),
    ("What is the cafeteria policy?", "no_match"),
])
def test_unresolved_retrieval_clarifies_with_one_llm_call(monkeypatch, faq_provider, question, raw_status):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0.71))
    model = faq_provider(question)
    lookup = Mock(wraps=workflow.retrieve_faq)
    monkeypatch.setattr(workflow, "retrieve_faq", lookup)
    reply = post(question)
    data = reply.json()
    assert reply.status_code == 200 and data["status"] == "needs_clarification"
    assert data["result"]["status"] == raw_status and data["result"]["answer"] is None
    assert data["trace"][0]["result"] == data["result"]
    assert len(data["workflow_trace"]) == 2
    lookup.assert_called_once_with(question)
    model.invoke.assert_called_once()


def test_presenter_missing_detail_retains_matched_result_in_http_history(monkeypatch, faq_provider):
    question = "Can contractors work from home?"
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0.71))
    faq_provider(question, "The fictional demo policy does not specify contractor eligibility.", "needs_clarification")
    reply = post(question)
    data = reply.json()
    assert reply.status_code == 200 and data["status"] == "needs_clarification"
    assert data["reason"] == "policy_detail_missing" and data["result"]["status"] == "matched"
    assert data["result"]["policy_id"] == "REMOTE-01"
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    for field in ("result", "reply", "trace", "workflow_trace", "status"):
        assert saved[field] == data[field]


@pytest.mark.parametrize("failure", ["extraction", "retrieval", "presentation"])
def test_http_failures_retain_actual_records_without_retry_or_handoff(monkeypatch, faq_provider, failure):
    question = "What is the remote-work policy?"
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("faq_retrieval", 1, 0.71))
    model = faq_provider("invented question" if failure == "extraction" else question)
    lookup = Mock(wraps=workflow.retrieve_faq)
    monkeypatch.setattr(workflow, "retrieve_faq", lookup)
    if failure == "retrieval":
        lookup.side_effect = RuntimeError("private credentials")
    elif failure == "presentation":
        model.invoke.side_effect = [response({"status": "ready", "question": question, "reason": "explicit_question"}),
                                    RuntimeError("private credentials")]
    handoff = Mock()
    monkeypatch.setattr(runtime, "run_agent", handoff)
    reply = post(question)
    data = reply.json()
    assert reply.status_code == 503 and data["route"] == "llm_assisted"
    assert data["status"] == ("partial_failure" if failure == "presentation" else "error")
    assert len(data["workflow_trace"]) == {"extraction": 1, "retrieval": 2, "presentation": 3}[failure]
    if failure == "extraction":
        assert data["trace"] == [] and data["result"] is None
        lookup.assert_not_called()
    else:
        lookup.assert_called_once_with(question)
        assert data["trace"][0]["arguments"] == {"question": question}
        assert data["trace"][0]["result"] == data["result"]
        if failure == "presentation":
            assert data["result"]["status"] == "matched"
            assert data["reply"].endswith(data["result"]["answer"])
        else:
            assert data["trace"][0]["status"] == "failed"
    saved = json.loads(sessions._sessions["one"].history.messages[-1].content)
    for field in ("result", "reply", "trace", "workflow_trace", "status"):
        assert saved[field] == data[field]
    assert "private credentials" not in reply.text
    assert model.invoke.call_count == (2 if failure == "presentation" else 1)
    handoff.assert_not_called()


def test_faq_only_endpoint_preserves_direct_contract_without_workflow(monkeypatch):
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_faq_workflow", workflow_call)
    reply = client.post("/api/v1/faq", json={"message": "What is the remote-work policy?"})
    assert reply.status_code == 200
    assert reply.json()["route"] == "direct" and reply.json()["faq"]["status"] == "matched"
    assert "workflow_trace" not in reply.json()
    workflow_call.assert_not_called()


def test_saved_classifier_natural_question_http_success_retains_policy(faq_provider):
    model = faq_provider("What is the remote-work policy?")
    reply = post("Please answer this FAQ: What is the remote-work policy?")
    data = reply.json()
    assert reply.status_code == 200 and data["route"] == "llm_assisted"
    assert data["confidence"] >= 0.71 and data["result"]["policy_id"] == "REMOTE-01"
    assert data["trace"][0]["arguments"] == {"question": "What is the remote-work policy?"}
    assert model.invoke.call_count == 2


def test_reported_low_confidence_question_uses_pure_agent_lookup_with_draft_context(monkeypatch):
    message = "Please answer this FAQ: Can contractors work from home?"
    question = "Can contractors work from home?"
    reply = "The fictional demo policy does not specify contractor eligibility; please confirm it with HR."
    workflow_call = Mock()
    monkeypatch.setattr(runtime, "run_faq_workflow", workflow_call)
    responses = iter([
        response({"status": "needs_clarification", "reply": "Who is the email draft for?"}),
        AIMessage(content="", tool_calls=[{"name": "retrieve_faq", "args": {"question": question}, "id": "call1"}],
                  response_metadata={"finish_reason": "tool_calls"}),
        response({"status": "needs_clarification", "reply": reply}),
    ])
    seen = []

    def invoke(messages):
        seen.append(list(messages))
        return next(responses)

    model = Mock(invoke=Mock(side_effect=invoke))
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    assert post("Draft an email about maintenance").json()["status"] == "needs_clarification"
    result = post(message)
    data = result.json()
    assert result.status_code == 200 and data["route"] == "agent" and data["reason"] == "low_confidence"
    assert data["confidence"] < 0.71 and data["workflow_trace"] == []
    assert data["trace"][0]["tool"] == "retrieve_faq" and data["trace"][0]["result"]["policy_id"] == "REMOTE-01"
    assert reply in data["reply"] and "recipient" not in data["reply"]
    assert seen[1][-1].content == message
    assert json.loads(seen[1][-2].content)["reply"] == "Who is the email draft for?"
    assert model.invoke.call_count == 3
    workflow_call.assert_not_called()


def test_openapi_exposes_faq_workflow_stages():
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schema["FAQStage"]["properties"]["stage"]["enum"]) == {
        "extract_question", "retrieve_faq", "explain_result",
    }
    alternatives = schema["ChatResponse"]["properties"]["workflow_trace"]["items"]["anyOf"]
    assert "#/components/schemas/FAQStage" in {option["$ref"] for option in alternatives}
