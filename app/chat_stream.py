"""SSE transport with execution owned by the backend, not its subscriber."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from app.chat_store import ChatPersistenceError, ChatTurnConflict
from app.execution_events import EventEmitter, observe_events
from app.monitoring import log
from app.runtime import RuntimeUnavailable


_workers: set[asyncio.Task] = set()


async def drain_stream_workers() -> None:
    """Finish disconnected requests before releasing the SQLite ownership lock."""
    if _workers:
        await asyncio.gather(*tuple(_workers))


async def stream_turn(session_id: str, message: str, turn_id: str,
                      execute: Callable) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    subscribed = True

    def deliver(event: dict) -> None:
        if subscribed:
            queue.put_nowait(event)

    def publish(event: dict) -> None:
        loop.call_soon_threadsafe(deliver, event)

    emitter = EventEmitter(session_id, turn_id, publish)

    def run() -> None:
        with observe_events(emitter):
            # Identity acknowledgment only; durable acceptance happens in sessions.
            emitter.emit("turn", message="Turn identity assigned.")
            try:
                execution = execute(session_id, message, turn_id=turn_id)
            except ChatPersistenceError as error:
                log("stream_failure", failed=True, failure_code="chat_persistence")
                emitter.emit("failure", http_status=503, code="chat_persistence",
                             outcome=error.outcome, message=str(error))
            except ChatTurnConflict as error:
                log("stream_failure", failure_code="chat_turn_conflict")
                emitter.emit("failure", http_status=409, code="chat_turn_conflict",
                             state=error.state, message=str(error))
            except RuntimeUnavailable as error:
                log("stream_failure", failed=True, failure_code="runtime_unavailable")
                # The session wrapper saves this sanitized runtime failure first.
                emitter.emit("failure", http_status=503, code="runtime_unavailable",
                             outcome="saved", message=str(error))
            except Exception:
                log("stream_failure", failed=True, failure_code="execution_unknown")
                emitter.emit("failure", http_status=503, code="execution_unknown",
                             outcome="unknown", message="Turn completion is unknown. Read saved chat history; do not automatically retry.")
            else:
                emitter.emit("final", http_status=503 if execution.status in {"error", "partial_failure"} else 200,
                             outcome="saved", execution=asdict(execution))

    worker = asyncio.create_task(asyncio.to_thread(run))
    _workers.add(worker)
    worker.add_done_callback(_workers.discard)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            # Numeric SSE IDs avoid interpolating caller-owned identity into headers.
            yield (f"id: {event['sequence']}\nevent: {event['event']}\n"
                   f"data: {json.dumps(event, ensure_ascii=False, allow_nan=False)}\n\n")
            if event["event"] in {"final", "failure"}:
                break
    finally:
        # Cancellation closes only this subscriber. Keep a strong worker reference
        # until completion; discard any remaining transient progress after disconnect.
        subscribed = False
