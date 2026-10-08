"""Durable lifecycle checks with synthetic executions and temporary local storage."""

import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app import sessions, ui_client
from app.agent import AgentTrace
from app.chat_store import ChatPersistenceError, ChatStore, ChatTurnConflict
from app.main import app
from app.runtime import ExecutionResult, RuntimeUnavailable


BASE = ExecutionResult('completed', 'sentiment_analysis', 1, 'direct', 'direct', None, [], 0, reply='Done')
ROOT = Path(__file__).resolve().parents[1]


def restart():
    sessions.close_chat_store()
    sessions._sessions.clear()


def child(source, path):
    return subprocess.run([sys.executable, '-c', source], cwd=ROOT,
                          env={**os.environ, 'OPSFLOW_CHATS_DB': str(path)},
                          capture_output=True, text=True, timeout=15)


def test_fresh_process_restores_exact_context_without_reexecuting(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    source = '  Synthetic source\nkept exactly  '
    first = sessions.execute_session_request('one', source, turn_id='first')
    path = sessions._get_store().path
    restart()
    result = child('''
import json
from dataclasses import asdict
from app import sessions
from app.runtime import ExecutionResult
seen = []
def execute(message, *, history):
    seen.append([turn.content for turn in history])
    return ExecutionResult('completed', 'email_drafting', 1, 'agent', 'intent_requires_agent', None, [], 0, reply='Follow-up')
sessions.execute_request = execute
sessions.execute_session_request('one', 'Continue', turn_id='second')
print(json.dumps(seen))
''', path)
    assert result.returncode == 0, result.stderr
    seen = json.loads(result.stdout)
    assert len(seen) == 1 and seen[0][0] == source
    assert json.loads(seen[0][1]) == asdict(first)
    assert execute.call_count == 1
    turns = sessions._get_store().turns('one')
    assert [turn['sequence'] for turn in turns] == [1, 2]
    assert [turn['message'] for turn in turns] == [source, 'Continue']
    assert all(turn['state'] == 'finished' for turn in turns)


def test_duplicate_id_replays_exact_outcome_after_restart_and_conflicts(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    first = sessions.execute_session_request('one', 'Synthetic text', turn_id='same')
    restart()
    second = sessions.execute_session_request('one', 'Synthetic text', turn_id='same')
    assert asdict(first) == asdict(second)
    assert execute.call_count == 1 and len(sessions._get_store().turns('one')) == 1
    for session_id, message in [('one', 'Changed'), ('two', 'Synthetic text')]:
        with pytest.raises(ChatTurnConflict):
            sessions.execute_session_request(session_id, message, turn_id='same')
    assert execute.call_count == 1 and sessions._get_store().turns('two') == []


def test_concurrent_duplicate_and_distinct_same_text(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(sessions.execute_session_request, 'one', 'Text', turn_id='same') for _ in range(2)]
        results = [task.result(timeout=5) for task in tasks]
    assert results[0] == results[1] and execute.call_count == 1
    sessions.execute_session_request('one', 'Text', turn_id='intentional-new')
    assert execute.call_count == 2 and len(sessions._get_store().turns('one')) == 2


def test_abrupt_process_exit_recovers_unknown_and_never_retries(monkeypatch, tmp_path):
    path = tmp_path / 'chats.sqlite3'
    result = child('''
import os
from app.chat_store import ChatStore, database_path
store = ChatStore(database_path())
store.begin('one', 'Unfinished source', 'unfinished')
os._exit(7)
''', path)
    assert result.returncode == 7
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    store = sessions._get_store()
    interrupted = store.turns('one')[0]
    assert interrupted['state'] == 'interrupted' and interrupted['execution'] is None
    assert interrupted['finished_at'] is None and interrupted['failure_reason'] == 'interrupted'
    with pytest.raises(ChatTurnConflict):
        sessions.execute_session_request('one', 'Unfinished source', turn_id='unfinished')
    assert not execute.called
    sessions.execute_session_request('one', 'What happened?', turn_id='new')
    history = execute.call_args.kwargs['history']
    assert history[0].content == 'Unfinished source'
    previous = json.loads(history[1].content)
    assert previous['reason'] == 'interrupted' and previous['trace'] == []
    assert 'unknown' in previous['reply']


def test_second_process_cannot_recover_live_marker():
    store = sessions._get_store()
    store.begin('one', 'Still running', 'live')
    result = child('''
from app.chat_store import ChatStore, ChatPersistenceError, database_path
try:
    ChatStore(database_path())
except ChatPersistenceError:
    print('excluded')
else:
    raise AssertionError('Second owner accepted')
''', store.path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'excluded'
    assert store.turns('one')[0]['state'] == 'running'
    with pytest.raises(ChatTurnConflict):
        sessions.clear_session_history('one')


@pytest.mark.parametrize('phase', ['begin', 'finish'])
def test_failed_commit_rolls_back_and_never_uses_unsaved_context(monkeypatch, phase):
    store = sessions._get_store()
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    connect = sqlite3.connect

    class FailedCommit:
        def __init__(self, *args, **kwargs):
            self.connection = connect(*args, **kwargs)
            self.fail = False

        @property
        def row_factory(self):
            return self.connection.row_factory

        @row_factory.setter
        def row_factory(self, value):
            self.connection.row_factory = value

        def execute(self, sql, parameters=()):
            if (phase == 'begin' and 'INSERT INTO chat_turns' in sql
                    or phase == 'finish' and "UPDATE chat_turns SET state='finished'" in sql):
                self.fail = True
            return self.connection.execute(sql, parameters)

        def __enter__(self):
            return self

        def __exit__(self, kind, error, traceback):
            if kind is None and self.fail:
                self.connection.rollback()
                raise sqlite3.OperationalError('private simulated commit failure')
            return self.connection.__exit__(kind, error, traceback)

        def close(self):
            self.connection.close()

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, 'connect', FailedCommit)
        response = TestClient(app).post('/api/v1/chat', json={'session_id': 'one', 'message': 'Synthetic'})
    assert response.status_code == 503
    detail = response.json()['detail']
    assert detail['code'] == 'chat_persistence' and 'private' not in json.dumps(detail)
    assert detail['outcome'] == ('not_started' if phase == 'begin' else 'unsaved')
    assert execute.call_count == (0 if phase == 'begin' else 1)
    assert sessions._sessions['one'].history.messages == []
    turns = store.turns('one')
    if phase == 'begin':
        assert turns == []
        with connect(store.path) as connection:
            assert connection.execute('SELECT * FROM chats').fetchall() == []
    else:
        assert turns[0]['state'] == 'running' and turns[0]['execution'] is None
        with pytest.raises(ChatTurnConflict):
            sessions.execute_session_request('one', 'Another')
        assert execute.call_count == 1
        restart()
        assert sessions._get_store().turns('one')[0]['state'] == 'interrupted'


def test_failed_read_blocks_execution_and_corrupt_record_is_not_discarded(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    sessions.execute_session_request('one', 'Synthetic')
    store = sessions._get_store()
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE chat_turns SET execution_json='not json'")
    with pytest.raises(ChatPersistenceError):
        sessions.execute_session_request('one', 'Follow up')
    assert execute.call_count == 1
    with sqlite3.connect(store.path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM chat_turns').fetchone()[0] == 1
        connection.execute("UPDATE chat_turns SET execution_json='{}'")
    with pytest.raises(ChatPersistenceError):
        sessions.execute_session_request('one', 'Follow up')
    assert execute.call_count == 1


def test_unexpected_execution_failure_leaves_unknown_marker_and_sanitized_reply(monkeypatch):
    execute = Mock(side_effect=RuntimeError('private unexpected failure'))
    monkeypatch.setattr(sessions, 'execute_request', execute)
    response = TestClient(app).post('/api/v1/chat', json={'session_id': 'one', 'message': 'Synthetic'})
    assert response.status_code == 503 and response.json()['detail']['outcome'] == 'unsaved'
    assert 'private' not in response.text
    assert sessions._get_store().turns('one')[0]['state'] == 'running'
    with pytest.raises(ChatTurnConflict):
        sessions.execute_session_request('one', 'Another')
    assert execute.call_count == 1


def test_runtime_failure_replays_without_reexecution_and_retains_context(monkeypatch):
    execute = Mock(side_effect=RuntimeUnavailable('Intent classifier unavailable'))
    monkeypatch.setattr(sessions, 'execute_request', execute)
    for _ in range(2):
        with pytest.raises(RuntimeUnavailable):
            sessions.execute_session_request('one', 'Synthetic', turn_id='same')
        restart()
    assert execute.call_count == 1
    execute.side_effect = None
    execute.return_value = BASE
    sessions.execute_session_request('one', 'Continue')
    previous = json.loads(execute.call_args.kwargs['history'][1].content)
    assert previous['reason'] == 'runtime_unavailable' and previous['trace'] == []


@pytest.mark.parametrize('status', ['completed', 'needs_clarification', 'partial_failure', 'error'])
def test_restoration_preserves_status_results_reasons_and_demo_marker(monkeypatch, status):
    trace = [AgentTrace('retrieve_faq', {'question': 'Synthetic policy question'}, 'completed',
                       {'status': 'matched', 'answer': 'Fictional answer', 'is_demo': True}, None, 1.23456789)]
    if status in {'partial_failure', 'error'}:
        trace.append(AgentTrace('draft_email', {'recipient': 'Alex', 'content': 'Fictional answer'},
                                'failed', None, 'provider_unavailable', 2.3456789))
    outcome = ExecutionResult(status, 'email_drafting', .8, 'agent', 'intent_requires_agent',
                              None, trace, 0, reply='Synthetic reply', agent_reason='provider_unavailable')
    execute = Mock(return_value=outcome)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    original = sessions.execute_session_request('one', 'Synthetic', turn_id='one-turn')
    restart()
    replay = sessions.execute_session_request('one', 'Synthetic', turn_id='one-turn')
    assert asdict(replay) == asdict(original) and execute.call_count == 1
    sessions.execute_session_request('one', 'Follow up', turn_id='follow-up')
    previous = execute.call_args.kwargs['history'][1]
    assert json.loads(previous.content) == asdict(original)
    assert previous.additional_kwargs['opsflow_demo_policy'] is True


def test_workflow_result_and_stage_records_survive_restart(monkeypatch, sentiment_provider):
    from app import runtime

    sentiment_provider('I am happy', 'Synthetic positive explanation')
    monkeypatch.setattr(runtime, 'classify_request', lambda message: ('sentiment_analysis', 1, .71))
    original = sessions.execute_session_request('one', 'Check sentiment: I am happy', turn_id='workflow')
    assert original.route == 'llm_assisted' and len(original.workflow_trace) == 3
    restart()
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    replay = sessions.execute_session_request('one', 'Check sentiment: I am happy', turn_id='workflow')
    assert asdict(replay) == asdict(original) and not execute.called
    sessions.execute_session_request('one', 'Follow up')
    assert json.loads(execute.call_args.kwargs['history'][1].content) == asdict(original)


def test_durable_clear_does_not_resurrect_context_or_reset_sequence(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, 'execute_request', execute)
    sessions.execute_session_request('one', 'Synthetic')
    sessions.execute_session_request('two', 'Independent')
    sessions.clear_session_history('one')
    restart()
    sessions.execute_session_request('one', 'New context')
    assert execute.call_args.kwargs['history'] == []
    assert sessions._get_store().turns('one')[0]['sequence'] == 2
    assert sessions._get_store().turns('two')[0]['message'] == 'Independent'


def test_failed_clear_preserves_history_and_records(monkeypatch):
    monkeypatch.setattr(sessions, 'execute_request', Mock(return_value=BASE))
    sessions.execute_session_request('one', 'Synthetic')
    store = sessions._get_store()
    with sqlite3.connect(store.path) as connection:
        connection.execute("CREATE TRIGGER fail_clear BEFORE DELETE ON chat_turns BEGIN SELECT RAISE(ABORT, 'private'); END")
    with pytest.raises(ChatPersistenceError):
        sessions.clear_session_history('one')
    assert len(sessions._sessions['one'].history.messages) == 2
    assert len(store.turns('one')) == 1


@pytest.mark.parametrize('schema', ['future', 'foreign'])
def test_unsupported_schema_is_not_modified(tmp_path, schema):
    path = tmp_path / 'unsupported.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE reminders (task TEXT)')
        connection.execute("INSERT INTO reminders VALUES ('Synthetic sentinel')")
        if schema == 'future':
            connection.execute('PRAGMA user_version = 99')
    with pytest.raises(ChatPersistenceError):
        ChatStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT * FROM reminders').fetchall() == [('Synthetic sentinel',)]
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('reminders',)]


@pytest.mark.parametrize('outcome,wording', [('not_started', 'No new turn'), ('unsaved', 'not saved')])
def test_client_discloses_storage_failure_without_retry_or_private_text(monkeypatch, outcome, wording):
    response = io.BytesIO(json.dumps({'detail': {
        'code': 'chat_persistence', 'outcome': outcome, 'message': 'private server data',
    }}).encode())
    response.status = 503
    send = Mock(return_value=response)
    monkeypatch.setattr(ui_client, 'urlopen', send)
    with pytest.raises(ui_client.ChatClientError, match=wording) as error:
        ui_client.submit_chat('http://localhost', 'one', 'Synthetic')
    assert 'private' not in str(error.value) and send.call_count == 1


@pytest.mark.parametrize('turn_id', ['', ' ', 'x' * 129, 2])
def test_invalid_turn_identity_does_not_initialize_storage(monkeypatch, turn_id):
    execute = Mock()
    monkeypatch.setattr(sessions, 'execute_request', execute)
    with pytest.raises((TypeError, ValueError)):
        sessions.execute_session_request('one', 'Synthetic', turn_id=turn_id)
    assert sessions._store is None and sessions._sessions == {} and not execute.called
