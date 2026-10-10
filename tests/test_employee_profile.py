import json
import os
import sqlite3
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.chat import sessions
from app.chat.chat_store import ChatStore
from app.ui.email_catalogue import saved_email_entries
from app.main import app
from tests.test_chat_catalogue import BASE
from tests.test_email_catalogue import chat as draft_chat
from tests.test_reminder_catalogue import seed


client = TestClient(app)
EXPECTED = dict(profile_id="EMP-001", name="Sachin Tendulkar", role="Operations Associate",
                company="OpsFlow Demo Company", timezone="Asia/Kolkata", is_demo=True)


def test_singleton_survives_fresh_process_without_execution(monkeypatch):
    execute = Mock(side_effect=AssertionError("Read executed work"))
    monkeypatch.setattr(sessions, "execute_request", execute)
    assert client.get("/api/v1/profile").json() == EXPECTED
    assert client.get("/api/v1/profile").json() == EXPECTED
    store = sessions._get_store()
    with store._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM employee_profile").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 0
    sessions.close_chat_store()
    result = subprocess.run([os.path.abspath('.venv/bin/python'), '-c',
        'from app.chat.sessions import get_profile, close_chat_store; '
        'print(get_profile().model_dump_json()); close_chat_store()'],
        capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == EXPECTED
    execute.assert_not_called()


def test_version_two_migration_preserves_saved_turns_and_titles(monkeypatch):
    monkeypatch.setattr(sessions, "execute_request", Mock(return_value=BASE))
    sessions.execute_session_request("retained", "Exact message", turn_id="retained-turn")
    sessions.rename_chat("retained", "Custom title")
    path = sessions._get_store().path
    before = sessions.get_chat("retained")
    sessions.close_chat_store()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE employee_profile")
        connection.execute("PRAGMA user_version=2")
    assert client.get("/api/v1/profile").json() == EXPECTED
    assert sessions.get_chat("retained") == before
    assert client.get("/api/v1/chats/retained").json()["profile_id"] == "EMP-001"
    assert client.get("/api/v1/chats").json()[0]["profile_id"] == "EMP-001"
    assert client.post("/api/v1/chats", json={}).json()["profile_id"] == "EMP-001"


def test_existing_reminders_and_saved_drafts_share_identity_without_writes(tmp_path):
    path = tmp_path / 'reminders.sqlite3'
    seed(path, "unknown")
    before = path.read_bytes()
    from app.reminders.reminder_catalogue import list_saved_reminders
    records = list_saved_reminders(path)
    assert records[0].profile_id == EXPECTED["profile_id"]
    assert records[0].state == "unknown" and path.read_bytes() == before
    drafts, unavailable = saved_email_entries([draft_chat()])
    assert drafts[0]["profile_id"] == EXPECTED["profile_id"] and unavailable == 0
    assert drafts[0]["draft"]["recipient"] == "Alex"


@pytest.mark.parametrize('corruption', ['missing', 'name', 'foreign_schema'])
def test_profile_storage_failure_is_explicit_and_not_reseeded(corruption):
    path = sessions._get_store().path
    sessions.close_chat_store()
    with sqlite3.connect(path) as connection:
        if corruption == 'missing':
            connection.execute('DELETE FROM employee_profile')
        elif corruption == 'name':
            connection.execute("UPDATE employee_profile SET name=''")
        else:
            connection.execute('PRAGMA user_version=99')
    response = client.get('/api/v1/profile')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Employee profile could not be loaded.'}


def test_failed_migration_rolls_back_without_touching_records(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    store = ChatStore(path)
    store.create_chat('retained')
    store.close()
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version=2')
    from app.chat.chat_store import ChatPersistenceError
    with pytest.raises(ChatPersistenceError):
        ChatStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert connection.execute('SELECT session_id FROM chats').fetchone()[0] == 'retained'


def test_profile_has_no_mutation_api():
    for method in ["POST", "PATCH", "DELETE"]:
        assert client.request(method, "/api/v1/profile").status_code == 405
