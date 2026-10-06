import socket
import ssl
from unittest.mock import Mock

import pytest

from app.tools import email_notifications as tool
from app.tools.email_drafting import EmailDraft, EmailDraftResult, _ACTION_INSTRUCTIONS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(tool, "load_dotenv", Mock())
    monkeypatch.setenv("SMTP_USERNAME", "sender@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("OPSFLOW_USER_EMAIL", "user@example.com")


@pytest.fixture
def draft():
    return EmailDraftResult(
        email_draft=EmailDraft(recipient="client@external.com", subject="Maintenance update",
                              body="Hi Alex,\n\nMaintenance is Friday.\n[Your name]"),
        action_instructions=list(_ACTION_INSTRUCTIONS),
    )


@pytest.fixture
def transport(monkeypatch):
    smtp = Mock()
    smtp.send_message.return_value = {}
    factory = Mock(return_value=smtp)
    monkeypatch.setattr(tool.smtplib, "SMTP_SSL", factory)
    return factory, smtp


def test_message_sections_and_envelope_are_confined_to_configured_user(draft, transport):
    factory, smtp = transport
    result = tool.send_draft_notification(draft)
    assert result.status == "accepted"
    assert result.reason is None
    factory.assert_called_once()
    args, kwargs = factory.call_args
    assert args == ("smtp.gmail.com", 465)
    assert kwargs["timeout"] == 30
    assert kwargs["context"].verify_mode == ssl.CERT_REQUIRED
    assert kwargs["context"].check_hostname is True
    smtp.login.assert_called_once_with("sender@gmail.com", "abcdefghijklmnop")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert smtp.send_message.call_args.kwargs == {
        "from_addr": "sender@gmail.com", "to_addrs": ["user@example.com"],
    }
    assert message["To"] == "user@example.com"
    assert message["From"] == "sender@gmail.com"
    assert message["Subject"] == "OpsFlow: email draft ready for review"
    assert message["Message-ID"] == result.message_id
    assert message["Date"]
    assert message["Bcc"] is None and message["Cc"] is None and message["Reply-To"] is None
    body = message.get_content()
    assert body.index("Email draft") < body.index("What you should do")
    assert "Intended recipient: client@external.com" in body
    assert "Subject: Maintenance update" in body
    assert draft.email_draft.body in body
    for instruction in _ACTION_INSTRUCTIONS:
        assert instruction in body
    assert message.get_content_type() == "text/plain"
    smtp.close.assert_called_once()
    tool.load_dotenv.assert_called_once_with(tool.Path(tool.__file__).resolve().parents[2] / ".env", override=False)


def test_header_like_body_text_does_not_change_recipients(draft, transport):
    _, smtp = transport
    draft.email_draft.body = "Bcc: another@example.com\nTo: someone@example.com\n<script>example</script>"
    result = tool.send_draft_notification(draft)
    assert result.status == "accepted"
    message = smtp.send_message.call_args.args[0]
    assert message["Bcc"] is None
    assert message["To"] == "user@example.com"
    assert smtp.send_message.call_args.kwargs["to_addrs"] == ["user@example.com"]
    assert draft.email_draft.body in message.get_content()


@pytest.mark.parametrize("name,value", [
    ("SMTP_USERNAME", ""), ("SMTP_USERNAME", "Sender <sender@gmail.com>"),
    ("SMTP_USERNAME", "sender@gmail.com\r\nBcc: other@example.com"),
    ("OPSFLOW_USER_EMAIL", ""), ("OPSFLOW_USER_EMAIL", "not-an-address"),
    ("OPSFLOW_USER_EMAIL", "one@example.com,two@example.com"),
    ("OPSFLOW_USER_EMAIL", "one@example.com;two@example.com"),
    ("OPSFLOW_USER_EMAIL", "one@example.com\nBcc: other@example.com"),
    ("OPSFLOW_USER_EMAIL", "person@"), ("OPSFLOW_USER_EMAIL", "user@example.com\n"),
    ("SMTP_PASSWORD", ""), ("SMTP_PASSWORD", "short"),
    ("SMTP_PASSWORD", "abcd\nefghijklmnop"),
])
def test_invalid_configuration_prevents_connections(name, value, draft, transport, monkeypatch):
    factory, _ = transport
    monkeypatch.setenv(name, value)
    result = tool.send_draft_notification(draft)
    assert result.status == "failed" and result.reason == "configuration"
    factory.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("recipient", " "), ("recipient", "a" * 321), ("recipient", "Alex\nBcc: other@example.com"),
    ("subject", "Update\r\nBcc: other@example.com"), ("body", "a" * 4001),
])
def test_invalid_or_mutated_draft_prevents_connection(field, value, draft, transport):
    factory, _ = transport
    setattr(draft.email_draft, field, value)
    with pytest.raises(ValueError, match="Invalid notification draft"):
        tool.send_draft_notification(draft)
    factory.assert_not_called()


