"""Process-local conversation history; callers own session identity and authorization."""

import json
from dataclasses import asdict, dataclass, field, replace
from threading import Lock
from time import perf_counter

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langsmith import tracing_context

from app.runtime import ExecutionResult, RuntimeUnavailable, execute_request


@dataclass
class _Session:
    history: InMemoryChatMessageHistory = field(default_factory=InMemoryChatMessageHistory)
    lock: Lock = field(default_factory=Lock)


_sessions: dict[str, _Session] = {}
_registry_lock = Lock()


def _get_session(session_id: str) -> _Session:
    if not isinstance(session_id, str):
        raise TypeError("Session ID must be a string")
    if not session_id.strip() or len(session_id) > 128:
        raise ValueError("Session ID must be nonblank and at most 128 characters")
    with _registry_lock:
        if session_id not in _sessions:
            _sessions[session_id] = _Session()
        return _sessions[session_id]


def _execute_turn(inputs: dict) -> dict:
    try:
        execution = execute_request(inputs["message"], history=inputs["history"])
    except RuntimeUnavailable as error:
        # Preserve the failed turn, then re-raise the existing contract to the caller.
        detail = str(error)
        return {"error": detail, "saved": AIMessage(content=json.dumps({
            "status": "error", "reply": detail, "reason": "runtime_unavailable", "trace": [],
        }))}
    demo_policy = any(step.tool == "retrieve_faq" and step.status == "completed"
                      and (step.result.get("is_demo") if isinstance(step.result, dict)
                           else getattr(step.result, "is_demo", False)) for step in execution.trace)
    return {"execution": execution, "saved": AIMessage(content=json.dumps(asdict(execution)),
            additional_kwargs={"opsflow_demo_policy": bool(demo_policy)})}


_conversation = RunnableWithMessageHistory(
    RunnableLambda(_execute_turn),
    lambda session_id: _get_session(session_id).history,
    input_messages_key="message", history_messages_key="history", output_messages_key="saved",
)


def execute_session_request(session_id: str, message: str) -> ExecutionResult:
    """Execute and remember a turn; serialize execution and clearing within one session.

    No automatic eviction/truncation, disk persistence, public endpoint or authentication.
    Total elapsed time includes lock waiting and history processing. History contains
    private source and result data; external tracing is disabled for the whole runnable.
    """
    if not isinstance(message, str):
        raise TypeError("Message must be a string")
    if not message.strip() or len(message) > 10000:
        raise ValueError("Message must be nonblank and at most 10,000 characters")
    started = perf_counter()
    session = _get_session(session_id)
    with session.lock, tracing_context(enabled=False):
        output = _conversation.invoke({"message": message},
                                      config={"configurable": {"session_id": session_id}})
        if "error" in output:
            raise RuntimeUnavailable(output["error"]) from None
        return replace(output["execution"], elapsed_ms=(perf_counter() - started) * 1000)


def clear_session_history(session_id: str) -> None:
    """Clear source/reply/result history after any active turn; retain the session lock."""
    session = _get_session(session_id)
    with session.lock:
        session.history.clear()
