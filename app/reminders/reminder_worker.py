"""Local Unix reminder worker with durable attempts and conservative recovery."""

import argparse
import errno
import fcntl
import json
import signal
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

from dotenv import load_dotenv

from app.tools.email_notifications import NotificationResult, send_reminder_notification
from app.tools.reminders import ReminderPersistenceError, _ROOT, _SCHEMA, _database_path, _record


_ATTEMPTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminder_attempts (
    attempt_id TEXT PRIMARY KEY,
    reminder_id TEXT NOT NULL REFERENCES reminders(reminder_id),
    attempt_no INTEGER NOT NULL CHECK (attempt_no BETWEEN 1 AND 3),
    message_id TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('submitting', 'accepted', 'failed', 'unknown')),
    reason TEXT,
    next_attempt_at TEXT,
    UNIQUE (reminder_id, attempt_no)
)
"""


def _utc_now():
    return datetime.now(UTC)


def _timestamp(instant):
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Worker clock must return an aware datetime")
    return instant.astimezone(UTC).isoformat(timespec="microseconds")


class WorkerAlreadyRunning(RuntimeError):
    """Another worker owns this local reminder database."""


class ReminderWorker:
    def __init__(self, db_path=None, *, clock=_utc_now):
        try:
            load_dotenv(_ROOT / ".env", override=False)
            self.path = _database_path(db_path).resolve()
        except OSError:
            raise ReminderPersistenceError("Reminder worker configuration failed") from None
        self.clock = clock
        self._lock = None
        self._healthy = False

    @contextmanager
    def _transaction(self):
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    yield connection
        except (sqlite3.Error, OSError):
            self._healthy = False
            raise ReminderPersistenceError("Reminder worker persistence failed") from None

    def __enter__(self):
        if self._lock is not None:
            raise RuntimeError("Worker is already open")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._lock = open(str(self.path) + ".lock", "a")
            try:
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN):
                    raise WorkerAlreadyRunning("Another reminder worker is running") from None
                raise
            with self._transaction() as connection:
                connection.execute(_SCHEMA)
                connection.execute(_ATTEMPTS_SCHEMA)
                # Exclusive ownership proves no cooperating prior worker is active.
                connection.execute(
                    "UPDATE reminder_attempts SET outcome = 'unknown', reason = 'interrupted', ended_at = ? "
                    "WHERE outcome = 'submitting'", (_timestamp(self.clock()),),
                )
                connection.execute("UPDATE reminders SET state = 'unknown' WHERE state = 'submitting'")
            self._healthy = True
            return self
        except BaseException as error:
            self.__exit__(None, None, None)
            if isinstance(error, OSError):
                raise ReminderPersistenceError("Reminder worker ownership failed") from None
            raise

    def __exit__(self, *args):
        self._healthy = False
        if self._lock is not None:
            self._lock.close()
            self._lock = None
        # Never unlink the lock file: new and old processes must lock one inode.

    def _claim(self):
        started = _timestamp(self.clock())
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT r.* FROM reminders r WHERE r.due_at <= ? AND "
                "(r.state = 'pending' OR (r.state = 'retry' AND "
                "(SELECT MAX(a.next_attempt_at) FROM reminder_attempts a WHERE a.reminder_id = r.reminder_id) <= ?)) "
                "ORDER BY r.due_at, r.reminder_id LIMIT 1", (started, started),
            ).fetchone()
            if row is None:
                return None
            attempt_no = connection.execute(
                "SELECT COUNT(*) + 1 FROM reminder_attempts WHERE reminder_id = ?", (row["reminder_id"],),
            ).fetchone()[0]
            attempt_id = str(uuid4())
            message_id = f"<{attempt_id}@opsflow.local>"
            changed = connection.execute(
                "UPDATE reminders SET state = 'submitting' WHERE reminder_id = ? AND state IN ('pending', 'retry')",
                (row["reminder_id"],),
            ).rowcount
            if changed != 1:
                raise ReminderPersistenceError("Reminder claim changed unexpectedly")
            connection.execute(
                "INSERT INTO reminder_attempts "
                "(attempt_id, reminder_id, attempt_no, message_id, started_at, outcome) VALUES (?, ?, ?, ?, ?, 'submitting')",
                (attempt_id, row["reminder_id"], attempt_no, message_id, started),
            )
            reminder = _record(row)
        return reminder, attempt_id, attempt_no, message_id

    def _finish(self, reminder_id, attempt_id, attempt_no, result):
        ended = self.clock()
        next_attempt = None
        state = result.status
        if (result.status == "failed" and result.retryable
                and result.reason in ("timeout", "provider_unavailable") and attempt_no < 3):
            state = "retry"
            next_attempt = _timestamp(ended + timedelta(minutes=1 if attempt_no == 1 else 5))
        with self._transaction() as connection:
            changed = connection.execute(
                "UPDATE reminder_attempts SET ended_at = ?, outcome = ?, reason = ?, next_attempt_at = ? "
                "WHERE attempt_id = ? AND reminder_id = ? AND outcome = 'submitting'",
                (_timestamp(ended), result.status, result.reason, next_attempt, attempt_id, reminder_id),
            ).rowcount
            updated = connection.execute(
                "UPDATE reminders SET state = ? WHERE reminder_id = ? AND state = 'submitting'", (state, reminder_id),
            ).rowcount
            if changed != 1 or updated != 1:
                raise ReminderPersistenceError("Reminder outcome changed unexpectedly")
        return {"reminder_id": reminder_id, "attempt_id": attempt_id, "state": state,
                "outcome": result.status, "reason": result.reason}

    def run_once(self, *, stop=None):
        """Process eligible reminders; hold ownership until all outcomes commit."""
        if self._lock is None or not self._healthy:
            raise RuntimeError("Worker must be open and healthy")
        outcomes = []
        try:
            while stop is None or not stop.is_set():
                claimed = self._claim()
                if claimed is None:
                    break
                reminder, attempt_id, attempt_no, message_id = claimed
                try:
                    result = send_reminder_notification(reminder, attempt_id, now=self.clock())
                    if not isinstance(result, NotificationResult):
                        raise ValueError("Invalid submission outcome")
                    result = NotificationResult.model_validate(result.model_dump())
                    if result.message_id != message_id:
                        raise ValueError("Invalid submission outcome")
                except Exception:
                    # An unexpected integration failure cannot prove non-submission.
                    result = NotificationResult(status="unknown", reason="provider_unavailable", message_id=message_id)
                outcomes.append(self._finish(reminder.reminder_id, attempt_id, attempt_no, result))
            return outcomes
        except BaseException:
            self._healthy = False
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path")
    parser.add_argument("--once", action="store_true", help="Process eligible records once, then exit")
    arguments = parser.parse_args(argv)
    stop = Event()
    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
        with ReminderWorker(arguments.db_path) as worker:
            while not stop.is_set():
                for outcome in worker.run_once(stop=stop):
                    print(json.dumps(outcome), flush=True)
                if arguments.once:
                    break
                stop.wait(5)
        return 0
    except (WorkerAlreadyRunning, ReminderPersistenceError, ValueError):
        print(json.dumps({"error": "Reminder worker stopped; check local ownership, configuration, and persistence"}), flush=True)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