def test_arbitrary_actions_and_wrong_input_type_are_rejected(draft, transport):
    factory, _ = transport
    draft.action_instructions = ["Send this to everyone"]
    with pytest.raises(ValueError):
        tool.send_draft_notification(draft)
    with pytest.raises(TypeError):
        tool.send_draft_notification({})
    factory.assert_not_called()


@pytest.mark.parametrize("stage,failure,status,reason", [
    ("connect", TimeoutError("private-secret"), "failed", "timeout"),
    ("connect", OSError("private-secret"), "failed", "provider_unavailable"),
    ("login", tool.smtplib.SMTPAuthenticationError(535, b"private-secret"), "failed", "authentication"),
    ("login", tool.smtplib.SMTPServerDisconnected("private-secret"), "failed", "provider_unavailable"),
    ("send", tool.smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"private-secret")}), "failed", "rejected"),
    ("send", tool.smtplib.SMTPSenderRefused(550, b"private-secret", "sender@gmail.com"), "failed", "rejected"),
    ("send", tool.smtplib.SMTPDataError(554, b"private-secret"), "failed", "rejected"),
    ("send", TimeoutError("private-secret"), "unknown", "timeout"),
    ("send", tool.smtplib.SMTPServerDisconnected("private-secret"), "unknown", "provider_unavailable"),
    ("send", RuntimeError("private-secret"), "unknown", "provider_unavailable"),
])
def test_stage_aware_failures_are_sanitized_and_not_retried(stage, failure, status, reason, draft, transport):
    factory, smtp = transport
    if stage == "connect":
        factory.side_effect = failure
    elif stage == "login":
        smtp.login.side_effect = failure
    else:
        smtp.send_message.side_effect = failure
    result = tool.send_draft_notification(draft)
    assert result.status == status and result.reason == reason
    assert "private-secret" not in result.model_dump_json()
    factory.assert_called_once()
    assert smtp.send_message.call_count == (1 if stage == "send" else 0)
    assert smtp.close.call_count == (0 if stage == "connect" else 1)


def test_explicit_refusal_result_is_failure(draft, transport):
    _, smtp = transport
    smtp.send_message.return_value = {"user@example.com": (550, b"private-secret")}
    result = tool.send_draft_notification(draft)
    assert result.status == "failed" and result.reason == "rejected"
    assert "private-secret" not in result.model_dump_json()


@pytest.mark.parametrize("failure", [None, tool.smtplib.SMTPDataError(554, b"private"), TimeoutError("private")])
def test_cleanup_cannot_override_submission_outcome(failure, draft, transport):
    _, smtp = transport
    smtp.send_message.side_effect = failure
    smtp.close.side_effect = OSError("private cleanup failure")
    result = tool.send_draft_notification(draft)
    assert result.status == ("accepted" if failure is None else "failed" if isinstance(failure, tool.smtplib.SMTPDataError) else "unknown")
    smtp.send_message.assert_called_once()
    smtp.close.assert_called_once()


def test_each_call_has_unique_id_without_claiming_deduplication(draft, transport):
    first = tool.send_draft_notification(draft)
    second = tool.send_draft_notification(draft)
    assert first.message_id != second.message_id
