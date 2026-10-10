import json
import sqlite3
from pathlib import Path
from datetime import UTC, datetime
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.reminders.reminder_catalogue import list_saved_reminders
from app.tools.reminders import ReminderPersistenceError, schedule_reminder
from app.ui import ui_client
from tests.test_streamlit_ui import Response


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "reminders #local.sqlite3"
    monkeypatch.setenv("OPSFLOW_REMINDERS_DB", str(path))
    return path


def seed(path, state="pending", key="one", timezone="Asia/Kolkata"):
    record = schedule_reminder("Review **literal**\nSecond line", datetime(2026, 11, 1, 9), key,
                              timezone=timezone, db_path=path, now=datetime(2026, 10, 1, tzinfo=UTC))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE reminders SET state=? WHERE reminder_id=?", (state, record.reminder_id))
    return record


def test_missing_database_is_empty_without_creating_storage(database):
    assert list_saved_reminders() == []
    assert not database.exists() and not database.with_suffix(".lock").exists()
    assert TestClient(app).get("/api/v1/reminders").json() == []


def test_snapshot_preserves_all_worker_states_and_does_not_initialize_worker(database):
    states = ["pending", "submitting", "retry", "accepted", "failed", "unknown"]
    for index, state in enumerate(states):
        seed(database, state, str(index), "America/New_York" if index == 1 else "Asia/Kolkata")
    before = database.read_bytes()
    records = list_saved_reminders()
    assert {record.state for record in records} == set(states)
    assert records == sorted(records, key=lambda record: (record.due_at, record.reminder_id))
    assert all(record.task == "Review **literal**\nSecond line" for record in records)
    client = TestClient(app)
    payload = client.get("/api/v1/reminders").json()
    assert ui_client.SavedReminder.model_validate_json(json.dumps(payload[0])) == records[0]
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='reminder_attempts'").fetchall() == []
    assert not Path(str(database) + ".lock").exists()
    assert client.post("/api/v1/reminders", json={}).status_code == 405


@pytest.mark.parametrize("corruption", ["not sqlite", "no schema", "state", "timezone", "due_at", "task"])
def test_invalid_storage_has_safe_failure_and_is_not_repaired(database, corruption):
    if corruption == "not sqlite":
        database.write_text("private broken database")
    elif corruption == "no schema":
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
    else:
        seed(database)
        value = {"state": "sent", "timezone": "Private/Invalid", "due_at": "2026-11-01T09:00:00", "task": " "}[corruption]
        with sqlite3.connect(database) as connection:
            connection.execute(f"UPDATE reminders SET {corruption}=?", (value,))
    before = database.read_bytes()
    with pytest.raises(ReminderPersistenceError, match="could not be loaded"):
        list_saved_reminders()
    response = TestClient(app).get("/api/v1/reminders")
    assert response.status_code == 503 and response.json() == {"detail": "Saved reminders could not be loaded"}
    assert database.read_bytes() == before


def test_client_get_roundtrip_and_no_retry(database, monkeypatch):
    seed(database)
    payload = TestClient(app).get("/api/v1/reminders").json()
    send = Mock(return_value=Response(payload))
    monkeypatch.setattr(ui_client, "urlopen", send)
    assert ui_client.list_reminders("http://localhost/") == payload
    assert send.call_args.args[0].method == "GET"
    assert send.call_args.args[0].full_url == "http://localhost/api/v1/reminders"
    assert send.call_count == 1


@pytest.mark.parametrize("failure", [URLError("private"), TimeoutError("private"), [{"state": "sent"}],
                                      [{"reminder_id": "x", "task": "x", "due_at": "2026-11-01T09:00:00Z",
                                        "timezone": "Private/Invalid", "created_at": "2026-10-01T09:00:00Z", "state": "pending"}]])
def test_client_safe_errors(monkeypatch, failure):
    send = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=Response(failure))
    monkeypatch.setattr(ui_client, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError, match="Saved reminders could not be loaded"):
        ui_client.list_reminders("http://localhost")
    assert send.call_count == 1
