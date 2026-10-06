"""Stateless FAQ API; this does not invoke an agent or maintain chat history."""

from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.intent_router import classify_request
from app.routes.faq_route import try_direct_faq
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
    started = perf_counter()
    try:
        intent, confidence, threshold = classify_request(body.message)
    except Exception:
        raise HTTPException(status_code=503, detail="Intent classifier unavailable") from None
    try:
        decision = try_direct_faq(body.message, intent=intent, confidence=confidence, threshold=threshold)
    except Exception:
        raise HTTPException(status_code=503, detail="FAQ routing unavailable") from None

    trace = []
    status = "agent_required"
    if decision.route == "direct":
        succeeded = decision.faq is not None
        status = "completed" if succeeded else "error"
        if not succeeded:
            response.status_code = 503
        trace.append(FAQTrace(arguments={"question": decision.question},
                              status="completed" if succeeded else "failed",
                              result=decision.faq, elapsed_ms=decision.tool_elapsed_ms))
    return FAQResponse(status=status, predicted_intent=intent, confidence=confidence,
                       route=decision.route, reason=decision.reason, faq=decision.faq,
                       trace=trace, elapsed_ms=(perf_counter() - started) * 1000)
