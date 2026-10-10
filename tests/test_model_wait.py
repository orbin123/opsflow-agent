import json
from unittest.mock import Mock

import httpx
import pytest
from groq import RateLimitError, APITimeoutError
from langchain_core.messages import AIMessage

from app.core import agent, model_wait
from app.core.execution_events import EventEmitter, observe_events
from app.tools import summarization, email_drafting


def limited(header="19"):
    headers = {} if header is None else {"retry-after": header}
    return RateLimitError("private provider text", response=httpx.Response(
        429, headers=headers, request=httpx.Request("POST", "https://example.test")), body=None)


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    delays = []
    monkeypatch.setattr(model_wait, "perf_counter", lambda: now[0])
    def wait(delay):
        delays.append(delay)
        now[0] += delay
    monkeypatch.setattr(model_wait, "sleep", wait)
    return now, delays


def test_rejected_request_waits_once_with_safe_correlated_events(clock):
    model = Mock()
    messages = ["private source"]
    model.invoke.side_effect = [limited(), "answer"]
    events = []
    with observe_events(EventEmitter("chat", "turn", events.append)), model_wait.rate_limit_wait(120):
        assert model_wait.invoke_model(model, messages) == "answer"
    assert clock[1] == [20]
    assert [call.args[0] for call in model.invoke.call_args_list] == [messages, messages]
    assert events[0]["name"] == "Model busy — waiting 20 seconds"
    assert events[1]["step_id"] == events[0]["sequence"]
    assert events[1]["elapsed_ms"] == 20000
    assert "private" not in json.dumps(events)


@pytest.mark.parametrize("header,deadline", [
    (None, 120), ("invalid", 120), ("nan", 120), ("inf", 120),
    ("-1", 120), ("60", 120), ("19", 20),
])
def test_unsafe_or_over_budget_wait_does_not_retry(clock, header, deadline):
    model = Mock()
    model.invoke.side_effect = limited(header)
    with model_wait.rate_limit_wait(deadline), pytest.raises(RateLimitError):
        model_wait.invoke_model(model, [])
    model.invoke.assert_called_once()
    assert clock[1] == []


def test_repeated_limit_stops_and_context_does_not_leak(clock):
    model = Mock()
    model.invoke.side_effect = limited("0")
    with model_wait.rate_limit_wait(120), pytest.raises(RateLimitError):
        model_wait.invoke_model(model, [])
    assert model.invoke.call_count == 2 and clock[1] == [1]
    with pytest.raises(RateLimitError):
        model_wait.invoke_model(model, [])
    assert model.invoke.call_count == 3 and clock[1] == [1]


def test_timeout_is_never_retried(clock):
    model = Mock()
    model.invoke.side_effect = APITimeoutError(request=httpx.Request("POST", "https://example.test"))
    with model_wait.rate_limit_wait(120), pytest.raises(APITimeoutError):
        model_wait.invoke_model(model, [])
    model.invoke.assert_called_once()
    assert clock[1] == []


def test_delayed_wakeup_cannot_retry_past_deadline(clock, monkeypatch):
    model = Mock()
    model.invoke.side_effect = limited("1")
    monkeypatch.setattr(model_wait, "sleep", lambda delay: clock[0].__setitem__(0, 120))
    with model_wait.rate_limit_wait(120), pytest.raises(RateLimitError):
        model_wait.invoke_model(model, [])
    model.invoke.assert_called_once()


def test_four_tool_chat_waits_without_reexecuting_completed_tools(clock, monkeypatch):
    source = "The service failed twice today and I am frustrated."
    def call(name, args, ident):
        return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": ident}],
                         response_metadata={"finish_reason": "tool_calls"})
    model = Mock()
    model.invoke.side_effect = [
        call("analyze_sentiment", {"text": source}, "1"),
        call("extract_keywords", {"text": source}, "2"), limited("19"),
        call("summarize_text", {"text": source}, "3"),
        call("draft_email", {"recipient": "Alex", "content": source}, "4"),
        AIMessage(content='{"status":"completed","reply":"Done"}',
                  response_metadata={"finish_reason": "stop"}),
    ]
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    monkeypatch.setattr(agent, "perf_counter", lambda: clock[0][0])
    summary_model = Mock()
    summary_model.invoke.side_effect = [limited("1"), AIMessage(
        content=json.dumps({"summary": source, "key_points": []}),
        response_metadata={"finish_reason": "stop"})]
    draft_model = Mock()
    draft_model.invoke.side_effect = [limited("2"), AIMessage(
        content=json.dumps({"subject": "Service complaint", "body": source}),
        response_metadata={"finish_reason": "stop"})]
    monkeypatch.setattr(summarization, "_create_model", lambda: summary_model)
    monkeypatch.setattr(email_drafting, "_create_model", lambda: draft_model)
    attempts = {}
    for name, (schema, tool, description) in agent._TOOLS.items():
        def counted(_tool=tool, _name=name, **arguments):
            attempts[_name] = attempts.get(_name, 0) + 1
            return _tool(**arguments)
        monkeypatch.setitem(agent._TOOLS, name, (schema, counted, description))
    result = agent.run_agent("Analyze sentiment, extract keywords, summarize and draft to Alex: " + source)
    assert result.status == "completed"
    assert attempts == {"analyze_sentiment": 1, "extract_keywords": 1, "summarize_text": 1, "draft_email": 1}
    assert len(result.trace) == 4 and all(step.status == "completed" for step in result.trace)
    assert clock[1] == [20, 2, 3]
    assert source in result.reply and "Intended recipient: Alex" in result.reply
    assert model.invoke.call_count == 6
