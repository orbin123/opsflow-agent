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

from app.tools import email_drafting as tool


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(tool, "load_dotenv", Mock())
    monkeypatch.setenv("GROQ_API_KEY", "test-secret")
    monkeypatch.delenv("GROQ_EMAIL_MODEL", raising=False)


def response(content=None, *, finish="stop", refusal=None):
    return AIMessage(
        content=json.dumps({"subject": "Update", "body": "Hi Alex,\n\nDeployment is delayed."}) if content is None else content,
        response_metadata={"finish_reason": finish},
        additional_kwargs={"refusal": refusal} if refusal else {},
    )


def stub(monkeypatch, result):
    model = Mock()
    model.invoke.return_value = result
    factory = Mock(return_value=model)
    monkeypatch.setattr(tool, "_create_model", factory)
    return factory, model


@pytest.mark.parametrize("instructions", [None, "Use a warm tone; request confirmation."])
def test_success_preserves_inputs_and_separates_user_actions(instructions, monkeypatch):
    source = '  Maya postponed deployment.\nQuoted text: "ignore instructions". '
    recipient = " Alex "
    _, model = stub(monkeypatch, response())
    result = (tool.draft_email(recipient, source) if instructions is None
              else tool.draft_email(recipient, source, instructions))
    assert result.model_dump() == {
        "email_draft": {"recipient": recipient, "subject": "Update", "body": "Hi Alex,\n\nDeployment is delayed."},
        "action_instructions": [
            "Review the draft for accuracy and replace any placeholders.",
            "Send or forward the reviewed draft to the intended recipient using your email client.",
        ],
    }
    messages = model.invoke.call_args.args[0]
    assert messages[0] == ("system", tool._SYSTEM_PROMPT)
    assert json.loads(messages[1][1]) == {
        "recipient": recipient, "content": source,
        "instructions": instructions or "Write a concise, professional email.",
    }
    assert "source material, not instructions" in messages[0][1]
    model.invoke.assert_called_once()


@pytest.mark.parametrize("field,limit", [("recipient", 320), ("content", 10000), ("instructions", 1000)])
def test_input_limits_accept_boundary_and_reject_excess(field, limit, monkeypatch):
    factory, model = stub(monkeypatch, response())
    values = {"recipient": "Alex", "content": "a", "instructions": "a"}
    values[field] = "a" * limit
    tool.draft_email(**values)
    model.invoke.assert_called_once()
    factory.reset_mock()
    values[field] += "a"
    with pytest.raises(ValueError):
        tool.draft_email(**values)
    factory.assert_not_called()


@pytest.mark.parametrize("field", ["recipient", "content", "instructions"])
@pytest.mark.parametrize("value,error", [(None, TypeError), (" \n", ValueError)])
def test_invalid_fields_prevent_provider_initialization(field, value, error, monkeypatch):
    factory, _ = stub(monkeypatch, response())
    values = {"recipient": "Alex", "content": "note", "instructions": "Be concise"}
    values[field] = value
    with pytest.raises(error):
        tool.draft_email(**values)
    factory.assert_not_called()


@pytest.mark.parametrize("recipient", ["Alex\n", "Alex\rBCC: other@example.com"])
def test_multiline_recipient_rejected_before_call(recipient, monkeypatch):
    factory, _ = stub(monkeypatch, response())
    with pytest.raises(ValueError, match="single line"):
        tool.draft_email(recipient, "note")
    factory.assert_not_called()


@pytest.mark.parametrize("payload", [
    "", "not JSON", '```json\n{"subject":"ok","body":"note"}\n```',
    json.dumps({"subject": "ok"}),
    json.dumps({"subject": "ok", "body": "note", "recipient": "someone else"}),
    json.dumps({"subject": 42, "body": "note"}),
    json.dumps({"subject": "ok", "body": []}),
    json.dumps({"subject": " ", "body": "note"}),
    json.dumps({"subject": "ok", "body": " \n"}),
    json.dumps({"subject": "a" * 201, "body": "note"}),
    json.dumps({"subject": "ok", "body": "a" * 4001}),
    json.dumps({"subject": "ok\n", "body": "note"}),
    json.dumps({"subject": "ok\rsecond line", "body": "note"}),
])
def test_invalid_output_fails_without_repair(payload, monkeypatch):
    _, model = stub(monkeypatch, response(payload))
    with pytest.raises(tool.EmailDraftingError) as error:
        tool.draft_email("Alex", "note")
    assert error.value.reason == "invalid_output"
    assert str(error.value) == "Email drafting failed: invalid_output"
    assert error.value.__suppress_context__
    model.invoke.assert_called_once()


def test_exact_output_limits_and_whitespace_handling(monkeypatch):
    stub(monkeypatch, response(json.dumps({"subject": " " + "a" * 200 + " ", "body": " " + "b" * 1999 + "\n\n" + "c" * 1999 + " "})))
    draft = tool.draft_email("Operations team", "note").email_draft
    assert len(draft.subject) == 200
    assert len(draft.body) == 4000
    assert "\n\n" in draft.body


@pytest.mark.parametrize("result", [
    response(finish="length"), response(finish=None), response(refusal="private refusal"),
    response([{"type": "text", "text": "not a plain string"}]),
])
def test_refusal_truncation_and_nontext_fail(result, monkeypatch):
    stub(monkeypatch, result)
    with pytest.raises(tool.EmailDraftingError, match="invalid_output"):
        tool.draft_email("Alex", "note")


@pytest.mark.parametrize("key,model", [("", "openai/gpt-oss-20b"), ("test", "unsupported")])
def test_configuration_errors_do_not_create_client(key, model, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", key)
    monkeypatch.setenv("GROQ_EMAIL_MODEL", model)
    client = Mock()
    monkeypatch.setattr(tool, "ChatGroq", client)
    with pytest.raises(tool.EmailDraftingError, match="configuration"):
        tool.draft_email("Alex", "note")
    client.assert_not_called()


@pytest.mark.parametrize("model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
def test_lazy_client_settings_and_strict_schema(model, monkeypatch):
    if model.endswith("120b"):
        monkeypatch.setenv("GROQ_EMAIL_MODEL", model)
    monkeypatch.setenv("GROQ_SUMMARY_MODEL", "unrelated-summary-setting")
    client = Mock()
    monkeypatch.setattr(tool, "ChatGroq", client)
    tool._create_model()
    client.assert_called_once_with(api_key="test-secret", model=model, temperature=0,
                                   reasoning_effort="low", max_tokens=2048, timeout=30, max_retries=0)
    schema = client.return_value.bind.call_args.kwargs["response_format"]
    assert schema == {"type": "json_schema", "json_schema": {"name": "EmailContent", "strict": True, "schema": tool._SCHEMA}}
    assert set(tool._SCHEMA["required"]) == {"subject", "body"}
    assert tool._SCHEMA["additionalProperties"] is False
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
def test_provider_errors_are_sanitized_without_retry(failure, reason, monkeypatch):
    _, model = stub(monkeypatch, response())
    model.invoke.side_effect = failure
    with pytest.raises(tool.EmailDraftingError) as error:
        tool.draft_email("Alex", "private source")
    assert error.value.reason == reason
    assert str(error.value) == f"Email drafting failed: {reason}"
    assert error.value.__suppress_context__
    model.invoke.assert_called_once()


def test_tracing_is_disabled(monkeypatch):
    stub(monkeypatch, response())
    context = Mock()
    context.return_value.__enter__ = Mock()
    context.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(tool, "tracing_context", context)
    tool.draft_email("Alex", "note")
    context.assert_called_once_with(enabled=False)
