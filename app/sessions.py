"""Durable conversation history for one trusted local backend process."""

import json
from dataclasses import asdict, dataclass, field, replace
from threading import Lock
from time import perf_counter
from uuid import uuid4

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from langsmith import tracing_context
from pydantic import TypeAdapter, ValidationError

from app.monitoring import track_persistence
from app.agent import AgentTrace
from app.chat_store import ChatPersistenceError, ChatStore, ChatTurnConflict, database_path
from app.chat_reminders import reminder_turn
from app.runtime import ExecutionResult, RuntimeUnavailable, execute_request


@dataclass
class _Session:
    # A display/testing snapshot only; SQLite supplies context for every request.
    history: InMemoryChatMessageHistory = field(default_factory=InMemoryChatMessageHistory)
    lock: Lock = field(default_factory=Lock)


_sessions: dict[str, _Session] = {}
_registry_lock = Lock()
_store: ChatStore | None = None


def _text(value: str, name: str, limit: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank and at most {limit:,} characters")


def _get_session(session_id: str) -> _Session:
    _text(session_id, "Session ID", 128)
    with _registry_lock:
        if session_id not in _sessions:
            _sessions[session_id] = _Session()
        return _sessions[session_id]


def _get_store() -> ChatStore:
    global _store
    with _registry_lock:
        path = database_path()
        if _store is None:
            _store = ChatStore(path)
        elif _store.path != path:
            raise ChatPersistenceError("Restart the backend before changing chat storage.")
        return _store


def close_chat_store() -> None:
    """Release ownership on graceful backend shutdown, after active requests finish."""
    global _store
    with _registry_lock:
        if _store is not None:
            _store.close()
            _store = None


def get_profile():
    return _get_store().profile()


def create_chat() -> dict:
    return _get_store().create_chat(uuid4().hex)


def list_chats() -> list[dict]:
    return _get_store().list_chats()


def get_chat(session_id: str) -> dict | None:
    _text(session_id, "Session ID", 128)
    chat = _get_store().get_chat(session_id)
    if chat is not None:
        for turn in chat["turns"]:
            if turn["execution"] is not None:
                turn["execution"] = asdict(_execution(turn["execution"]))
    return chat


def rename_chat(session_id: str, title: str) -> dict:
    _text(title, "Title", 120)
    session = _get_session(session_id)
    if not session.lock.acquire(blocking=False):
        raise ChatTurnConflict("Running work blocks chat management.", state="running")
    try:
        return _get_store().rename(session_id, " ".join(title.split()))
    finally:
        session.lock.release()


def delete_chat(session_id: str) -> None:
    session = _get_session(session_id)
    if not session.lock.acquire(blocking=False):
        raise ChatTurnConflict("Running work blocks chat management.", state="running")
    try:
        _get_store().delete(session_id)
        # Retain the same lock for callers already referencing this session.
        session.history.clear()
    finally:
        session.lock.release()


def _execution(record: dict) -> ExecutionResult:
    try:
        execution = TypeAdapter(ExecutionResult).validate_python(record)
        # Preserve reasons when the shared tool/agent trace union overlaps.
        trace = [TypeAdapter(AgentTrace).validate_python(step) if "reason" in step else decoded
                 for step, decoded in zip(record["trace"], execution.trace)]
        return replace(execution, trace=trace)
    except (ValidationError, KeyError, TypeError, ValueError):
        raise ChatPersistenceError("Saved chat outcomes could not be restored.") from None


def _assistant(turn: dict) -> AIMessage:
    if turn["execution"] is not None:
        _execution(turn["execution"])
        record = turn["execution"]
    else:
        record = {"status": "error", "reply": turn["failure_reply"],
                  "reason": turn["failure_reason"], "trace": []}
    return AIMessage(content=json.dumps(record),
                     additional_kwargs={"opsflow_demo_policy": turn["demo_policy"]})


def _restore(turns: list[dict]) -> list[HumanMessage | AIMessage]:
    return [message for turn in turns if turn["state"] != "running"
            for message in (HumanMessage(content=turn["message"]), _assistant(turn))]


def execute_session_request(session_id: str, message: str, *, turn_id: str | None = None) -> ExecutionResult:
    """Commit a turn once, restore its context, execute, then persist its outcome.

    Optional turn IDs provide duplicate protection for Python and HTTP callers.
    No automatic execution retries or history truncation.
    """
    _text(message, "Message", 10000)
    _text(session_id, "Session ID", 128)
    if turn_id is not None:
        _text(turn_id, "Turn ID", 128)
    else:
        turn_id = uuid4().hex
    started = perf_counter()
    session = _get_session(session_id)
    with session.lock, tracing_context(enabled=False):
        store = _get_store()
        prior = store.turns(session_id)
        history = _restore(prior)
        session.history.messages = history
        existing = store.begin(session_id, message, turn_id)
        if existing is not None:
            if existing["state"] != "finished":
                raise ChatTurnConflict("This turn has unfinished or unknown completion. No execution was repeated.",
                                       state=existing["state"])
            if existing["execution"] is None:
                raise RuntimeUnavailable(existing["failure_reply"])
            return _execution(existing["execution"])

        with track_persistence():
            failure_reply = None
            try:
                with reminder_turn(turn_id):
                    execution = execute_request(message, history=history)
            except RuntimeUnavailable as error:
                execution = None
                failure_reply = str(error)
            except Exception:
                # Unobserved completion cannot be invented or automatically repeated.
                raise ChatPersistenceError(
                    "The turn stopped before its outcome was saved. Completion is unknown; no automatic retry.",
                    outcome="unsaved") from None
            if execution is not None:
                # Freeze the same timing for response and storage. Final SQLite commit
                # duration is excluded, as are HTTP transport and rendering.
                execution = replace(execution, elapsed_ms=(perf_counter() - started) * 1000)
                record = asdict(execution)
                demo_policy = any(step.tool == "retrieve_faq" and step.status == "completed"
                    and (step.result.get("is_demo") if isinstance(step.result, dict)
                         else getattr(step.result, "is_demo", False)) for step in execution.trace)
            else:
                record, demo_policy = None, False
            try:
                store.finish(turn_id, execution=record, demo_policy=bool(demo_policy),
                             failure_reply=failure_reply,
                             failure_reason="runtime_unavailable" if failure_reply is not None else None)
            except ChatPersistenceError:
                raise ChatPersistenceError(
                    "The turn ran, but its outcome was not saved. Completion is unknown after reload; no automatic retry.",
                    outcome="unsaved") from None
            saved = {"execution": record, "demo_policy": bool(demo_policy),
                     "failure_reply": failure_reply, "failure_reason": "runtime_unavailable"}
            session.history.messages = [*history, HumanMessage(content=message), _assistant(saved)]
            if execution is None:
                raise RuntimeUnavailable(failure_reply) from None
            return execution


def clear_session_history(session_id: str) -> None:
    """Clear durable turns after active execution; keep metadata and session lock."""
    session = _get_session(session_id)
    with session.lock, tracing_context(enabled=False):
        _get_store().clear(session_id)
        session.history.clear()
