"""Classifier-first direct/LLM-assisted execution and bounded agent handoff."""

from dataclasses import dataclass, field
import math
from time import perf_counter
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage

from app.observability.monitoring import track_execution
from app.core.execution_events import emit
from app.core.agent import AgentTrace, run_agent
from app.core.intent_router import classify_request
from app.routes.faq_route import try_direct_faq
from app.workflows.faq_workflow import FAQStage, run_faq_workflow
from app.workflows.keyword_workflow import KeywordStage, run_keyword_workflow
from app.workflows.sentiment_workflow import SentimentStage, run_sentiment_workflow
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
    route: Literal["direct", "llm_assisted", "agent"]
    reason: str
    result: ToolResult | None
    trace: list[ToolTrace | AgentTrace]
    elapsed_ms: float
    reply: str | None = None
    agent_reason: str | None = None
    workflow_trace: list[SentimentStage | KeywordStage | FAQStage] = field(default_factory=list)


@track_execution
def execute_request(message: str, *, faq_only: bool = False,
                    history: list[HumanMessage | AIMessage] | None = None) -> ExecutionResult:
    """Classify once; high-confidence sentiment/keywords/FAQ use fixed workflows.

    The FAQ endpoint restricts execution to FAQ to preserve its public contract.
    Other requests that defer invoke the stateless agent once with the original message.
    Optional prior conversation is supplied by the session entry point, never stored here.
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

    emit("classification", predicted_intent=intent, confidence=confidence)
    result = None
    trace = []
    workflow_trace = []
    status = "agent_required"
    reply = None
    route = "agent"
    reason = "intent_not_faq" if faq_only else "intent_requires_agent"
    try:
        if faq_only:
            decision = try_direct_faq(message, intent=intent, confidence=confidence, threshold=threshold)
            tool, arguments, result = "retrieve_faq", {"question": decision.question}, decision.faq
        elif intent in {"sentiment_analysis", "keyword_extraction", "faq_retrieval"}:
            decision = None
            if not math.isfinite(threshold) or not 0 < threshold <= 1:
                raise ValueError("Invalid routing threshold")
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                reason = "invalid_confidence"
            elif confidence < threshold:
                reason = "low_confidence"
            else:
                workflow_fn = {"sentiment_analysis": run_sentiment_workflow,
                               "keyword_extraction": run_keyword_workflow,
                               "faq_retrieval": run_faq_workflow}[intent]
                emit("routing", route="llm_assisted", reason="high_confidence_workflow")
                workflow = workflow_fn(message)
                status, reason, result, reply = (workflow.status, workflow.reason,
                                                 workflow.result, workflow.reply)
                route = "agent" if status == "agent_required" else "llm_assisted"
                workflow_trace = workflow.trace
                tool = {"sentiment_analysis": "analyze_sentiment",
                        "keyword_extraction": "extract_keywords",
                        "faq_retrieval": "retrieve_faq"}[intent]
                for stage in workflow_trace:
                    if stage.stage == tool:
                        arguments = ({"question": workflow.question} if intent == "faq_retrieval"
                                     else {"text": workflow.source_text})
                        trace.append(ToolTrace(tool, arguments,
                                               stage.status, result, stage.elapsed_ms))
        else:
            decision = None
    except Exception:
        detail = "FAQ routing unavailable" if faq_only else "Execution routing unavailable"
        raise RuntimeUnavailable(detail) from None

    if decision is not None:
        route, reason = decision.route, decision.reason
        if route == "direct":
            succeeded = result is not None
            status = "completed" if succeeded else "error"
            trace.append(ToolTrace(tool, arguments, "completed" if succeeded else "failed",
                                   result, decision.tool_elapsed_ms))
    agent_reason = None
    if status == "agent_required" and not faq_only:
        emit("routing", route="agent", reason=reason)
        try:
            agent = run_agent(message) if history is None else run_agent(message, history=history)
        except Exception:
            status = "error"
            reply = "Agent unavailable. No execution results were returned."
            agent_reason = "agent_unavailable"
        else:
            status, reply, agent_reason, trace = agent.status, agent.reply, agent.reason, agent.trace
    return ExecutionResult(status, intent, confidence, route, reason, result, trace,
                           (perf_counter() - started) * 1000, reply, agent_reason, workflow_trace)
