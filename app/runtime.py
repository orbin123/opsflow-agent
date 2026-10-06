"""Stateless direct execution and bounded agent handoff; FAQ-only mode abstains."""

from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from app.agent import AgentTrace, run_agent
from app.intent_router import classify_request
from app.routes.faq_route import try_direct_faq
from app.routes.keyword_route import try_direct_keyword
from app.routes.sentiment_route import try_direct_sentiment
from app.tools.faq import FAQResult
from app.tools.keywords import Keyword
from app.tools.sentiment import SentimentResult


ToolResult = SentimentResult | list[Keyword] | FAQResult


class RuntimeUnavailable(Exception):
    """A sanitized classifier or routing failure, with no tool execution trace."""


@dataclass(frozen=True)
class ToolTrace:
    tool: Literal["analyze_sentiment", "extract_keywords", "retrieve_faq"]
    arguments: dict[str, str]
    status: Literal["completed", "failed"]
    result: ToolResult | None
    elapsed_ms: float


@dataclass(frozen=True)
class ExecutionResult:
    status: Literal["completed", "agent_required", "needs_clarification", "partial_failure", "error"]
    predicted_intent: str
    confidence: float
    route: Literal["direct", "agent"]
    reason: str
    result: ToolResult | None
    trace: list[ToolTrace | AgentTrace]
    elapsed_ms: float
    reply: str | None = None
    agent_reason: str | None = None


def execute_request(message: str, *, faq_only: bool = False) -> ExecutionResult:
    """Classify once and use existing extraction/confidence gates.

    The FAQ endpoint restricts execution to FAQ to preserve its public contract.
    Other requests that defer invoke the stateless agent once with the original message.
    Callers supply a nonblank string of at most 10,000 characters.
    """
    if not isinstance(message, str):
        raise TypeError("Message must be a string")
    if not message.strip() or len(message) > 10000:
        raise ValueError("Message must be nonblank and at most 10,000 characters")
    started = perf_counter()
    try:
        intent, confidence, threshold = classify_request(message)
    except Exception:
        raise RuntimeUnavailable("Intent classifier unavailable") from None

    result = None
    trace = []
    route = "agent"
    reason = "intent_not_faq" if faq_only else "intent_requires_agent"
    try:
        if faq_only or intent == "faq_retrieval":
            decision = try_direct_faq(message, intent=intent, confidence=confidence, threshold=threshold)
            tool, arguments, result = "retrieve_faq", {"question": decision.question}, decision.faq
        elif intent == "sentiment_analysis":
            decision = try_direct_sentiment(message, intent=intent, confidence=confidence, threshold=threshold)
            tool, arguments, result = "analyze_sentiment", {"text": decision.text}, decision.sentiment
        elif intent == "keyword_extraction":
            decision = try_direct_keyword(message, intent=intent, confidence=confidence, threshold=threshold)
            tool, arguments, result = "extract_keywords", {"text": decision.text}, decision.keywords
        else:
            decision = None
    except Exception:
        detail = "FAQ routing unavailable" if faq_only else "Execution routing unavailable"
        raise RuntimeUnavailable(detail) from None

    status = "agent_required"
    if decision is not None:
        route, reason = decision.route, decision.reason
        if route == "direct":
            succeeded = result is not None
            status = "completed" if succeeded else "error"
            trace.append(ToolTrace(tool, arguments, "completed" if succeeded else "failed",
                                   result, decision.tool_elapsed_ms))
    reply = None
    agent_reason = None
    if status == "agent_required" and not faq_only:
        try:
            agent = run_agent(message)
        except Exception:
            status = "error"
            reply = "Agent unavailable. No execution results were returned."
            agent_reason = "agent_unavailable"
        else:
            status, reply, agent_reason, trace = agent.status, agent.reply, agent.reason, agent.trace
    return ExecutionResult(status, intent, confidence, route, reason, result, trace,
                           (perf_counter() - started) * 1000, reply, agent_reason)
