from unittest.mock import Mock

import pytest

from app import runtime
from app.routes import faq_route, keyword_route, sentiment_route
from app.tools.faq import retrieve_faq
from app.tools.keywords import extract_keywords
from app.tools.sentiment import analyze_sentiment


CASES = [
    ("sentiment_analysis", 'Analyze the sentiment of "  I am sad  "', "analyze_sentiment",
     sentiment_route, analyze_sentiment, {"text": "  I am sad  "}),
    ("keyword_extraction", 'Extract keywords from "Customer support improves retention"', "extract_keywords",
     keyword_route, extract_keywords, {"text": "Customer support improves retention"}),
    ("faq_retrieval", 'FAQ: "What is the remote-work policy?"', "retrieve_faq",
     faq_route, retrieve_faq, {"question": "What is the remote-work policy?"}),
]


@pytest.mark.parametrize(("intent", "message", "tool_name", "module", "function", "arguments"), CASES)
def test_dispatch_classifies_once_and_traces_exact_payload(intent, message, tool_name, module, function, arguments, monkeypatch):
    classifier = Mock(return_value=(intent, 0.71, 0.71))
    tool = Mock(wraps=function)
    monkeypatch.setattr(runtime, "classify_request", classifier)
    monkeypatch.setattr(module, tool_name, tool)
    execution = runtime.execute_request(message)
    classifier.assert_called_once_with(message)
    tool.assert_called_once_with(next(iter(arguments.values())))
    assert execution.status == "completed" and execution.route == "direct"
    assert execution.predicted_intent == intent and execution.confidence == 0.71
    assert len(execution.trace) == 1
    step = execution.trace[0]
    assert step.tool == tool_name and step.arguments == arguments
    assert step.status == "completed" and step.result == execution.result
    assert execution.elapsed_ms >= step.elapsed_ms >= 0


@pytest.mark.parametrize(("intent", "message", "confidence", "reason"), [
    ("reminder_creation", "Remind me tomorrow to check policy", 1, "intent_requires_agent"),
    ("compound_request", "Check sentiment and draft an email", 1, "intent_requires_agent"),
    ("summarization", "Summarize the previous message", 1, "intent_requires_agent"),
    ("email_drafting", "Draft an email", 1, "intent_requires_agent"),
    ("out_of_scope", "Hello", 1, "intent_requires_agent"),
    ("sentiment_analysis", 'Sentiment: "sad"', 0.70, "low_confidence"),
    ("sentiment_analysis", "Analyze sentiment of the previous message", 1, "payload_not_unambiguous"),
    ("keyword_extraction", 'Keywords: "sad" and email me', 1, "payload_not_unambiguous"),
    ("faq_retrieval", "What about that policy?", 1, "question_not_unambiguous"),
])
def test_fallback_never_runs_any_tool(intent, message, confidence, reason, monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=(intent, confidence, 0.71)))
    tools = []
    for _, _, name, module, _, _ in CASES:
        tool = Mock()
        monkeypatch.setattr(module, name, tool)
        tools.append(tool)
    result = runtime.execute_request(message)
    assert result.status == "agent_required" and result.route == "agent"
    assert result.reason == reason and result.result is None and result.trace == []
    for tool in tools:
        tool.assert_not_called()


@pytest.mark.parametrize(("intent", "message", "tool_name", "module", "function", "arguments"), CASES)
def test_tool_failure_has_failed_trace_without_exception_details(intent, message, tool_name, module, function, arguments, monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=(intent, 1, 0.71)))
    tool = Mock(side_effect=RuntimeError("private payload and credentials"))
    monkeypatch.setattr(module, tool_name, tool)
    result = runtime.execute_request(message)
    assert result.status == "error" and result.route == "direct" and result.result is None
    assert result.reason.endswith("_unavailable")
    step, = result.trace
    assert step.status == "failed" and step.result is None and step.arguments == arguments
    assert result.elapsed_ms >= step.elapsed_ms >= 0
    assert "private" not in repr(result)
    tool.assert_called_once_with(next(iter(arguments.values())))


def test_empty_keyword_result_is_success(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("keyword_extraction", 1, 0.71)))
    monkeypatch.setattr(keyword_route, "extract_keywords", Mock(return_value=[]))
    result = runtime.execute_request('Keywords: "!!!"')
    assert result.status == "completed" and result.result == []
    assert result.trace[0].status == "completed"


def test_faq_endpoint_scope_does_not_execute_sentiment(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("sentiment_analysis", 1, 0.71)))
    tool = Mock()
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", tool)
    result = runtime.execute_request('Sentiment: "sad"', faq_only=True)
    assert result.status == "agent_required" and result.reason == "intent_not_faq"
    assert result.trace == []
    tool.assert_not_called()


def test_classifier_failure_is_sanitized_and_prevents_dispatch(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(side_effect=RuntimeError("private artifact path")))
    dispatch = Mock()
    monkeypatch.setattr(runtime, "try_direct_faq", dispatch)
    with pytest.raises(runtime.RuntimeUnavailable, match="^Intent classifier unavailable$"):
        runtime.execute_request("What is the remote-work policy?")
    dispatch.assert_not_called()


@pytest.mark.parametrize("faq_only", [False, True])
def test_routing_failure_is_sanitized_without_fabricated_trace(faq_only, monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(return_value=("faq_retrieval", 1, 0.71)))
    monkeypatch.setattr(runtime, "try_direct_faq", Mock(side_effect=RuntimeError("private FAQ path")))
    detail = "FAQ routing unavailable" if faq_only else "Execution routing unavailable"
    with pytest.raises(runtime.RuntimeUnavailable, match=f"^{detail}$"):
        runtime.execute_request("What is the remote-work policy?", faq_only=faq_only)


@pytest.mark.parametrize("message", [None, "", "   ", "a" * 10001])
def test_invalid_runtime_input_does_not_classify(message, monkeypatch):
    classifier = Mock()
    monkeypatch.setattr(runtime, "classify_request", classifier)
    with pytest.raises((TypeError, ValueError)):
        runtime.execute_request(message)
    classifier.assert_not_called()


def test_saved_classifier_sentiment_execution():
    result = runtime.execute_request('Analyze the sentiment of "I am sad"')
    assert result.status == "completed" and result.result.label == "negative"
    assert result.trace[0].arguments == {"text": "I am sad"}


def test_saved_classifier_keyword_low_confidence_defers(monkeypatch):
    tool = Mock()
    monkeypatch.setattr(keyword_route, "extract_keywords", tool)
    result = runtime.execute_request('Extract keywords from "Employee onboarding requires security training"')
    assert result.predicted_intent == "keyword_extraction"
    assert result.status == "agent_required" and result.reason == "low_confidence"
    assert result.trace == []
    tool.assert_not_called()
