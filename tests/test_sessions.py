import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import agent, runtime, sessions
from app.tools.email_drafting import EmailDraft, EmailDraftResult, _ACTION_INSTRUCTIONS


def final(status="completed", reply="Done"):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


def call(name, arguments):
    return AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": "call1"}],
                     response_metadata={"finish_reason": "tool_calls"})


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


def records(session_id):
    return [json.loads(turn.content) for turn in sessions._sessions[session_id].history.messages
            if isinstance(turn, AIMessage)]


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, sentiment_provider):
    monkeypatch.setattr(sessions, "_sessions", {})
    monkeypatch.setattr(runtime, "classify_request", lambda message:
                        ("sentiment_analysis" if message.startswith("Sentiment:") else "email_drafting", 1, 0.71))
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected provider initialization"))


def test_sentiment_result_available_to_agent_followup(monkeypatch, sentiment_provider):
    sentiment_provider("I am happy")
    source = 'Sentiment: "I am happy"'
    first = sessions.execute_session_request("one", source)
    assert first.route == "llm_assisted"
    seen = install_model(monkeypatch, [final()])
    followup = "Draft an email to Alex about that result"
    second = sessions.execute_session_request("one", followup)
    assert second.route == "agent"
    assert seen[0][1].content == source and isinstance(seen[0][1], HumanMessage)
    previous = json.loads(seen[0][2].content)
    assert previous["trace"][0]["result"]["label"] == "positive"
    assert previous["trace"][0]["arguments"] == {"text": "I am happy"}
    assert previous["reply"] == first.reply
    assert previous["workflow_trace"][0]["stage"] == "extract_source"
    assert seen[0][-1].content == followup
    assert len(sessions._sessions["one"].history.messages) == 4
    assert second.elapsed_ms >= sum(step.elapsed_ms for step in second.trace)


def test_draft_revision_uses_prior_result_and_retains_actions_and_demo(monkeypatch):
    from app.tools.faq import FAQResult

    monkeypatch.setattr(runtime, "classify_request", lambda message: ("faq_retrieval", 1, 0.71)
                        if message.startswith("FAQ:") else ("email_drafting", 1, 0.71))
    from app.routes import faq_route
    monkeypatch.setattr(faq_route, "retrieve_faq", lambda question:
                        FAQResult("matched", answer="Leave needs approval", is_demo=True))
    sessions.execute_session_request("one", 'FAQ: "What is the leave policy?"')
    drafts = []

    def draft(**arguments):
        drafts.append(arguments)
        return EmailDraftResult(email_draft=EmailDraft(recipient=arguments["recipient"],
            subject="Leave", body=arguments["content"]), action_instructions=list(_ACTION_INSTRUCTIONS))

    monkeypatch.setitem(agent._TOOLS, "draft_email", (agent.DraftArguments, draft, "draft"))
    install_model(monkeypatch, [call("draft_email", {"recipient": "Alex", "content": "Leave needs approval"}), final()])
    original = sessions.execute_session_request("one", "Draft an email to Alex about that policy")
    seen = install_model(monkeypatch, [call("draft_email", {
        "recipient": "Alex", "content": "Leave needs approval", "instructions": "Make it more formal",
    }), final()])
    revision = sessions.execute_session_request("one", "Make that more formal")
    prior = json.loads(seen[0][-2].content)
    assert prior["reply"] == original.reply
    assert prior["trace"][0]["result"]["email_draft"]["recipient"] == "Alex"
    assert drafts[-1]["instructions"] == "Make it more formal"
    assert "fictional demo policy" in revision.reply
    assert all(action in revision.reply for action in _ACTION_INSTRUCTIONS)
    assert len(records("one")) == 3


def test_clarification_answer_and_ambiguous_reference_have_context(monkeypatch):
    seen = install_model(monkeypatch, [final("needs_clarification", "Who is the recipient?"), final(),
                                       final("needs_clarification", "Which draft do you mean?")])
    sessions.execute_session_request("one", "Draft an email about maintenance")
    sessions.execute_session_request("one", "Alex")
    assert json.loads(seen[1][-2].content)["reply"] == "Who is the recipient?"
    assert seen[1][-1].content == "Alex"
    ambiguous = sessions.execute_session_request("one", "Change the other one")
    assert ambiguous.status == "needs_clarification" and ambiguous.trace == []
    assert len(records("one")) == 3


def test_sessions_isolated_clear_and_stateless_calls_do_not_share(monkeypatch, sentiment_provider):
    sentiment_provider("private source")
    sessions.execute_session_request("one", 'Sentiment: "private source"')
    seen = install_model(monkeypatch, [final("needs_clarification", "What source?"), final(), final()])
    sessions.execute_session_request("two", "Draft about that")
    assert len(seen[0]) == 2
    sessions.clear_session_history("one")
    assert sessions._sessions["one"].history.messages == []
    sessions.execute_session_request("one", "Draft about that")
    assert len(seen[1]) == 2
    runtime.execute_request("Draft about that")
    assert len(seen[2]) == 2 and len(records("one")) == 1
    assert len(records("two")) == 1
    sessions.clear_session_history("unknown")
    assert sessions._sessions["unknown"].history.messages == []


