import io
import json
from threading import Event, Thread
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.chat import sessions
from app.ui import ui_client
from app.main import app
from tests.test_chat_catalogue import BASE, submit


client = TestClient(app)


def test_rename_empty_chat_survives_first_turn_and_restart(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    chat = sessions.create_chat()['session_id']
    renamed = client.patch(f'/api/v1/chats/{chat}', json={'title': '  Release **review** <today>  '})
    assert renamed.status_code == 200 and renamed.json()['title'] == 'Release **review** <today>'
    execute.assert_not_called()
    submit(chat)
    original = sessions.get_chat(chat)
    sessions.close_chat_store()
    sessions._sessions.clear()
    assert sessions.get_chat(chat) == original
    assert original['title'] == renamed.json()['title']
    assert execute.call_count == 1


def test_rename_populated_chat_keeps_exact_turns_and_delete_isolated(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    submit('one')
    submit('two', 'second')
    one, two = sessions.get_chat('one'), sessions.get_chat('two')
    assert client.patch('/api/v1/chats/one', json={'title': 'Renamed'}).status_code == 200
    assert sessions.get_chat('one')['turns'] == one['turns']
    assert client.delete('/api/v1/chats/one').json() == {'session_id': 'one'}
    assert sessions._sessions['one'].history.messages == []
    assert sessions.get_chat('one') is None and sessions.get_chat('two') == two
    sessions.close_chat_store()
    assert sessions.get_chat('one') is None
    assert sessions.get_chat('two') == two and execute.call_count == 2


@pytest.mark.parametrize('title', ['', '   ', 'x' * 121, 12, None])
def test_invalid_title_does_not_change_chat(title):
    chat = sessions.create_chat()
    response = client.patch('/api/v1/chats/' + chat['session_id'], json={'title': title})
    assert response.status_code == 422
    assert sessions.list_chats() == [chat]


@pytest.mark.parametrize('method', ['PATCH', 'DELETE'])
def test_unknown_chat_not_created_and_running_markers_block(method):
    body = {'json': {'title': 'Changed'}} if method == 'PATCH' else {}
    assert client.request(method, '/api/v1/chats/missing', **body).status_code == 404
    assert not sessions.list_chats()
    sessions._get_store().begin('one', 'Unfinished', 'unfinished')
    before = sessions.get_chat('one')
    response = client.request(method, '/api/v1/chats/one', **body)
    assert response.status_code == 409
    assert response.json()['detail']['state'] == 'running'
    assert sessions.get_chat('one') == before


def test_management_rejects_inflight_execution_without_waiting(monkeypatch):
    entered, release = Event(), Event()
    def execute(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return BASE
    monkeypatch.setattr(sessions, 'execute_request', execute)
    worker = Thread(target=lambda: sessions.execute_session_request('one', 'Work', turn_id='work'))
    worker.start()
    try:
        assert entered.wait(10)
        assert client.patch('/api/v1/chats/one', json={'title': 'Changed'}).status_code == 409
        assert client.delete('/api/v1/chats/one').status_code == 409
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive()
    assert sessions.get_chat('one')['turns'][0]['state'] == 'finished'


@pytest.mark.parametrize('operation', ['rename', 'delete'])
def test_storage_failure_rolls_back_metadata_and_turns(monkeypatch, operation):
    monkeypatch.setattr(sessions, 'execute_request', Mock(return_value=BASE))
    submit('one')
    before = sessions.get_chat('one')
    with sessions._get_store()._connection(write=True) as connection:
        command = 'UPDATE' if operation == 'rename' else 'DELETE'
        connection.execute(f"CREATE TRIGGER fail_change BEFORE {command} ON chats BEGIN SELECT RAISE(ABORT, 'private path'); END")
    response = (client.patch('/api/v1/chats/one', json={'title': 'Changed'}) if operation == 'rename'
                else client.delete('/api/v1/chats/one'))
    assert response.status_code == 503 and 'private path' not in response.text
    assert sessions.get_chat('one') == before
    assert sessions._sessions['one'].history.messages


def test_version_one_migration_retains_catalogue_and_turns(monkeypatch):
    import sqlite3
    monkeypatch.setattr(sessions, 'execute_request', Mock(return_value=BASE))
    submit('one')
    before = sessions.get_chat('one')
    path = sessions._get_store().path
    sessions.close_chat_store()
    with sqlite3.connect(path) as connection:
        connection.execute('DROP TABLE employee_profile')
        connection.execute('ALTER TABLE chats DROP COLUMN custom_title')
        connection.execute('PRAGMA user_version = 1')
    assert sessions.get_chat('one') == before
    assert sessions.rename_chat('one', 'Migrated')['title'] == 'Migrated'
    with sessions._get_store()._connection() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 3


def test_management_client_escaped_identity_and_safe_failure(monkeypatch):
    calls = []
    def send(request, timeout):
        calls.append(request)
        response = client.request(request.method, request.full_url, content=request.data,
                                  headers=dict(request.header_items()))
        stream = io.BytesIO(response.content)
        stream.status = response.status_code
        return stream
    monkeypatch.setattr(ui_client, 'urlopen', send)
    sessions._get_store().create_chat('space / 雨?')
    assert ui_client.rename_chat('http://testserver', 'space / 雨?', 'New')['title'] == 'New'
    ui_client.delete_chat('http://testserver', 'space / 雨?')
    assert sessions.get_chat('space / 雨?') is None
    assert '%2F' in calls[0].full_url and calls[0].method == 'PATCH'
    with pytest.raises(ui_client.ChatClientError, match='not found'):
        ui_client.delete_chat('http://testserver', 'space / 雨?')
    assert len(calls) == 3


@pytest.mark.parametrize('operation', ['rename', 'delete'])
def test_management_client_does_not_retry_transport_or_wrong_identity(monkeypatch, operation):
    send = Mock(side_effect=OSError('private token'))
    monkeypatch.setattr(ui_client, 'urlopen', send)
    args = ('http://testserver', 'one', 'New') if operation == 'rename' else ('http://testserver', 'one')
    function = getattr(ui_client, operation + '_chat')
    with pytest.raises(ui_client.ChatClientError, match='could not be confirmed'):
        function(*args)
    assert send.call_count == 1
    payload = {'session_id': 'other'}
    if operation == 'rename':
        payload.update(title='New', created_at='now', updated_at='now')
    stream = io.BytesIO(json.dumps(payload).encode())
    stream.status = 200
    send.side_effect = None
    send.return_value = stream
    with pytest.raises(ui_client.ChatClientError, match='different chat'):
        function(*args)
