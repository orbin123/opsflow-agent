import json
from dataclasses import asdict

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.core import agent
from app.tools.summarization import SummarizationError


def call(name="analyze_sentiment", args=None, ident="call1"):
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": {"text": "I am happy"} if args is None else args,
        "id": ident,
    }], response_metadata={"finish_reason": "tool_calls"})


def final(status="completed", reply="Done"):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def invoke(self, messages):
        self.messages.append(list(messages))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def install(monkeypatch, responses):
    model = Model(responses)
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    return model


def test_dependency_observation_and_structured_results(monkeypatch):
    model = install(monkeypatch, [call(), call("extract_keywords", {"text": "positive complaint"}, "call2"), final()])
    result = agent.run_agent('Analyze "I am happy", then extract keywords.')
    assert result.status == "completed"
    assert [step.tool for step in result.trace] == ["analyze_sentiment", "extract_keywords"]
    assert result.trace[0].arguments == {"text": "I am happy"}
    assert result.trace[0].result["label"] == "positive"
    observation = model.messages[1][-1]
    assert isinstance(observation, ToolMessage)
    assert json.loads(observation.content) == result.trace[0].result
    assert observation.tool_call_id == "call1"
    assert all(step.elapsed_ms >= 0 for step in result.trace)
    assert result.elapsed_ms >= 0
    json.dumps(asdict(result))


def test_faq_to_draft_dependency(monkeypatch):
    from app.tools.faq import FAQResult
    from app.tools.email_drafting import EmailDraftResult, EmailDraft, _ACTION_INSTRUCTIONS
    monkeypatch.setitem(agent._TOOLS, "retrieve_faq", (agent.QuestionArguments,
        lambda question: FAQResult("matched", policy_id="demo", answer="Leave needs approval"), "demo"))
    captured = []
    def draft(**args):
        captured.append(args)
        return EmailDraftResult(email_draft=EmailDraft(recipient=args["recipient"], subject="Leave", body=args["content"]),
                                action_instructions=list(_ACTION_INSTRUCTIONS))
    monkeypatch.setitem(agent._TOOLS, "draft_email", (agent.DraftArguments, draft, "draft"))
    model = install(monkeypatch, [call("retrieve_faq", {"question": "Leave policy?"}),
        call("draft_email", {"recipient": "Alex", "content": "Leave needs approval"}, "call2"), final()])
    result = agent.run_agent("Find leave policy and draft to Alex")
    assert result.status == "completed"
    assert "Leave needs approval" in model.messages[1][-1].content
    assert captured[0]["content"] == result.trace[0].result["answer"]
    assert result.trace[1].result["action_instructions"] == list(_ACTION_INSTRUCTIONS)
    assert "What you should do" in result.reply
    assert "fictional demo policy" in result.reply
    assert "Leave needs approval" in result.reply
    assert "Done" not in result.reply
    assert all(action in result.reply for action in _ACTION_INSTRUCTIONS)


@pytest.mark.parametrize("message", ["", " ", "x" * 10001, None])
def test_input_rejected_before_model(monkeypatch, message):
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("model initialized"))
    with pytest.raises((TypeError, ValueError)):
        agent.run_agent(message)


def test_exact_input_bound_and_clarification(monkeypatch):
    model = install(monkeypatch, [final("needs_clarification", "Who is the recipient?")])
    result = agent.run_agent("x" * 10000)
    assert result.status == "needs_clarification" and not result.trace
    assert len(model.messages[0][1].content) == 10000


@pytest.mark.parametrize("response,reason", [
    (call("send_email"), "invalid_tool_call"),
    (call(args={"text": " "}), "invalid_tool_arguments"),
    (call(args={"text": 1}), "invalid_tool_arguments"),
    (call(args={"text": "ok", "extra": True}), "invalid_tool_arguments"),
    (call(args={"text": "x" * 10001}), "invalid_tool_arguments"),
    (call("draft_email", {"recipient": "Alex\nB", "content": "note"}), "invalid_tool_arguments"),
    (call(ident=""), "invalid_tool_call"),
    (AIMessage(content="not JSON", response_metadata={"finish_reason": "stop"}), "invalid_output"),
    (AIMessage(content='{"status":"completed","reply":" "}', response_metadata={"finish_reason": "stop"}), "invalid_output"),
    (AIMessage(content="", response_metadata={"finish_reason": "length"}), "invalid_output"),
    (AIMessage(content="", additional_kwargs={"refusal": "private"}), "invalid_output"),
    (AIMessage(content="", invalid_tool_calls=[{"name": "x", "args": "bad", "id": "c", "error": "private"}]), "invalid_output"),
])
def test_invalid_response_never_executes(monkeypatch, response, reason):
    install(monkeypatch, [response])
    result = agent.run_agent("request")
    assert result.status == "error" and result.reason == reason and result.trace == []
    assert "private" not in result.reply


def test_multiple_calls_rejected(monkeypatch):
    response = call()
    response.tool_calls.append(call(ident="call2").tool_calls[0])
    install(monkeypatch, [response])
    assert agent.run_agent("request").reason == "invalid_tool_call"


