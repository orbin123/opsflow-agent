"""Conservative sentiment handoff; model loading and agent execution come later."""

from dataclasses import dataclass
import math
import re
from typing import Literal

from app.tools.sentiment import SentimentResult, analyze_sentiment


# Match the entire instruction, not just a quoted substring. Internal double
# quotes are deliberately unsupported because they can obscure payload boundaries.
_REQUEST = re.compile(
    r'(?:please\s+)?'
    r'(?:(?:analyze|analyse|check|assess|get)\s+(?:the\s+)?sentiment\s+'
    r'(?:of|for)(?:\s+this\s+text)?(?:\s*:\s*|\s+)|sentiment\s*:\s*)'
    r'(?:"(?P<straight>[^"“”]+)"|“(?P<curly>[^"“”]+)”)'
    r'\s*[.!?]?',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SentimentRouteResult:
    route: Literal["direct", "agent"]
    reason: str
    text: str | None = None
    sentiment: SentimentResult | None = None


def extract_sentiment_payload(request: str) -> str | None:
    """Accept one explicit quoted payload; otherwise defer interpretation."""
    match = _REQUEST.fullmatch(request.strip())
    if match is None:
        return None
    text = match.group("straight") or match.group("curly")
    return text if text.strip() else None


def try_direct_sentiment(
    request: str, *, intent: str, confidence: float, threshold: float
) -> SentimentRouteResult:
    """Use an upstream prediction and its configured threshold to gate execution.

    An agent result is only a handoff decision: no agent has been invoked.
    The caller will supply the saved model metadata's routing threshold.
    """
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("Routing threshold must be finite and in (0, 1]")
    if intent != "sentiment_analysis":
        return SentimentRouteResult("agent", "intent_not_sentiment")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return SentimentRouteResult("agent", "invalid_confidence")
    if confidence < threshold:
        return SentimentRouteResult("agent", "low_confidence")

    text = extract_sentiment_payload(request)
    if text is None:
        return SentimentRouteResult("agent", "payload_not_unambiguous")
    return SentimentRouteResult("direct", "safe_sentiment_payload", text, analyze_sentiment(text))
