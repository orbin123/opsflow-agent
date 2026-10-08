"""Durable chat for local, single-process use; session IDs are caller-owned."""

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, Path
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.agent import AgentTrace
from app.runtime import ExecutionResult, RuntimeUnavailable, ToolResult, ToolTrace
from app.sessions import execute_session_request, create_chat, list_chats, get_chat
from app.chat_store import ChatPersistenceError, ChatTurnConflict
from app.workflows.sentiment_workflow import SentimentStage
from app.workflows.keyword_workflow import KeywordStage
from app.workflows.faq_workflow import FAQStage


router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(strict=True, min_length=1, max_length=128)
    message: str = Field(strict=True, min_length=1, max_length=10000)
    turn_id: str | None = Field(default=None, strict=True, min_length=1, max_length=128)

    @field_validator("session_id", "message", "turn_id")
    @classmethod
    def reject_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Value must not be blank")
        return value


class ChatResponse(BaseModel):
    session_id: str
    turn_id: str | None = None
    status: Literal["completed", "agent_required", "needs_clarification", "partial_failure", "error"]
    predicted_intent: str
    confidence: float
    route: Literal["direct", "llm_assisted", "agent"]
    reason: str
    result: ToolResult | None
    trace: list[ToolTrace | AgentTrace]
    elapsed_ms: float
    reply: str | None
    agent_reason: str | None
    workflow_trace: list[SentimentStage | KeywordStage | FAQStage] = Field(default_factory=list)


@router.post("/api/v1/chat", response_model=ChatResponse, responses={
    409: {"description": "Conflicting submission or unfinished turn; no repeated execution."},
    503: {"description": "Execution failed; retained outcomes or sanitized runtime detail."},
})
def chat(body: ChatRequest, response: Response) -> ChatResponse:
    turn_id = body.turn_id or uuid4().hex
    try:
        execution = execute_session_request(body.session_id, body.message, turn_id=turn_id)
    except RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ChatPersistenceError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "chat_persistence", "outcome": exc.outcome, "message": str(exc),
        }) from None
    except ChatTurnConflict as exc:
        detail = {"code": "chat_turn_conflict", "state": exc.state, "message": str(exc)}
        raise HTTPException(status_code=409, detail=detail) from None
    if execution.status in {"error", "partial_failure"}:
        response.status_code = 503
    return ChatResponse(session_id=body.session_id, turn_id=turn_id, **vars(execution))


class CreateChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatMetadata(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str


class SavedTurn(BaseModel):
    turn_id: str
    session_id: str
    sequence: int
    message: str
    started_at: str
    finished_at: str | None
    state: Literal["running", "finished", "interrupted"]
    execution: dict | None
    failure_reply: str | None
    failure_reason: str | None
    demo_policy: bool

    @field_validator("execution")
    @classmethod
    def validate_execution(cls, value: dict | None) -> dict | None:
        if value is not None:
            TypeAdapter(ExecutionResult).validate_python(value)
        # Keep exact fields, including reasons in overlapping tool/agent traces.
        return value


class SavedChat(ChatMetadata):
    turns: list[SavedTurn]


def _storage_detail(exc: ChatPersistenceError) -> HTTPException:
    return HTTPException(status_code=503, detail={
        "code": "chat_persistence", "outcome": exc.outcome, "message": str(exc),
    })


@router.post("/api/v1/chats", response_model=ChatMetadata, status_code=201,
             responses={503: {"description": "Sanitized chat storage failure."}})
def new_chat(body: CreateChatRequest) -> dict:
    try:
        return create_chat()
    except ChatPersistenceError as exc:
        raise _storage_detail(exc) from None


@router.get("/api/v1/chats", response_model=list[ChatMetadata],
            responses={503: {"description": "Sanitized chat storage failure."}})
def catalogue() -> list[dict]:
    try:
        return list_chats()
    except ChatPersistenceError as exc:
        raise _storage_detail(exc) from None


@router.get("/api/v1/chats/{session_id:path}", response_model=SavedChat, responses={
    404: {"description": "Chat not found; no record created."},
    503: {"description": "Sanitized chat storage or restoration failure."},
})
def saved_chat(session_id: str = Path(min_length=1, max_length=128, pattern=r"\S")) -> dict:
    try:
        saved = get_chat(session_id)
    except ChatPersistenceError as exc:
        raise _storage_detail(exc) from None
    if saved is None:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return saved
