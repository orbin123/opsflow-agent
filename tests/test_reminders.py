import json
import socket
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app.tools import reminders as tool


NOW = datetime(2026, 10, 6, tzinfo=UTC)
LOCAL_DUE = datetime(2026, 10, 7, 9)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    monkeypatch.setattr(tool, "load_dotenv", Mock())
    monkeypatch.setenv("OPSFLOW_TIMEZONE", "Asia/Kolkata")


@pytest.fixture
def db(tmp_path):
    return tmp_path / "reminders.sqlite3"


def schedule(db, **changes):
    arguments = dict(task="Review the SLA", local_due=LOCAL_DUE, creation_key="request-1", db_path=db, now=NOW)
    arguments.update(changes)
    return tool.schedule_reminder(**arguments)


def stored_rows(db):
    if not db.exists():
        return []
    with sqlite3.connect(db) as connection:
        if not connection.execute("SELECT name FROM sqlite_master WHERE name = 'reminders'").fetchone():
            return []
        return connection.execute("SELECT * FROM reminders").fetchall()


def test_kolkata_default_stores_utc_and_scheduled_not_sent(db):
    result = schedule(db)
    assert result.due_at == datetime(2026, 10, 7, 3, 30, tzinfo=UTC)
    assert result.timezone == "Asia/Kolkata"
    assert result.created_at == NOW
    assert result.status == "scheduled"
    rows = stored_rows(db)
    assert len(rows) == 1
    assert rows[0][3] == "2026-10-07T03:30:00.000000+00:00"
    assert rows[0][-1] == "pending"


def test_explicit_zone_overrides_config_and_host_timezone(db, monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    result = schedule(db, timezone="America/New_York")
    assert result.due_at == datetime(2026, 10, 7, 13, tzinfo=UTC)
    assert result.timezone == "America/New_York"


def test_default_without_configuration_is_kolkata(db, monkeypatch):
    monkeypatch.delenv("OPSFLOW_TIMEZONE")
    assert schedule(db).timezone == "Asia/Kolkata"


@pytest.mark.parametrize("zone", ["Invalid/Zone", "", "../Asia/Kolkata"])
def test_invalid_zone_has_no_record(db, zone):
    with pytest.raises(ValueError):
        schedule(db, timezone=zone)
    assert not stored_rows(db)


def test_unavailable_zone_data_does_not_fall_back(db, monkeypatch):
    monkeypatch.setattr(tool, "ZoneInfo", Mock(side_effect=tool.ZoneInfoNotFoundError("private detail")))
    with pytest.raises(ValueError, match="data is unavailable") as error:
        schedule(db)
    assert "private detail" not in str(error.value)
    assert not stored_rows(db)


def test_nonexistent_dst_wall_time_is_rejected(db):
    with pytest.raises(ValueError, match="does not exist"):
        schedule(db, local_due=datetime(2027, 3, 14, 2, 30), timezone="America/New_York")
    assert not stored_rows(db)


def test_ambiguous_dst_wall_time_requires_offset_even_if_fold_set(db):
    with pytest.raises(ValueError, match="ambiguous"):
        schedule(db, local_due=datetime(2026, 11, 1, 1, 30, fold=1), timezone="America/New_York")
    assert not stored_rows(db)


@pytest.mark.parametrize(("offset", "utc_hour"), [(-240, 5), (-300, 6)])
def test_confirmed_offset_selects_each_dst_occurrence(db, offset, utc_hour):
    result = schedule(db, local_due=datetime(2026, 11, 1, 1, 30),
                      timezone="America/New_York", utc_offset_minutes=offset)
    assert result.due_at == datetime(2026, 11, 1, utc_hour, 30, tzinfo=UTC)


@pytest.mark.parametrize(("zone", "local_due", "offset"), [
    ("Asia/Kolkata", LOCAL_DUE, 300),
    ("America/New_York", datetime(2026, 11, 1, 1, 30), -360),
])
def test_offset_must_match_zone_and_local_time(db, zone, local_due, offset):
    with pytest.raises(ValueError, match="does not match"):
        schedule(db, timezone=zone, local_due=local_due, utc_offset_minutes=offset)
    assert not stored_rows(db)


def test_unambiguous_confirmed_offset_and_aware_current_instant(db):
    result = schedule(db, utc_offset_minutes=330, now=NOW.astimezone(tool.ZoneInfo("Asia/Kolkata")))
    assert result.created_at == NOW


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-1)])
def test_new_due_at_or_before_now_is_rejected(db, delta):
    with pytest.raises(ValueError, match="future"):
        schedule(db, local_due=(NOW + delta).replace(tzinfo=None), timezone="UTC")
    assert not stored_rows(db)


def test_one_microsecond_in_future_is_valid(db):
    result = schedule(db, local_due=NOW.replace(tzinfo=None) + timedelta(microseconds=1), timezone="UTC")
    assert result.due_at > NOW


