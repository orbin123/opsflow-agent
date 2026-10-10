"""Metrics protect correlation, actual execution counts and content boundaries."""
import asyncio
import json
import logging
from threading import Event

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.observability import monitoring as m
from app.core import runtime
from app.chat import sessions
from app.core.execution_events import finish_step
from app.main import app
from app.core.runtime import ExecutionResult, RuntimeUnavailable, ToolTrace
from app.chat.chat_store import ChatPersistenceError
from app.chat.chat_stream import stream_turn, drain_stream_workers


@pytest.fixture
def logs():
    records = []
    class Capture(logging.Handler):
        def emit(self, record):
            records.append(json.loads(record.getMessage()))
    handler = Capture()
    m.logger.addHandler(handler)
    yield records
    m.logger.removeHandler(handler)


def sample(metric, labels):
    return metric._metrics[tuple(labels)]._value.get() if tuple(labels) in metric._metrics else 0


def completed():
    return ExecutionResult('completed', 'sentiment_analysis', .9, 'llm_assisted', 'done',
                           None, [], 2, 'Safe reply')


def test_requests_templates_headers_and_sanitized_errors(logs):
    demo = FastAPI()
    demo.add_middleware(m.RequestMonitoring)
    @demo.get('/items/{item_id}')
    def item(item_id: str):
        if item_id == 'fail':
            raise ValueError('SECRET token private message')
        return {'ok': True}
    errors_before = sample(m.http_outcomes, ['server_error'])
    before = sample(m.requests, ['GET', '/items/{item_id}', '200'])
    with TestClient(demo) as client:
        first = client.get('/items/private-one?token=SECRET', headers={'X-Request-ID': 'SECRET'})
        second = client.get('/items/private-two')
        failure = client.get('/items/fail')
    assert first.headers['x-request-id'] != second.headers['x-request-id']
    assert len(first.headers['x-request-id']) == 32
    assert failure.status_code == 500 and failure.headers['x-request-id']
    assert failure.json() == {'detail': 'Internal server error'}
    assert sample(m.requests, ['GET', '/items/{item_id}', '200']) == before + 2
    assert logs[-1]['failure_code'] == 'unhandled_error'
    assert sample(m.http_outcomes, ['server_error']) == errors_before + 1
    assert 'SECRET' not in json.dumps(logs) and 'private-' not in json.dumps(logs)


def test_validation_unmatched_and_scrape_exclusion(logs):
    with TestClient(app) as client:
        validation = client.post('/api/v1/chat', json={'message': 'SECRET'})
        client.get('/unknown/SECRET')
        scrape = client.get('/metrics')
    assert validation.status_code == 422 and validation.headers['x-request-id']
    assert logs[-1]['route'] == 'unmatched'
    assert 'SECRET' not in json.dumps(logs)
    assert scrape.status_code == 200 and 'text/plain' in scrape.headers['content-type']
    assert 'route="/metrics"' not in scrape.text


@pytest.mark.parametrize('status', ['completed', 'needs_clarification', 'partial_failure', 'error'])
def test_task_outcomes_bounded_labels_and_no_content(status, logs):
    result = completed()
    result = ExecutionResult(status, result.predicted_intent, .9, result.route, 'SECRET',
                             None, [], 2, 'SECRET')
    aggregate_before = sample(m.task_outcomes, [status])
    before = sample(m.tasks, ['sentiment_analysis', 'llm_assisted', status])
    wrapped = m.track_execution(lambda message: result)
    assert wrapped('SECRET') is result
    assert sample(m.tasks, ['sentiment_analysis', 'llm_assisted', status]) == before + 1
    assert sample(m.task_outcomes, [status]) == aggregate_before + 1
    assert 'SECRET' not in json.dumps(logs)


def test_runtime_failure_and_unknown_labels(logs):
    def fail(message):
        raise RuntimeUnavailable('SECRET')
    before = sample(m.tasks, ['unknown', 'unknown', 'error'])
    with pytest.raises(RuntimeUnavailable):
        m.track_execution(fail)('SECRET')
    assert sample(m.tasks, ['unknown', 'unknown', 'error']) == before + 1
    weird = ExecutionResult('completed', 'SECRET', .9, 'SECRET', 'SECRET', None, [], 1)
    m.track_execution(lambda: weird)()
    assert logs[-1]['intent'] == logs[-1]['route'] == 'unknown'
    assert 'SECRET' not in json.dumps(logs)


def test_real_workflow_tool_count_without_stream_observer(monkeypatch, sentiment_provider, logs):
    monkeypatch.setattr(runtime, 'classify_request', lambda _: ('sentiment_analysis', .9, .71))
    sentiment_provider('I am happy')
    before = sample(m.tools, ['analyze_sentiment', 'completed'])
    runtime.execute_request('Analyze sentiment: I am happy')
    assert sample(m.tools, ['analyze_sentiment', 'completed']) == before + 1
    assert logs[-2]['event'] == 'tool_finished'


