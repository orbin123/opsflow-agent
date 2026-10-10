"""Local, process-scoped metrics and content-free correlated JSON logs."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from datetime import datetime, timezone
import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.responses import JSONResponse

from prometheus_client import CollectorRegistry, Counter, Histogram


registry = CollectorRegistry()
requests = Counter('opsflow_http_requests_total', 'HTTP responses, including stream transports.',
                   ['method', 'route', 'status'], registry=registry)
http_outcomes = Counter('opsflow_http_outcomes_total', 'HTTP outcomes initialized before first scrape.',
                        ['outcome'], registry=registry)
for outcome in ('server_error', 'other'):
    http_outcomes.labels(outcome)
request_seconds = Histogram('opsflow_http_request_duration_seconds', 'Full HTTP lifetime including streaming.',
                            ['method', 'route'], registry=registry,
                            buckets=(.01, .05, .1, .5, 1, 5, 15, 30, 60, 120, 300))
tasks = Counter('opsflow_tasks_total', 'New runtime executions; excludes saved replay.',
                ['intent', 'route', 'outcome'], registry=registry)
task_outcomes = Counter('opsflow_task_outcomes_total', 'Runtime outcomes initialized before first scrape.',
                        ['outcome'], registry=registry)
for outcome in ('completed', 'agent_required', 'needs_clarification', 'partial_failure', 'error'):
    task_outcomes.labels(outcome)
task_seconds = Histogram('opsflow_task_duration_seconds', 'Runtime duration excluding persistence.',
                         ['route'], registry=registry, buckets=(.1, .5, 1, 5, 15, 30, 60, 120, 300))
tools = Counter('opsflow_tool_calls_total', 'Actual completed or failed tool calls.',
                ['tool', 'outcome'], registry=registry)
tool_seconds = Histogram('opsflow_tool_duration_seconds', 'Recorded tool execution duration.',
                         ['tool'], registry=registry, buckets=(.001, .01, .1, 1, 5, 15, 30, 60, 120))
persistence = Counter('opsflow_turn_persistence_total', 'Finalization of newly accepted chat turns.',
                      ['outcome'], registry=registry)
_request_id = ContextVar('monitoring_request_id', default=None)
logger = logging.getLogger('opsflow.monitoring')
# Only this dedicated logger is configured; provider and application logs are not ingested.
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
INTENTS = {'sentiment_analysis', 'keyword_extraction', 'faq_retrieval', 'summarization',
           'email_drafting', 'reminder_creation', 'compound_request', 'out_of_scope'}
TOOLS = {'analyze_sentiment', 'extract_keywords', 'retrieve_faq', 'summarize_text',
         'draft_email', 'schedule_reminder'}
ROUTES = {'direct', 'llm_assisted', 'agent'}
OUTCOMES = {'completed', 'agent_required', 'needs_clarification', 'partial_failure', 'error'}


def log(event, *, failed=False, **fields):
    logger.log(logging.ERROR if failed else logging.INFO,
               json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, 'request_id': _request_id.get(), **fields},
                          allow_nan=False, separators=(',', ':')))


def record_tool(record):
    name = getattr(record, 'tool', getattr(record, 'stage', None))
    if name not in TOOLS:
        return
    outcome = 'completed' if record.status == 'completed' else 'failed'
    tools.labels(name, outcome).inc()
    tool_seconds.labels(name).observe(record.elapsed_ms / 1000)
    log('tool_finished', failed=outcome == 'failed', tool=name, outcome=outcome,
        duration_seconds=record.elapsed_ms / 1000)


def track_execution(fn):
    @wraps(fn)
    def tracked(*args, **kwargs):
        started = perf_counter()
        intent, route, outcome = 'unknown', 'unknown', 'error'
        try:
            result = fn(*args, **kwargs)
            intent = result.predicted_intent if result.predicted_intent in INTENTS else 'unknown'
            route = result.route if result.route in ROUTES else 'unknown'
            outcome = result.status if result.status in OUTCOMES else 'error'
            # Direct FAQ has no workflow step events.
            if route == 'direct':
                for step in result.trace:
                    record_tool(step)
            return result
        finally:
            duration = perf_counter() - started
            tasks.labels(intent, route, outcome).inc()
            task_outcomes.labels(outcome).inc()
            task_seconds.labels(route).observe(duration)
            log('task_finished', failed=outcome in {'error', 'partial_failure'},
                intent=intent, route=route, outcome=outcome, duration_seconds=duration)
    return tracked


@contextmanager
def track_persistence():
    # Enter only after durable acceptance, never on a saved replay.
    try:
        yield
    except Exception as error:
        from app.chat.chat_store import ChatPersistenceError
        from app.core.runtime import RuntimeUnavailable
        outcome = ('unsaved' if isinstance(error, ChatPersistenceError) else
                   'saved_failure' if isinstance(error, RuntimeUnavailable) else 'unknown')
        persistence.labels(outcome).inc()
        log('turn_persistence', failed=True, outcome=outcome)
        raise
    else:
        persistence.labels('saved').inc()
        log('turn_persistence', outcome='saved')


class RequestMonitoring:
    """Pure ASGI middleware preserves context across streaming/thread workers."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        token = _request_id.set(request_id)
        started = perf_counter()
        status = 500
        failure = None
        response_started = False

        async def tracked_send(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
                message = {**message, 'headers': [*message.get('headers', []),
                                                 (b'x-request-id', request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            failure = 'unhandled_error'
            if response_started:
                raise
            await JSONResponse({'detail': 'Internal server error'}, status_code=500)(scope, receive, tracked_send)
        finally:
            route = getattr(scope.get('route'), 'path', 'unmatched')
            method = scope['method'] if scope['method'] in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'} else 'OTHER'
            duration = perf_counter() - started
            # Scrapes do not inflate API usage; still get correlation headers.
            if route != '/metrics':
                requests.labels(method, route, str(status)).inc()
                http_outcomes.labels('server_error' if status >= 500 else 'other').inc()
                request_seconds.labels(method, route).observe(duration)
                log('request_finished', failed=status >= 500 or failure is not None,
                    method=method, route=route, status=status,
                    failure_code=failure or ('http_error' if status >= 400 else None),
                    duration_seconds=duration)
            _request_id.reset(token)
