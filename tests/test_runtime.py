from unittest.mock import Mock

import pytest

from app import runtime
from app.workflows import keyword_workflow, faq_workflow
from app.agent import AgentResult, AgentTrace
from app.routes import keyword_route, sentiment_route
from app.tools.faq import retrieve_faq
from app.tools.keywords import extract_keywords


CASES = [
    ("keyword_extraction", 'Extract keywords from "Customer support improves retention"', "extract_keywords",
     keyword_workflow, extract_keywords, {"text": "Customer support improves retention"}),
    ("faq_retrieval", 'FAQ: "What is the remote-work policy?"', "retrieve_faq",
     faq_workflow, retrieve_faq, {"question": "What is the remote-work policy?"}),
]


@pytest.fixture(autouse=True)
def agent_double(monkeypatch, sentiment_provider, keyword_provider, faq_provider):
    agent = Mock(return_value=AgentResult("needs_clarification", "Please provide details.", None, [], 0))
    monkeypatch.setattr(runtime, "run_agent", agent)
    return agent


@pytest.mark.parametrize(("intent", "message", "tool_name", "module", "function", "arguments"), CASES)
def test_dispatch_classifies_once_and_traces_exact_payload(intent, message, tool_name, module, function, arguments, monkeypatch, agent_double, keyword_provider, faq_provider):
    if intent == "keyword_extraction":
        keyword_provider(arguments["text"])
    else:
        faq_provider(arguments["question"])
    classifier = Mock(return_value=(intent, 0.71, 0.71))
    tool = Mock(wraps=function)
    monkeypatch.setattr(runtime, "classify_request", classifier)
    monkeypatch.setattr(module, tool_name, tool)
    execution = runtime.execute_request(message)
    classifier.assert_called_once_with(message)
    tool.assert_called_once_with(next(iter(arguments.values())))
    assert execution.status == "completed"
    assert execution.route == "llm_assisted"
    assert execution.predicted_intent == intent and execution.confidence == 0.71
    assert len(execution.trace) == 1
    step = execution.trace[0]
    assert step.tool == tool_name and step.arguments == arguments
    assert step.status == "completed" and step.result == execution.result
    assert execution.elapsed_ms >= step.elapsed_ms >= 0
    agent_double.assert_not_called()
    assert execution.reply
    assert execution.agent_reason is None


@pytest.mark.parametrize(("intent", "message", "confidence", "reason"), [
    ("reminder_creation", "Remind me tomorrow to check policy", 1, "intent_requires_agent"),
    ("compound_request", "Check sentiment and draft an email", 1, "intent_requires_agent"),
    ("summarization", "Summarize the previous message", 1, "intent_requires_agent"),
    ("email_drafting", "Draft an email", 1, "intent_requires_agent"),
    ("out_of_scope", "Hello", 1, "intent_requires_agent"),
    ("sentiment_analysis", 'Sentiment: "sad"', 0.70, "low_confidence"),
    ("keyword_extraction", 'Keywords: "sad" and email me', 1, "compound_request"),
    ("faq_retrieval", "What about that policy?", 1, "context_required"),
])
def test_fallback_hands_off_once_without_direct_execution(intent, message, confidence, reason, monkeypatch, agent_double):
    if intent == "keyword_extraction":
        import json
        from langchain_core.messages import AIMessage
        model = Mock()
        model.invoke.return_value = AIMessage(content=json.dumps({
            "status": "agent_required", "source_text": None, "reason": "compound_request",
        }), response_metadata={"finish_reason": "stop"})
        monkeypatch.setattr(keyword_workflow, "_create_model", lambda *args: model)
    elif intent == "faq_retrieval":
        import json
        from langchain_core.messages import AIMessage
        model = Mock()
        model.invoke.return_value = AIMessage(content=json.dumps({
            "status": "agent_required", "question": None, "reason": "context_required",
        }), response_metadata={"finish_reason": "stop"})
        monkeypatch.setattr(faq_workflow, "_create_model", lambda *args: model)
    classifier = Mock(return_value=(intent, confidence, 0.71))
    monkeypatch.setattr(runtime, "classify_request", classifier)
    tools = []
    for _, _, name, module, _, _ in CASES:
        tool = Mock()
        monkeypatch.setattr(module, name, tool)
        tools.append(tool)
    result = runtime.execute_request(message)
    assert result.status == "needs_clarification" and result.route == "agent"
    assert result.reason == reason and result.result is None and result.trace == []
    assert result.reply == "Please provide details." and result.agent_reason is None
    classifier.assert_called_once_with(message)
    agent_double.assert_called_once_with(message)
    for tool in tools:
        tool.assert_not_called()