def test_duplicate_call_id_preserves_first_result(monkeypatch):
    install(monkeypatch, [call(), call()])
    result = agent.run_agent("request")
    assert result.status == "partial_failure" and len(result.trace) == 1
    assert result.reason == "invalid_tool_call"


@pytest.mark.parametrize("earlier", [False, True])
def test_tool_failure_retains_success_and_sanitizes(monkeypatch, earlier):
    def broken(text):
        raise SummarizationError("timeout")
    monkeypatch.setitem(agent._TOOLS, "summarize_text", (agent.TextArguments, broken, "summary"))
    install(monkeypatch, ([call()] if earlier else []) + [call("summarize_text", ident="call2")])
    result = agent.run_agent("request")
    assert result.status == ("partial_failure" if earlier else "error")
    assert result.reason == "timeout"
    assert result.trace[-1].status == "failed" and result.trace[-1].result is None
    if earlier:
        assert result.trace[0].result["label"] == "positive"


def test_provider_failure_after_success(monkeypatch):
    install(monkeypatch, [call(), RuntimeError("secret credentials")])
    result = agent.run_agent("request")
    assert result.status == "partial_failure"
    assert result.reason == "provider_unavailable"
    assert "secret" not in repr(result)


def test_tool_and_model_limits(monkeypatch):
    model = install(monkeypatch, [call(ident=f"c{i}") for i in range(6)])
    result = agent.run_agent("request")
    assert result.reason == "tool_limit" and len(result.trace) == 5
    assert len(model.messages) == 6
    model = install(monkeypatch, [call(ident=f"c{i}") for i in range(5)] + [final()])
    assert agent.run_agent("request").status == "completed"


def test_budget_after_inflight_operation(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(agent, "perf_counter", lambda: clock[0])
    model = install(monkeypatch, [call()])
    def delayed(text):
        clock[0] = 121
        return agent.analyze_sentiment(text)
    monkeypatch.setitem(agent._TOOLS, "analyze_sentiment", (agent.TextArguments, delayed, "sentiment"))
    result = agent.run_agent("request")
    assert result.reason == "time_limit" and result.status == "partial_failure"
    assert len(model.messages) == 1 and result.trace[0].elapsed_ms == 121000


def test_configuration_without_provider(monkeypatch):
    monkeypatch.setattr(agent, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert agent.run_agent("request").reason == "configuration"


def test_model_settings_and_schema(monkeypatch):
    monkeypatch.setattr(agent, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("GROQ_API_KEY", "synthetic-key")
    monkeypatch.delenv("GROQ_AGENT_MODEL", raising=False)
    captured = {}
    class Chat:
        def __init__(self, **kw):
            captured.update(kw)
        def bind_tools(self, schemas, **kw):
            captured["schemas"] = schemas
            captured.update(kw)
            return self
    monkeypatch.setattr(agent, "ChatGroq", Chat)
    agent._create_model()
    assert captured["model"] == "openai/gpt-oss-20b"
    assert captured["timeout"] == 30 and captured["max_retries"] == 0
    assert captured["max_tokens"] == 2048 and captured["temperature"] == 0
    assert captured["reasoning_effort"] == "low" and captured["parallel_tool_calls"] is False
    assert {s["function"]["name"] for s in captured["schemas"]} == set(agent._TOOLS)
    assert all(s["function"]["parameters"]["additionalProperties"] is False for s in captured["schemas"])
    monkeypatch.setenv("GROQ_AGENT_MODEL", "unsupported")
    with pytest.raises(ValueError):
        agent._create_model()


def test_tracing_disabled(monkeypatch):
    from contextlib import contextmanager
    captured = []
    @contextmanager
    def context(**kw):
        captured.append(kw)
        yield
    monkeypatch.setattr(agent, "tracing_context", context)
    install(monkeypatch, [final()])
    agent.run_agent("request")
    assert captured == [{"enabled": False}]


@pytest.mark.parametrize("kind,status,reason", [
    ("auth", 401, "authentication"),
    ("rate", 429, "rate_limit"),
    ("timeout", None, "timeout"),
    ("bad", 400, "configuration"),
    ("call", 400, "invalid_tool_call"),
    ("server", 500, "provider_unavailable"),
])
def test_provider_error_categories(monkeypatch, kind, status, reason):
    import httpx
    from groq import AuthenticationError, RateLimitError, APITimeoutError, BadRequestError, InternalServerError
    request = httpx.Request("POST", "https://example.test")
    classes = {"auth": AuthenticationError, "rate": RateLimitError, "bad": BadRequestError,
               "call": BadRequestError, "server": InternalServerError}
    error = (APITimeoutError(request=request) if kind == "timeout" else classes[kind](
        "private secret", response=httpx.Response(status, request=request),
        body={"error": {"code": "tool_use_failed"}} if kind == "call" else None))
    model = install(monkeypatch, [error])
    result = agent.run_agent("request")
    assert result.reason == reason and result.status == "error"
    assert len(model.messages) == 1 and not result.trace
    assert "private" not in repr(result)