def test_retry_after_due_time_returns_original_record(db):
    first = schedule(db)
    again = schedule(db, task="  Review the SLA  ", now=first.due_at + timedelta(days=2))
    assert first == again
    assert len(stored_rows(db)) == 1


@pytest.mark.parametrize("change", [
    {"task": "Call Alex"}, {"local_due": datetime(2026, 10, 8, 9)}, {"timezone": "UTC"},
])
def test_key_conflicts_do_not_change_existing_record(db, change):
    first = schedule(db)
    with pytest.raises(ValueError, match="different reminder"):
        schedule(db, **change)
    assert schedule(db) == first
    assert len(stored_rows(db)) == 1


def test_distinct_keys_allow_intentional_identical_reminders(db):
    first = schedule(db)
    second = schedule(db, creation_key="request-2")
    assert first.reminder_id != second.reminder_id
    assert len(stored_rows(db)) == 2


def test_concurrent_same_key_creation_returns_one_record(db):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: schedule(db), range(4)))
    assert all(result == results[0] for result in results)
    assert len(stored_rows(db)) == 1


def test_restart_in_new_process_recovers_original_overdue_record(db):
    first = schedule(db)
    script = """
import json, sys
from datetime import UTC, datetime
from app.tools.reminders import schedule_reminder
record = schedule_reminder('Review the SLA', datetime(2026, 10, 7, 9), 'request-1',
    timezone='Asia/Kolkata', db_path=sys.argv[1], now=datetime(2026, 10, 10, tzinfo=UTC))
print(json.dumps({'id': record.reminder_id, 'created': record.created_at.isoformat(), 'status': record.status}))
"""
    completed = subprocess.run([sys.executable, "-c", script, str(db)], cwd=tool._ROOT,
                               check=True, capture_output=True, text=True)
    assert json.loads(completed.stdout) == dict(id=first.reminder_id, created=NOW.isoformat(), status="scheduled")
    assert len(stored_rows(db)) == 1


@pytest.mark.parametrize(("field", "value", "error"), [
    ("task", None, TypeError), ("task", " \n", ValueError), ("task", "a" * 1001, ValueError),
    ("creation_key", 1, TypeError), ("creation_key", "", ValueError), ("creation_key", "a" * 129, ValueError),
    ("local_due", "tomorrow", TypeError), ("local_due", LOCAL_DUE.replace(tzinfo=UTC), ValueError),
    ("timezone", 12, TypeError), ("now", "today", TypeError), ("now", NOW.replace(tzinfo=None), ValueError),
    ("utc_offset_minutes", True, TypeError), ("utc_offset_minutes", 330.0, TypeError),
    ("utc_offset_minutes", 1440, ValueError), ("db_path", "", ValueError),
    ("db_path", ":memory:", ValueError),
])
def test_invalid_contract_inputs_have_no_record(db, field, value, error):
    with pytest.raises(error):
        schedule(db, **{field: value})
    assert not stored_rows(db)


def test_exact_text_limits(db):
    result = schedule(db, task="a" * 1000, creation_key="b" * 128)
    assert len(result.task) == 1000
    assert len(result.creation_key) == 128


def test_database_error_is_sanitized_without_success(db, monkeypatch):
    monkeypatch.setattr(tool.sqlite3, "connect", Mock(side_effect=sqlite3.OperationalError("private path")))
    with pytest.raises(tool.ReminderPersistenceError, match="persistence failed") as error:
        schedule(db)
    assert "private path" not in str(error.value)
    assert error.value.__suppress_context__
    assert not stored_rows(db)


def test_commit_failure_rolls_back_without_returning_scheduled(db, monkeypatch):
    original_connect = sqlite3.connect

    class FailingCommit(sqlite3.Connection):
        def __exit__(self, *args):
            self.rollback()
            raise sqlite3.OperationalError("private commit failure")

    monkeypatch.setattr(tool.sqlite3, "connect", lambda *args, **kwargs:
                        original_connect(*args, factory=FailingCommit, **kwargs))
    with pytest.raises(tool.ReminderPersistenceError):
        schedule(db)
    monkeypatch.setattr(tool.sqlite3, "connect", original_connect)
    assert not stored_rows(db)


def test_unwritable_database_location_reports_failure(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("not a directory")
    with pytest.raises(tool.ReminderPersistenceError):
        schedule(parent / "reminders.sqlite3")


def test_configured_database_path(db, monkeypatch):
    monkeypatch.setenv("OPSFLOW_REMINDERS_DB", str(db))
    schedule(None)
    assert len(stored_rows(db)) == 1


def test_relative_database_path_is_rooted_at_repository(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "_ROOT", tmp_path)
    schedule("var/reminders.sqlite3")
    assert len(stored_rows(tmp_path / "var/reminders.sqlite3")) == 1
