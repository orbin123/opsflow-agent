import json
import socket
from unittest.mock import Mock

import httpx
import pytest
from groq import (
    APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError,
    InternalServerError, RateLimitError,
)
from langchain_core.messages import AIMessage

from app.tools import summarization as tool


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(tool, "load_dotenv", Mock())
    monkeypatch.setenv("GROQ_API_KEY", "test-secret")
    monkeypatch.delenv("GROQ_SUMMARY_MODEL", raising=False)


def response(content=None, *, finish="stop", refusal=None):
    return AIMessage(
        content=json.dumps({"summary": "Deployment is delayed.", "key_points": []}) if content is None else content,
        response_metadata={"finish_reason": finish},
        additional_kwargs={"refusal": refusal} if refusal else {},
    )


def stub(monkeypatch, result):
    model = Mock()
    model.invoke.return_value = result
    factory = Mock(return_value=model)
    monkeypatch.setattr(tool, "_create_model", factory)
    return factory, model


def test_source_is_preserved_and_success_is_structured(monkeypatch):
    source = "  Maya postponed deployment to 9 October; the cause may be a vendor delay.\n"
    expected = {"summary": "Maya postponed deployment to 9 October.", "key_points": ["A vendor delay may be the cause."]}
    _, model = stub(monkeypatch, response(json.dumps(expected)))
    result = tool.summarize_text(source)
    assert result.model_dump() == expected
    messages = model.invoke.call_args.args[0]
    assert messages == [("system", tool._SYSTEM_PROMPT), ("human", source)]
    assert "not instructions" in messages[0][1]


@pytest.mark.parametrize("length", [1, 10000])
def test_accepted_input_boundaries_and_empty_points(length, monkeypatch):
    stub(monkeypatch, response())
    assert tool.summarize_text("a" * length).key_points == []


@pytest.mark.parametrize("text,exception", [(None, TypeError), (12, TypeError), ("", ValueError), (" \n", ValueError), ("a" * 10001, ValueError)])
def test_invalid_input_never_initializes_provider(text, exception, monkeypatch):
    factory, _ = stub(monkeypatch, response())
    with pytest.raises(exception):
        tool.summarize_text(text)
    factory.assert_not_called()


@pytest.mark.parametrize("payload", [
    "", "not JSON", '```json\n{"summary":"ok","key_points":[]}\n```',
    '{"summary":"ok","key_points":[]',
    json.dumps({"summary": "ok"}),
    json.dumps({"summary": "ok", "key_points": [], "extra": "private"}),
    json.dumps({"summary": 42, "key_points": []}),
    json.dumps({"summary": " \n", "key_points": []}),
    json.dumps({"summary": "a" * 1501, "key_points": []}),
    json.dumps({"summary": "ok", "key_points": ["a"] * 6}),
    json.dumps({"summary": "ok", "key_points": [" "]}),
    json.dumps({"summary": "ok", "key_points": ["a" * 301]}),
    json.dumps({"summary": "ok", "key_points": [12]}),
])
def test_invalid_output_is_not_repaired(payload, monkeypatch):
    _, model = stub(monkeypatch, response(payload))
    with pytest.raises(tool.SummarizationError) as error:
        tool.summarize_text("source")
    assert error.value.reason == "invalid_output"
    assert str(error.value) == "Summarization failed: invalid_output"
    assert error.value.__suppress_context__
    model.invoke.assert_called_once()


def test_output_limits_accept_exact_boundary(monkeypatch):
    stub(monkeypatch, response(json.dumps({"summary": "a" * 1500, "key_points": ["b" * 300] * 5})))
    assert len(tool.summarize_text("source").key_points) == 5


@pytest.mark.parametrize("finish,refusal", [("length", None), ("content_filter", None), (None, None), ("stop", "private refusal")])
def test_refusal_or_noncompleted_response_fails_even_with_valid_json(finish, refusal, monkeypatch):
    stub(monkeypatch, response(finish=finish, refusal=refusal))
    with pytest.raises(tool.SummarizationError, match="invalid_output"):
        tool.summarize_text("source")


@pytest.mark.parametrize("key,model", [("", "openai/gpt-oss-20b"), ("test", "unsupported-model")])
def test_missing_key_or_unsupported_model_prevents_client_creation(key, model, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", key)
    monkeypatch.setenv("GROQ_SUMMARY_MODEL", model)
    client = Mock()
    monkeypatch.setattr(tool, "ChatGroq", client)
    with pytest.raises(tool.SummarizationError, match="configuration"):
        tool.summarize_text("source")
    client.assert_not_called()


@pytest.mark.parametrize("model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
def test_lazy_configuration_and_strict_schema(model, monkeypatch):
    if model.endswith("120b"):
        monkeypatch.setenv("GROQ_SUMMARY_MODEL", model)
    client = Mock()
    monkeypatch.setattr(tool, "ChatGroq", client)
    tool._create_model()
    client.assert_called_once_with(api_key="test-secret", model=model, temperature=0,
                                   reasoning_effort="low", max_tokens=2048, timeout=30, max_retries=0)
    schema = client.return_value.bind.call_args.kwargs["response_format"]
    assert schema["type"] == "json_schema"
    assert schema["json_schema"]["strict"] is True
    assert schema["json_schema"]["schema"]["additionalProperties"] is False
    assert set(schema["json_schema"]["schema"]["required"]) == {"summary", "key_points"}
    tool.load_dotenv.assert_called_once_with(tool.Path(tool.__file__).resolve().parents[2] / ".env", override=False)


_request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


@pytest.mark.parametrize("failure,reason", [
    (AuthenticationError("private test-secret", response=httpx.Response(401, request=_request), body=None), "authentication"),
    (RateLimitError("private test-secret", response=httpx.Response(429, request=_request), body=None), "rate_limit"),
    (APITimeoutError(request=_request), "timeout"),
    (BadRequestError("private test-secret", response=httpx.Response(400, request=_request), body=None), "configuration"),
    (InternalServerError("private test-secret", response=httpx.Response(500, request=_request), body=None), "provider_unavailable"),
    (APIConnectionError(request=_request), "provider_unavailable"),
    (RuntimeError("private test-secret"), "provider_unavailable"),
])
def test_failures_are_sanitized_without_retry(failure, reason, monkeypatch):
    _, model = stub(monkeypatch, response())
    model.invoke.side_effect = failure
    with pytest.raises(tool.SummarizationError) as error:
        tool.summarize_text("private source")
    assert error.value.reason == reason
    assert str(error.value) == f"Summarization failed: {reason}"
    assert error.value.__suppress_context__
    model.invoke.assert_called_once()


def test_external_tracing_is_explicitly_disabled(monkeypatch):
    stub(monkeypatch, response())
    context = Mock()
    context.return_value.__enter__ = Mock()
    context.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(tool, "tracing_context", context)
    tool.summarize_text("source")
    context.assert_called_once_with(enabled=False)
