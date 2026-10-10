"""Stateless FAQ API; this does not invoke an agent or maintain chat history."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.runtime import RuntimeUnavailable, execute_request
from app.tools.faq import FAQResult


router = APIRouter()


class FAQRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(strict=True, min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class FAQTrace(BaseModel):
    tool: Literal["retrieve_faq"] = "retrieve_faq"
    arguments: dict[str, str]
    status: Literal["completed", "failed"]
    result: FAQResult | None
    elapsed_ms: float


class FAQResponse(BaseModel):
    status: Literal["completed", "agent_required", "error"]
    predicted_intent: str
    confidence: float
    route: Literal["direct", "agent"]
    reason: str
    faq: FAQResult | None
    trace: list[FAQTrace]
    elapsed_ms: float


@router.post("/api/v1/faq", response_model=FAQResponse)
def answer_faq(body: FAQRequest, response: Response) -> FAQResponse:
    try:
        execution = execute_request(body.message, faq_only=True)
    except RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if execution.status == "error":
        response.status_code = 503
    trace = [FAQTrace(tool=step.tool, arguments=step.arguments, status=step.status,
                      result=step.result, elapsed_ms=step.elapsed_ms)
             for step in execution.trace]
    return FAQResponse(status=execution.status, predicted_intent=execution.predicted_intent,
                       confidence=execution.confidence, route=execution.route,
                       reason=execution.reason, faq=execution.result, trace=trace,
                       elapsed_ms=execution.elapsed_ms)