@pytest.mark.parametrize(("intent", "message", "tool_name", "module", "function", "arguments"), CASES)
def test_tool_failure_has_failed_trace_without_exception_details(intent, message, tool_name, module, function, arguments, monkeypatch, agent_double, keyword_provider, faq_provider):
    if intent == "keyword_extraction":
        keyword_provider(arguments["text"])
    else:
        faq_provider(arguments["question"])
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=(intent, 1, 0.71)))
    tool = Mock(side_effect=RuntimeError("private payload and credentials"))
    monkeypatch.setattr(module, tool_name, tool)
    result = runtime.execute_request(message)
    assert result.status == "error" and result.result is None
    assert result.route == "llm_assisted"
    assert result.reason.endswith("_unavailable")
    step, = result.trace
    assert step.status == "failed" and step.result is None and step.arguments == arguments
    assert result.elapsed_ms >= step.elapsed_ms >= 0
    assert "private" not in repr(result)
    tool.assert_called_once_with(next(iter(arguments.values())))
    agent_double.assert_not_called()


def test_empty_keyword_result_is_success(monkeypatch, keyword_provider):
    keyword_provider("!!!")
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("keyword_extraction", 1, 0.71)))
    monkeypatch.setattr(keyword_workflow, "extract_keywords", Mock(return_value=[]))
    result = runtime.execute_request('Keywords: "!!!"')
    assert result.status == "completed" and result.result == []
    assert result.trace[0].status == "completed"


def test_faq_endpoint_scope_does_not_execute_sentiment(monkeypatch, agent_double):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("sentiment_analysis", 1, 0.71)))
    tool = Mock()
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", tool)
    result = runtime.execute_request('Sentiment: "sad"', faq_only=True)
    assert result.status == "agent_required" and result.reason == "intent_not_faq"
    assert result.trace == []
    tool.assert_not_called()
    agent_double.assert_not_called()


def test_classifier_failure_is_sanitized_and_prevents_dispatch(monkeypatch, agent_double):
    monkeypatch.setattr(runtime, "classify_request", Mock(side_effect=RuntimeError("private artifact path")))
    dispatch = Mock()
    monkeypatch.setattr(runtime, "try_direct_faq", dispatch)
    with pytest.raises(runtime.RuntimeUnavailable, match="^Intent classifier unavailable$"):
        runtime.execute_request("What is the remote-work policy?")
    dispatch.assert_not_called()
    agent_double.assert_not_called()


@pytest.mark.parametrize("faq_only", [False, True])
def test_routing_failure_is_sanitized_without_fabricated_trace(faq_only, monkeypatch, agent_double):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("faq_retrieval", 1, 0.71)))
    dispatch_name = "try_direct_faq" if faq_only else "run_faq_workflow"
    monkeypatch.setattr(runtime, dispatch_name, Mock(side_effect=RuntimeError("private FAQ path")))
    detail = "FAQ routing unavailable" if faq_only else "Execution routing unavailable"
    with pytest.raises(runtime.RuntimeUnavailable, match=f"^{detail}$"):
        runtime.execute_request("What is the remote-work policy?", faq_only=faq_only)
    agent_double.assert_not_called()


@pytest.mark.parametrize("message", [None, "", "   ", "a" * 10001])
def test_invalid_runtime_input_does_not_classify(message, monkeypatch, agent_double):
    classifier = Mock()
    monkeypatch.setattr(runtime, "classify_request", classifier)
    with pytest.raises((TypeError, ValueError)):
        runtime.execute_request(message)
    classifier.assert_not_called()
    agent_double.assert_not_called()


