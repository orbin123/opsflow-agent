"""One-attempt Gmail notification submission to the configured user's mailbox."""

import os
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError

from app.tools.email_drafting import EmailDraftResult, _ACTION_INSTRUCTIONS


class NotificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["accepted", "failed", "unknown"]
    reason: Literal["configuration", "authentication", "rejected", "timeout", "provider_unavailable"] | None
    message_id: str


def _mailbox(value: str) -> str:
    """Accept one bare ASCII mailbox, not display names or address lists."""
    if (not value or len(value) > 254 or not value.isascii()
            or any(character.isspace() for character in value)):
        raise ValueError("Invalid mailbox configuration")
    address = Address(addr_spec=value)
    if not address.username or not address.domain or address.addr_spec != value:
        raise ValueError("Invalid mailbox configuration")
    return value


def _configuration():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    sender = _mailbox(os.environ.get("SMTP_USERNAME", ""))
    recipient = _mailbox(os.environ.get("OPSFLOW_USER_EMAIL", ""))
    # Google displays app passwords with spaces between groups.
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "")
    if len(password) != 16 or not password.isascii() or not password.isalnum():
        raise ValueError("Invalid app-password configuration")
    return sender, recipient, password


def send_draft_notification(draft: EmailDraftResult) -> NotificationResult:
    """Submit a draft notification, without retries or claims of inbox arrival.

    Only the configured mailbox is an envelope recipient. Ambiguous submission
    outcomes require review before retrying; Message-ID is not deduplication.
    This function has no Groq call, session state, or reminder scheduling.
    """
    if not isinstance(draft, EmailDraftResult):
        raise TypeError("Notification draft must be an EmailDraftResult")
    try:
        draft = EmailDraftResult.model_validate(draft.model_dump())
    except ValidationError:
        raise ValueError("Invalid notification draft") from None
    target = draft.email_draft.recipient
    if (not target.strip() or len(target) > 320 or "\r" in target or "\n" in target
            or tuple(draft.action_instructions) != _ACTION_INSTRUCTIONS):
        raise ValueError("Invalid notification draft")

    message_id = f"<{uuid4()}@opsflow.local>"
    try:
        sender, recipient, password = _configuration()
    except Exception:
        return NotificationResult(status="failed", reason="configuration", message_id=message_id)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "OpsFlow: email draft ready for review"
    message["Message-ID"] = message_id
    message["Date"] = formatdate(usegmt=True)
    message.set_content(
        "Email draft\n"
        f"Intended recipient: {target}\n"
        f"Subject: {draft.email_draft.subject}\n\n"
        f"{draft.email_draft.body}\n\n"
        "What you should do\n"
        + "\n".join(f"- {action}" for action in draft.action_instructions)
    )

    smtp = None
    submitting = False
    try:
        smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30, context=ssl.create_default_context())
        smtp.login(sender, password)
        submitting = True
        refused = smtp.send_message(message, from_addr=sender, to_addrs=[recipient])
        if refused:
            return NotificationResult(status="failed", reason="rejected", message_id=message_id)
        return NotificationResult(status="accepted", reason=None, message_id=message_id)
    except smtplib.SMTPAuthenticationError:
        status, reason = "failed", "authentication"
    except (smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError):
        status, reason = "failed", "rejected"
    except TimeoutError:
        status, reason = ("unknown" if submitting else "failed"), "timeout"
    except Exception:
        status, reason = ("unknown" if submitting else "failed"), "provider_unavailable"
    finally:
        # No QUIT acknowledgement is needed to preserve an already observed result.
        if smtp is not None:
            try:
                smtp.close()
            except Exception:
                pass
    return NotificationResult(status=status, reason=reason, message_id=message_id)