def test_failed_tool_content_is_not_logged(logs):
    before = sample(m.tools, ['draft_email', 'failed'])
    finish_step(None, ToolTrace('draft_email', {'text': 'SECRET'}, 'failed', None, 3))
    assert sample(m.tools, ['draft_email', 'failed']) == before + 1
    assert 'SECRET' not in json.dumps(logs)


def test_saved_replay_and_reads_do_not_count(monkeypatch, logs):
    monkeypatch.setattr(sessions, 'execute_request', m.track_execution(lambda *a, **kw: completed()))
    with TestClient(app) as client:
        chat = client.post('/api/v1/chats', json={}).json()['session_id']
        body = {'session_id': chat, 'turn_id': 'same', 'message': 'SECRET'}
        first = client.post('/api/v1/chat', json=body)
        second = client.post('/api/v1/chat', json=body)
        client.get('/api/v1/chats')
        client.get('/api/v1/chats/' + chat)
    assert first.status_code == second.status_code == 200
    executions = [r for r in logs if r['event'] == 'task_finished']
    assert len(executions) == 1
    assert executions[0]['request_id'] == first.headers['x-request-id']
    assert len([r for r in logs if r['event'] == 'turn_persistence']) == 1


def test_unsaved_failure_logs_persistence_separately(monkeypatch, logs):
    monkeypatch.setattr(sessions, 'execute_request', m.track_execution(lambda *a, **kw: completed()))
    chat = sessions.create_chat()['session_id']
    def fail(*a, **kw):
        raise ChatPersistenceError('SECRET')
    monkeypatch.setattr(sessions._get_store(), 'finish', fail)
    with pytest.raises(ChatPersistenceError):
        sessions.execute_session_request(chat, 'SECRET', turn_id='unsaved')
    assert logs[-1]['outcome'] == 'unsaved'
    assert logs[-2]['outcome'] == 'completed'
    assert 'SECRET' not in json.dumps(logs)


def test_sse_http_200_retains_task_error_and_correlation(monkeypatch, logs):
    result = completed()
    result = ExecutionResult('error', result.predicted_intent, .9, result.route, 'error', None, [], 2)
    monkeypatch.setattr('app.api.chat.execute_session_request', m.track_execution(lambda *a, **kw: result))
    with TestClient(app) as client:
        response = client.post('/api/v1/chat/stream', json={'session_id': 'demo', 'message': 'SECRET'})
    assert response.status_code == 200 and '"http_status": 503' in response.text
    task = next(r for r in logs if r['event'] == 'task_finished')
    assert task['outcome'] == 'error' and task['request_id'] == response.headers['x-request-id']
    assert logs[-1]['status'] == 200


def test_disconnected_stream_worker_finishes_once(logs):
    ready, release = Event(), Event()
    @m.track_execution
    def execute(*a, **kw):
        ready.set()
        assert release.wait(5)
        return completed()
    async def scenario():
        token = m._request_id.set('correlated')
        try:
            stream = stream_turn('demo', 'SECRET', 'turn', execute)
            assert 'event: turn' in await anext(stream)
            assert await asyncio.to_thread(ready.wait, 5)
            await stream.aclose()
            release.set()
            await drain_stream_workers()
        finally:
            m._request_id.reset(token)
    asyncio.run(scenario())
    assert len(logs) == 1 and logs[0]['request_id'] == 'correlated'
    assert logs[0]['outcome'] == 'completed'


def test_concurrent_requests_keep_independent_worker_context(logs):
    async def scenario():
        gate = asyncio.Event()
        entered = 0
        async def endpoint(scope, receive, send):
            nonlocal entered
            entered += 1
            if entered == 2:
                gate.set()
            await gate.wait()
            await asyncio.to_thread(m.log, 'worker')
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'ok'})
        middleware = m.RequestMonitoring(endpoint)
        async def request():
            messages = []
            async def send(message):
                messages.append(message)
            async def receive():
                return {'type': 'http.request', 'body': b''}
            await middleware({'type': 'http', 'method': 'GET'}, receive, send)
            return dict(messages[0]['headers'])[b'x-request-id'].decode()
        return await asyncio.gather(request(), request())
    ids = asyncio.run(scenario())
    assert len(set(ids)) == 2
    assert {r['request_id'] for r in logs if r['event'] == 'worker'} == set(ids)
    assert m._request_id.get() is None


def test_stream_preexecution_failure_logs_safe_code(logs):
    def execute(*a, **kw):
        raise ChatPersistenceError('SECRET')
    async def scenario():
        events = [item async for item in stream_turn('demo', 'SECRET', 'turn', execute)]
        await drain_stream_workers()
        return events
    assert 'event: failure' in asyncio.run(scenario())[-1]
    assert len(logs) == 1
    assert logs[0]['failure_code'] == 'chat_persistence'
    assert 'SECRET' not in json.dumps(logs)
