"""Durable local chat records; one cooperating backend owns a database at a time."""

import fcntl
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from app.profile import EmployeeProfile, PROFILE_ID


class ChatPersistenceError(Exception):
    """Sanitized storage failure; execution must not continue with divergent history."""

    def __init__(self, message: str, *, outcome: str = "not_started"):
        super().__init__(message)
        self.outcome = outcome


class ChatTurnConflict(Exception):
    """A turn ID was reused inconsistently or unfinished work blocks execution."""

    def __init__(self, message: str, *, state: str | None = None):
        super().__init__(message)
        self.state = state


class ChatNotFound(Exception):
    """Management targets only an existing chat."""


_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = (
    """CREATE TABLE chats (
        session_id TEXT PRIMARY KEY, title TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        next_sequence INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE chat_turns (
        turn_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES chats(session_id),
        sequence INTEGER NOT NULL, message TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT,
        state TEXT NOT NULL CHECK(state IN ('running', 'finished', 'interrupted')),
        execution_json TEXT, failure_reply TEXT, failure_reason TEXT,
        demo_policy INTEGER NOT NULL DEFAULT 0 CHECK(demo_policy IN (0, 1)),
        UNIQUE(session_id, sequence))""",
)


def database_path() -> Path:
    load_dotenv(_ROOT / ".env", override=False)
    value = os.environ.get("OPSFLOW_CHATS_DB", "var/chats.sqlite3")
    if not value.strip() or value == ":memory:":
        raise ChatPersistenceError("Chat storage requires a persistent local file.")
    path = Path(value).expanduser()
    try:
        return (path if path.is_absolute() else _ROOT / path).resolve()
    except (OSError, ValueError, RuntimeError):
        raise ChatPersistenceError("Chat storage path is unavailable.") from None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _record(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["execution"] = json.loads(record.pop("execution_json")) if row["execution_json"] else None
    if record["execution"] is not None and not isinstance(record["execution"], dict):
        raise ValueError("Invalid execution record")
    if record["state"] == "finished" and record["execution"] is None and not record["failure_reply"]:
        raise ValueError("Missing finished outcome")
    record["demo_policy"] = bool(record["demo_policy"])
    return record


class ChatStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self._lock_file = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file = open(str(self.path) + ".lock", "a+b")
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._initialize()
        except (OSError, ChatPersistenceError):
            self.close()
            raise ChatPersistenceError("Chat storage unavailable or owned by another backend.") from None

    def close(self) -> None:
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    @contextmanager
    def _connection(self, *, write: bool = False):
        if self._lock_file is None:
            raise ChatPersistenceError("Chat storage is closed.")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    if write:
                        connection.execute("BEGIN IMMEDIATE")
                    yield connection
        except (sqlite3.Error, OSError, ValueError, TypeError):
            raise ChatPersistenceError("Chat records could not be saved or restored.") from None

    def _initialize(self) -> None:
        with self._connection(write=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ChatPersistenceError("Unsupported chat storage schema.")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 1")
            elif version not in {1, 2, 3}:
                raise ChatPersistenceError("Unsupported chat storage schema.")
            if version in {0, 1}:
                connection.execute("ALTER TABLE chats ADD COLUMN custom_title INTEGER NOT NULL DEFAULT 0")
                connection.execute("PRAGMA user_version = 2")
            if version in {0, 1, 2}:
                connection.execute("""CREATE TABLE employee_profile (
                    profile_id TEXT PRIMARY KEY CHECK(profile_id='EMP-001'),
                    name TEXT NOT NULL, role TEXT NOT NULL, company TEXT NOT NULL,
                    timezone TEXT NOT NULL, is_demo INTEGER NOT NULL CHECK(is_demo=1))""")
                connection.execute("INSERT INTO employee_profile VALUES (?, ?, ?, ?, ?, 1)",
                    (PROFILE_ID, "Sachin Tendulkar", "Operations Associate",
                     "OpsFlow Demo Company", "Asia/Kolkata"))
                connection.execute("PRAGMA user_version = 3")
            # Exclusive ownership proves these markers belong to a prior process.
            connection.execute("""UPDATE chat_turns SET state='interrupted',
                failure_reason='interrupted', failure_reply=? WHERE state='running'""",
                ("The previous turn was interrupted. Its completion is unknown; it was not retried.",))

    def profile(self) -> EmployeeProfile:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM employee_profile WHERE profile_id=?",
                                     (PROFILE_ID,)).fetchone()
            try:
                if row is None:
                    raise ValueError("Missing employee")
                data = dict(row)
                data["is_demo"] = data["is_demo"] == 1
                return EmployeeProfile.model_validate(data)
            except (ValueError, ValidationError):
                raise ChatPersistenceError("Employee profile could not be loaded.") from None

    def turns(self, session_id: str) -> list[dict]:
        """Read ordered records without creating chats or executing requests."""
        with self._connection() as connection:
            return [_record(row) for row in connection.execute(
                "SELECT * FROM chat_turns WHERE session_id=? ORDER BY sequence", (session_id,))]

    def create_chat(self, session_id: str) -> dict:
        with self._connection(write=True) as connection:
            now = _now()
            connection.execute("""INSERT INTO chats
                (session_id, title, created_at, updated_at) VALUES (?, 'New chat', ?, ?)""",
                               (session_id, now, now))
            return dict(session_id=session_id, title="New chat", created_at=now, updated_at=now)

    def list_chats(self) -> list[dict]:
        with self._connection() as connection:
            return [dict(row) for row in connection.execute("""SELECT
                session_id, title, created_at, updated_at FROM chats
                ORDER BY updated_at DESC, session_id ASC""")]

    def get_chat(self, session_id: str) -> dict | None:
        with self._connection() as connection:
            # Metadata and turns must describe the same snapshot during execution.
            connection.execute("BEGIN")
            row = connection.execute("""SELECT session_id, title, created_at, updated_at
                FROM chats WHERE session_id=?""", (session_id,)).fetchone()
            if row is None:
                return None
            return {**dict(row), "turns": [_record(turn) for turn in connection.execute(
                "SELECT * FROM chat_turns WHERE session_id=? ORDER BY sequence", (session_id,))]}

    def begin(self, session_id: str, message: str, turn_id: str) -> dict | None:
        """Commit the execution marker, or return an identical existing turn."""
        with self._connection(write=True) as connection:
            existing = connection.execute("SELECT * FROM chat_turns WHERE turn_id=?", (turn_id,)).fetchone()
            if existing is not None:
                if existing["session_id"] != session_id or existing["message"] != message:
                    raise ChatTurnConflict("Turn ID belongs to a different submission.")
                return _record(existing)
            if connection.execute("SELECT 1 FROM chat_turns WHERE session_id=? AND state='running'",
                                  (session_id,)).fetchone():
                raise ChatTurnConflict("An unfinished or unsaved turn blocks this chat. No execution was repeated.")
            now = _now()
            connection.execute("""INSERT OR IGNORE INTO chats
                (session_id, title, created_at, updated_at) VALUES (?, 'New chat', ?, ?)""",
                               (session_id, now, now))
            chat = connection.execute("SELECT next_sequence, custom_title FROM chats WHERE session_id=?",
                                      (session_id,)).fetchone()
            sequence = chat["next_sequence"]
            empty = not connection.execute("SELECT 1 FROM chat_turns WHERE session_id=?", (session_id,)).fetchone()
            connection.execute("""INSERT INTO chat_turns
                (turn_id, session_id, sequence, message, started_at, state)
                VALUES (?, ?, ?, ?, ?, 'running')""", (turn_id, session_id, sequence, message, now))
            if empty and not chat["custom_title"]:
                title = " ".join(message.split())
                title = title[:60] + ("…" if len(title) > 60 else "")
                connection.execute("UPDATE chats SET title=? WHERE session_id=?", (title, session_id))
            connection.execute("UPDATE chats SET updated_at=?, next_sequence=? WHERE session_id=?",
                               (now, sequence + 1, session_id))
            return None

    def finish(self, turn_id: str, *, execution: dict | None, demo_policy: bool = False,
               failure_reply: str | None = None, failure_reason: str | None = None) -> None:
        with self._connection(write=True) as connection:
            now = _now()
            cursor = connection.execute("""UPDATE chat_turns SET state='finished', finished_at=?,
                execution_json=?, demo_policy=?, failure_reply=?, failure_reason=?
                WHERE turn_id=? AND state='running'""",
                (now, json.dumps(execution, allow_nan=False) if execution is not None else None,
                 int(demo_policy), failure_reply, failure_reason, turn_id))
            if cursor.rowcount != 1:
                raise ChatPersistenceError("The turn could not be finalized.")
            connection.execute("""UPDATE chats SET updated_at=? WHERE session_id=
                (SELECT session_id FROM chat_turns WHERE turn_id=?)""", (now, turn_id))

    def clear(self, session_id: str) -> None:
        with self._connection(write=True) as connection:
            if connection.execute("SELECT 1 FROM chat_turns WHERE session_id=? AND state='running'",
                                  (session_id,)).fetchone():
                raise ChatTurnConflict("An unfinished or unsaved turn cannot be cleared.")
            connection.execute("DELETE FROM chat_turns WHERE session_id=?", (session_id,))
            connection.execute("UPDATE chats SET title='New chat', custom_title=0, updated_at=? WHERE session_id=?",
                               (_now(), session_id))

    def rename(self, session_id: str, title: str) -> dict:
        with self._connection(write=True) as connection:
            self._check_management(connection, session_id)
            connection.execute("UPDATE chats SET title=?, custom_title=1, updated_at=? WHERE session_id=?",
                               (title, _now(), session_id))
            return dict(connection.execute("SELECT session_id, title, created_at, updated_at FROM chats WHERE session_id=?",
                                           (session_id,)).fetchone())

    def delete(self, session_id: str) -> None:
        with self._connection(write=True) as connection:
            self._check_management(connection, session_id)
            connection.execute("DELETE FROM chat_turns WHERE session_id=?", (session_id,))
            connection.execute("DELETE FROM chats WHERE session_id=?", (session_id,))

    @staticmethod
    def _check_management(connection, session_id: str) -> None:
        if not connection.execute("SELECT 1 FROM chats WHERE session_id=?", (session_id,)).fetchone():
            raise ChatNotFound("Chat not found.")
        if connection.execute("SELECT 1 FROM chat_turns WHERE session_id=? AND state='running'",
                              (session_id,)).fetchone():
            raise ChatTurnConflict("Running or unsaved work blocks chat management.", state="running")
