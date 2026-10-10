"""Literal reminder arguments resolved locally inside a durable chat turn."""

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.tools.reminders import _ROOT, _resolve_due, schedule_reminder


Phrase = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class ReminderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None = None
    date: Phrase | None = None
    time: Phrase | None = None
    timezone: Phrase | None = None
    utc_offset: Phrase | None = None


class ReminderClarification(ValueError):
    """Safe user-facing question; no reminder was created by this call."""


@dataclass(frozen=True)
class ReminderTurn:
    creation_key: str
    now: datetime


_turn: ContextVar[ReminderTurn | None] = ContextVar("reminder_turn", default=None)


@contextmanager
def reminder_turn(turn_id: str, *, now: datetime | None = None):
    # Model call IDs are neither stable nor an application-owned operation ID.
    key = "chat-reminder:" + sha256(turn_id.encode()).hexdigest()
    token = _turn.set(ReminderTurn(key, now or datetime.now(UTC)))
    try:
        yield
    finally:
        _turn.reset(token)


def _literal(value: str, sources: list[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", source,
                         flags=re.IGNORECASE) for source in sources)


def creation_requested(source: str) -> bool:
    return bool(re.match(r"\s*(?:(?:please|can you|could you|would you|will you|I want you to|I need you to)\s+)?"
                         r"(?:remind me\b|(?:set|create|schedule|add)\b[^\n\"']*\breminder\b)",
                         source, flags=re.IGNORECASE))


def _date(phrase: str, current: date) -> date:
    relative = {"today": 0, "tomorrow": 1}
    if phrase.lower() in relative:
        return current + timedelta(days=relative[phrase.lower()])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", phrase):
        try:
            return date.fromisoformat(phrase)
        except ValueError:
            pass
    for pattern in ("%d %B %Y", "%B %d %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(phrase, pattern).date()
        except ValueError:
            pass
    raise ReminderClarification("Which date should I use? Please give today, tomorrow, or a full date with its year (for example 2026-10-10).")


def _time(phrase: str) -> time:
    if phrase.lower() in {"noon", "midnight"}:
        return time(12 if phrase.lower() == "noon" else 0)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", phrase, re.IGNORECASE)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        if 1 <= hour <= 12 and minute < 60:
            return time(hour % 12 + (12 if match[3].lower() == "pm" else 0), minute)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", phrase)
    if match and int(match[1]) < 24 and int(match[2]) < 60:
        return time(int(match[1]), int(match[2]))
    raise ReminderClarification("What time should I use? Please include am/pm or use a 24-hour time such as 10:00.")


def schedule_chat_reminder(*, sources: list[str], task=None, date=None, time=None,
                           timezone=None, utc_offset=None) -> BaseModel:
    turn = _turn.get()
    if turn is None:
        raise ReminderClarification("Please create this reminder through a saved OpsFlow chat.")
    if not any(creation_requested(source) for source in sources):
        raise ReminderClarification("Would you like me to create a one-time reminder? Please give its task, date and time.")
    for name, value in (("task", task), ("date", date), ("time", time)):
        if value is None or not value.strip():
            raise ReminderClarification(f"What {name} should I use for the reminder?")
    if not any(task in source for source in sources):
        raise ReminderClarification("Please confirm the exact task you want me to remind you about.")
    for value in (date, time, timezone, utc_offset):
        if value is not None and not _literal(value, sources):
            raise ReminderClarification("Please confirm the reminder task, full date, time and timezone; I could not verify those details from your messages.")
    if timezone is None and any(re.search(r"\b[A-Za-z_]+/[A-Za-z_]+\b|\b(?:in|timezone)\s+[A-Z]{2,5}\b", source)
                                for source in sources):
        raise ReminderClarification("Please confirm the explicit timezone as an IANA name, for example Asia/Kolkata.")
    for source in sources:
        # Reject alternative scheduling details, without interpreting task prose.
        prefix = re.split(re.escape(task), source, maxsplit=1, flags=re.IGNORECASE)[0]
        choosing_now = source != sources[-1] and (
            _literal(date, [sources[-1]]) or _literal(time, [sources[-1]]))
        if re.search(r"\bor\b", prefix, re.IGNORECASE) and not choosing_now:
            raise ReminderClarification("Which single date and time should I use for this reminder?")
        one_time_now = source != sources[-1] and re.search(r"\bone(?:-time| reminder| time)\b", sources[-1], re.IGNORECASE)
        if re.search(r"\b(every|each|daily|weekly|monthly|recurring)\b", prefix, re.IGNORECASE) and not one_time_now:
            raise ReminderClarification("I can create one one-time reminder. Which single date and time should I use?")
    load_dotenv(_ROOT / ".env", override=False)
    zone_name = timezone if timezone is not None else os.environ.get("OPSFLOW_TIMEZONE", "Asia/Kolkata")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ReminderClarification("Which IANA timezone should I use, for example Asia/Kolkata?") from None
    offset = None
    if utc_offset is not None:
        match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", utc_offset)
        if not match or int(match[2]) >= 24 or int(match[3]) >= 60:
            raise ReminderClarification("Please confirm a UTC offset such as -04:00 for this local time.")
        offset = (int(match[2]) * 60 + int(match[3])) * (1 if match[1] == "+" else -1)
    local_due = datetime.combine(_date(date, turn.now.astimezone(zone).date()), _time(time))
    try:
        if _resolve_due(local_due, zone_name, offset) <= turn.now:
            raise ValueError("A new reminder must be due in the future")
        record = schedule_reminder(task, local_due, turn.creation_key,
                                   timezone=zone_name, utc_offset_minutes=offset)
    except ValueError as error:
        # Existing scheduler messages are sanitized; no storage path/provider text.
        raise ReminderClarification(str(error) + ". Please confirm a future, unambiguous reminder time.") from None
    return ScheduledReminder(reminder_id=record.reminder_id, task=record.task,
                             due_at=record.due_at.isoformat(), timezone=record.timezone,
                             local_due=record.due_at.astimezone(zone).isoformat(),
                             created_at=record.created_at.isoformat())


class ScheduledReminder(BaseModel):
    status: str = "scheduled"
    reminder_id: str
    task: str
    due_at: str
    timezone: str
    local_due: str
    created_at: str


def scheduling_reply(record: dict) -> str:
    return (f"Reminder scheduled: {record['task']}\n\n"
            f"Due: {record['local_due']} [{record['timezone']}].\n\n"
            "Scheduling does not send email. The separately running reminder worker handles delivery. "
            "Check Settings → Reminders for the current delivery state; SMTP acceptance does not confirm inbox arrival.")