def test_saved_classifier_sentiment_execution(sentiment_provider):
    model = sentiment_provider("I am sad")
    result = runtime.execute_request('Analyze the sentiment of "I am sad"')
    assert result.status == "completed" and result.result.label == "negative"
    assert result.route == "llm_assisted" and model.invoke.call_count == 2
    assert result.trace[0].arguments == {"text": "I am sad"}


def test_saved_classifier_keyword_low_confidence_hands_off(monkeypatch, agent_double):
    tool = Mock()
    monkeypatch.setattr(keyword_route, "extract_keywords", tool)
    result = runtime.execute_request('Extract keywords from "Employee onboarding requires security training"')
    assert result.predicted_intent == "keyword_extraction"
    assert result.status == "needs_clarification" and result.reason == "low_confidence"
    assert result.trace == []
    tool.assert_not_called()
    agent_double.assert_called_once_with('Extract keywords from "Employee onboarding requires security training"')


@pytest.mark.parametrize(("status", "reason", "trace"), [
    ("completed", None, [AgentTrace("summarize_text", {"text": "Update"}, "completed",
                                   {"summary": "Update", "key_points": []}, None, 2)]),
    ("needs_clarification", None, []),
    ("error", "configuration", []),
    ("partial_failure", "timeout", [
        AgentTrace("retrieve_faq", {"question": "Leave?"}, "completed", {"status": "no_match"}, None, 1),
        AgentTrace("draft_email", {"recipient": "Alex", "content": "Update"}, "failed", None, "timeout", 2),
    ]),
])
def test_agent_outcomes_retained_with_total_timing(status, reason, trace, monkeypatch, agent_double):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("compound_request", 0.99, 0.71)))
    agent_double.return_value = AgentResult(status, "Reply with fixed draft actions", reason, trace, 500)
    monkeypatch.setattr(runtime, "perf_counter", Mock(side_effect=[10, 10.75]))
    result = runtime.execute_request("Find policy and draft to Alex")
    assert result.status == status and result.reply == agent_double.return_value.reply
    assert result.reason == "intent_requires_agent" and result.agent_reason == reason
    assert result.trace == trace and result.result is None
    assert result.predicted_intent == "compound_request" and result.confidence == 0.99
    assert result.elapsed_ms == 750


def test_unexpected_agent_exception_is_sanitized_without_invented_results(monkeypatch, agent_double):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("summarization", 1, 0.71)))
    agent_double.side_effect = RuntimeError("private credentials")
    result = runtime.execute_request("Summarize this update")
    assert result.status == "error" and result.agent_reason == "agent_unavailable"
    assert result.route == "agent" and result.trace == [] and result.result is None
    assert "private" not in repr(result)
    agent_double.assert_called_once_with("Summarize this update")


def test_runtime_invokes_real_agent_loop_with_offline_model(monkeypatch):
    import json
    from langchain_core.messages import AIMessage
    from app import agent

    monkeypatch.setattr(runtime, "run_agent", agent.run_agent)
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("sentiment_analysis", 0.5, 0.71)))
    responses = [AIMessage(content="", tool_calls=[{
        "name": "analyze_sentiment", "args": {"text": "I am happy"}, "id": "call1",
    }], response_metadata={"finish_reason": "tool_calls"}),
        AIMessage(content=json.dumps({"status": "completed", "reply": "Positive sentiment."}),
                  response_metadata={"finish_reason": "stop"})]
    model = Mock()
    model.invoke.side_effect = responses
    monkeypatch.setattr(agent, "_create_model", Mock(return_value=model))
    message = 'Analyze the sentiment of "I am happy"'
    result = runtime.execute_request(message)
    assert result.status == "completed" and result.route == "agent" and result.reason == "low_confidence"
    assert result.reply == "Positive sentiment." and result.trace[0].result["label"] == "positive"
    assert model.invoke.call_args_list[0].args[0][1].content == message
    assert result.elapsed_ms >= sum(step.elapsed_ms for step in result.trace)
