"""Session-aware chat for local, single-process use; session IDs are caller-owned."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent import AgentTrace
from app.runtime import RuntimeUnavailable, ToolResult, ToolTrace
from app.sessions import execute_session_request
from app.sentiment_workflow import SentimentStage
from app.keyword_workflow import KeywordStage


router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(strict=True, min_length=1, max_length=128)
    message: str = Field(strict=True, min_length=1, max_length=10000)

    @field_validator("session_id", "message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value


class ChatResponse(BaseModel):
    session_id: str
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
    workflow_trace: list[SentimentStage | KeywordStage] = Field(default_factory=list)


@router.post("/api/v1/chat", response_model=ChatResponse, responses={
    503: {"description": "Execution failed; retained outcomes or sanitized runtime detail."},
})
def chat(body: ChatRequest, response: Response) -> ChatResponse:
    try:
        execution = execute_session_request(body.session_id, body.message)
    except RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if execution.status in {"error", "partial_failure"}:
        response.status_code = 503
    return ChatResponse(session_id=body.session_id, **vars(execution))