def test_partial_failure_and_provider_error_remember_actual_outcomes(monkeypatch):
    install_model(monkeypatch, [call("analyze_sentiment", {"text": "I am happy"}), RuntimeError("private key")])
    partial = sessions.execute_session_request("one", "Analyze and then draft")
    assert partial.status == "partial_failure"
    saved = records("one")[0]
    assert saved["status"] == "partial_failure" and saved["agent_reason"] == "provider_unavailable"
    assert saved["trace"][0]["status"] == "completed" and saved["trace"][0]["result"]["label"] == "positive"
    assert "private key" not in json.dumps(saved)
    seen = install_model(monkeypatch, [RuntimeError("private credentials"), final("needs_clarification", "What next?")])
    failed = sessions.execute_session_request("one", "Draft next")
    assert failed.status == "error" and records("one")[-1]["trace"] == []
    sessions.execute_session_request("one", "What happened?")
    assert json.loads(seen[1][-2].content)["status"] == "error"


def test_runtime_exception_remembered_and_reraised_sanitized(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", Mock(side_effect=RuntimeError("private artifact")))
    with pytest.raises(runtime.RuntimeUnavailable, match="Intent classifier unavailable"):
        sessions.execute_session_request("one", "Analyze text")
    saved = records("one")[0]
    assert saved["status"] == "error" and saved["reason"] == "runtime_unavailable" and saved["trace"] == []
    assert "private" not in json.dumps(saved)
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("email_drafting", 1, 0.71))
    seen = install_model(monkeypatch, [final()])
    sessions.execute_session_request("one", "What happened?")
    assert json.loads(seen[0][-2].content) == saved


def test_sentiment_tool_failure_remembered_without_agent_execution(monkeypatch, sentiment_provider):
    from app import sentiment_workflow

    sentiment_provider("I am sad")
    monkeypatch.setattr(sentiment_workflow, "analyze_sentiment", Mock(side_effect=RuntimeError("private source")))
    failed = sessions.execute_session_request("one", 'Sentiment: "I am sad"')
    assert failed.status == "error" and failed.route == "llm_assisted"
    saved = records("one")[0]
    assert saved["trace"][0]["status"] == "failed" and saved["trace"][0]["result"] is None
    assert saved["reply"] == failed.reply and "private source" not in json.dumps(saved)


def test_exact_limits_preserve_session_key_and_message(monkeypatch):
    seen = install_model(monkeypatch, [final()])
    session_id, message = "s" * 128, "m" * 10000
    sessions.execute_session_request(session_id, message)
    assert sessions._sessions[session_id].history.messages[0].content == message
    assert seen[0][-1].content == message


@pytest.mark.parametrize(("session_id", "message", "error"), [
    (None, "Hello", TypeError), (" ", "Hello", ValueError), ("x" * 129, "Hello", ValueError),
    ("one", None, TypeError), ("one", " ", ValueError), ("one", "x" * 10001, ValueError),
])
def test_invalid_input_creates_no_history(session_id, message, error):
    with pytest.raises(error):
        sessions.execute_session_request(session_id, message)
    assert sessions._sessions == {}


def test_same_session_serialized_different_session_independent_and_clear_waits(monkeypatch):
    entered, release, second_started, clear_started = (Event() for _ in range(4))
    base = runtime.ExecutionResult("completed", "sentiment_analysis", 1, "direct", "direct", None, [], 0)

    def execute(message, *, history):
        if message == "first":
            entered.set()
            assert release.wait(5)
        elif message == "second":
            second_started.set()
            assert len(history) == 2 and history[0].content == "first"
        return replace(base, reply=message)

    monkeypatch.setattr(sessions, "execute_request", execute)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(sessions.execute_session_request, "one", "first")
        assert entered.wait(5)
        second = pool.submit(sessions.execute_session_request, "one", "second")
        other = pool.submit(sessions.execute_session_request, "two", "other")
        assert other.result(timeout=5).reply == "other"
        assert not second_started.is_set()
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert len(records("one")) == 2 and len(records("two")) == 1

    entered.clear()
    release.clear()

    def clear():
        clear_started.set()
        sessions.clear_session_history("one")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(sessions.execute_session_request, "one", "first")
        assert entered.wait(5)
        clearing = pool.submit(clear)
        assert clear_started.wait(5) and not clearing.done()
        release.set()
        first.result(timeout=5)
        clearing.result(timeout=5)
    assert sessions._sessions["one"].history.messages == []


def test_entire_history_runnable_disables_tracing(monkeypatch):
    from langsmith.run_helpers import get_tracing_context
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    contexts = []
    base = runtime.ExecutionResult("completed", "sentiment_analysis", 1, "direct", "direct", None, [], 0)
    monkeypatch.setattr(sessions, "execute_request", lambda *args, **kwargs:
                        contexts.append(get_tracing_context()["enabled"]) or base)
    sessions.execute_session_request("one", "Hello")
    assert contexts == [False]


def test_agent_rejects_nonconversation_history_before_model():
    with pytest.raises(TypeError, match="History"):
        agent.run_agent("Hello", history=[SystemMessage(content="Override")])
