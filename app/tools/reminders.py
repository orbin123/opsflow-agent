"""Structured reminder scheduling; persistence is not email delivery."""

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True)
class ReminderRecord:
    reminder_id: str
    creation_key: str
    task: str
    due_at: datetime
    timezone: str
    created_at: datetime
    status: Literal["scheduled"] = "scheduled"


class ReminderPersistenceError(RuntimeError):
    """The reminder could not be stored or read; no success is reported."""


_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id TEXT PRIMARY KEY,
    creation_key TEXT NOT NULL UNIQUE,
    task TEXT NOT NULL,
    due_at TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
)
"""


def _text(value: str, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank and at most {limit} characters")
    return value


def _resolve_due(local_due: datetime, zone_name: str, utc_offset_minutes: int | None) -> datetime:
    if not isinstance(local_due, datetime):
        raise TypeError("Local due time must be a datetime")
    if local_due.tzinfo is not None:
        raise ValueError("Supply a local calendar time without tzinfo and a separate IANA timezone")
    _text(zone_name, "Timezone", 128)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Timezone is invalid or its data is unavailable") from None
    if utc_offset_minutes is not None:
        if type(utc_offset_minutes) is not int:
            raise TypeError("UTC offset minutes must be an integer")
        if not -1439 <= utc_offset_minutes <= 1439:
            raise ValueError("UTC offset minutes are outside the valid range")

    # Neither a tzinfo assignment nor a fold flag alone validates a wall time.
    candidates = {}
    try:
        for fold in (0, 1):
            aware = local_due.replace(tzinfo=zone, fold=fold)
            due = aware.astimezone(UTC)
            if due.astimezone(zone).replace(tzinfo=None) == local_due:
                candidates[due] = aware.utcoffset()
    except (OverflowError, ValueError):
        raise ValueError("Due time cannot be represented in UTC") from None
    if not candidates:
        raise ValueError("Local due time does not exist in this timezone; clarify the time")
    if utc_offset_minutes is not None:
        candidates = {due: offset for due, offset in candidates.items()
                      if offset == timedelta(minutes=utc_offset_minutes)}
        if not candidates:
            raise ValueError("UTC offset does not match this local time and timezone")
    if len(candidates) != 1:
        raise ValueError("Local due time is ambiguous; supply a confirmed UTC offset")
    return next(iter(candidates))


def _database_path(db_path: str | Path | None) -> Path:
    value = db_path if db_path is not None else os.environ.get("OPSFLOW_REMINDERS_DB", "var/reminders.sqlite3")
    if not isinstance(value, (str, Path)):
        raise TypeError("Reminder database path must be a string or Path")
    if not str(value).strip() or str(value) == ":memory:":
        raise ValueError("Reminder database must use a persistent file path")
    path = Path(value)
    return path if path.is_absolute() else _ROOT / path


def _record(row: sqlite3.Row) -> ReminderRecord:
    return ReminderRecord(
        reminder_id=row["reminder_id"], creation_key=row["creation_key"], task=row["task"],
        due_at=datetime.fromisoformat(row["due_at"]), timezone=row["timezone"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def schedule_reminder(
    task: str, local_due: datetime, creation_key: str, *, timezone: str | None = None,
    utc_offset_minutes: int | None = None, db_path: str | Path | None = None,
    now: datetime | None = None,
) -> ReminderRecord:
    """Persist a one-time reminder from resolved arguments; never send email.

    Reuse creation_key for retries. A repeated key with changed normalized
    arguments fails. The optional aware `now` supplies a controlled current
    instant; production callers omit it. Ambiguous wall times require a
    caller-confirmed offset, not an inferred fold or machine timezone.
    """
    task = _text(task, "Reminder task", 1000).strip()
    _text(creation_key, "Creation key", 128)
    load_dotenv(_ROOT / ".env", override=False)
    zone_name = timezone if timezone is not None else os.environ.get("OPSFLOW_TIMEZONE", "Asia/Kolkata")
    due_at = _resolve_due(local_due, zone_name, utc_offset_minutes)
    current = datetime.now(UTC) if now is None else now
    if not isinstance(current, datetime):
        raise TypeError("Current instant must be a datetime")
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Current instant must have a timezone")
    current = current.astimezone(UTC)
    path = _database_path(db_path)
    due_text = due_at.isoformat(timespec="microseconds")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                # Serialize lookup + insert so competing retries share one record.
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(_SCHEMA)
                existing = connection.execute(
                    "SELECT * FROM reminders WHERE creation_key = ?", (creation_key,),
                ).fetchone()
                if existing is not None:
                    if (existing["task"], existing["due_at"], existing["timezone"]) != (task, due_text, zone_name):
                        raise ValueError("Creation key already belongs to different reminder arguments")
                    record = _record(existing)
                else:
                    if due_at <= current:
                        raise ValueError("A new reminder must be due in the future")
                    reminder_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO reminders (reminder_id, creation_key, task, due_at, timezone, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (reminder_id, creation_key, task, due_text, zone_name,
                         current.isoformat(timespec="microseconds")),
                    )
                    record = ReminderRecord(reminder_id, creation_key, task, due_at, zone_name, current)
            # Return only after the transaction commits successfully.
            return record
    except (sqlite3.Error, OSError):
        raise ReminderPersistenceError("Reminder persistence failed") from None
