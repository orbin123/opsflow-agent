"""Read-only snapshots of stored reminders; never initialize storage or a worker."""

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.tools.reminders import ReminderPersistenceError, _ROOT, _database_path


class SavedReminder(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    profile_id: Literal["EMP-001"] = "EMP-001"
    reminder_id: str = Field(min_length=1)
    task: str = Field(min_length=1, max_length=1000)
    due_at: AwareDatetime
    timezone: str
    created_at: AwareDatetime
    state: Literal["pending", "submitting", "retry", "accepted", "failed", "unknown"]

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value

    @field_validator("task", "reminder_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Blank reminder field")
        return value


def list_saved_reminders(db_path=None) -> list[SavedReminder]:
    """Read one SQLite snapshot, ordered by due time then identity.

    Missing storage means no reminders have been stored. Existing invalid storage
    fails explicitly. mode=ro prevents creation, migrations and worker recovery.
    """
    try:
        load_dotenv(_ROOT / ".env", override=False)
        path = _database_path(db_path).resolve()
        try:
            path.stat()
        except FileNotFoundError:
            return []
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT reminder_id, task, due_at, timezone, created_at, state FROM reminders"
            ).fetchall()
        records = []
        for row in rows:
            data = dict(row)
            for field in ("due_at", "created_at"):
                data[field] = datetime.fromisoformat(data[field])
            records.append(SavedReminder.model_validate(data))
        return sorted(records, key=lambda record: (record.due_at, record.reminder_id))
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise ReminderPersistenceError("Saved reminders could not be loaded") from None
