"""Transient observable execution events, scoped to one worker context.

Only validated application data belongs here, never provider messages/logs.
Nonstreaming callers have no observer and keep their existing behavior.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from typing import Callable

from fastapi.encoders import jsonable_encoder

from app.monitoring import record_tool


_observer: ContextVar["EventEmitter | None"] = ContextVar("execution_events", default=None)


class EventEmitter:
    def __init__(self, session_id: str, turn_id: str, publish: Callable[[dict], None]):
        self.session_id = session_id
        self.turn_id = turn_id
        self.publish = publish
        self.sequence = 0

    def emit(self, event: str, **data) -> int:
        self.sequence += 1
        self.publish(jsonable_encoder({
            "version": 1, "session_id": self.session_id, "turn_id": self.turn_id,
            "sequence": self.sequence, "event": event, **data,
        }))
        return self.sequence


@contextmanager
def observe_events(emitter: EventEmitter):
    token = _observer.set(emitter)
    try:
        yield
    finally:
        _observer.reset(token)


def emit(event: str, **data) -> int | None:
    observer = _observer.get()
    if observer is not None:
        return observer.emit(event, **data)
    return None


def start_step(name: str, *, kind: str = "workflow", arguments: dict | None = None) -> int | None:
    # The start event's sequence is its unique step ID within the turn.
    return emit("step_started", name=name, kind=kind, arguments=arguments)


def finish_step(step_id: int | None, record, *, arguments: dict | None = None, result=None) -> None:
    record_tool(record)
    if step_id is None:
        return
    data = asdict(record) if is_dataclass(record) else dict(record)
    if arguments is not None:
        data["arguments"] = arguments
        data["result"] = result
    emit("step_finished", step_id=step_id, **data)
