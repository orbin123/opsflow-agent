"""Conservative keyword execution routing; agent handoff is a decision only."""

from dataclasses import dataclass
import math
import re
from time import perf_counter
from typing import Literal

from app.tools.keywords import Keyword, extract_keywords


# Match the entire instruction, not just a quoted substring. Internal double
# quotes are deliberately unsupported because they can obscure payload boundaries.
_REQUEST = re.compile(
    r'(?:please\s+)?'
    r'(?:(?:extract|find|get)\s+(?:the\s+)?(?:keywords|key\s*phrases)\s+'
    r'(?:from|in|for)(?:\s+this\s+text)?(?:\s*:\s*|\s+)|'
    r'(?:keywords|key\s*phrases)\s*:\s*)'
    r'(?:"(?P<straight>[^"“”]+)"|“(?P<curly>[^"“”]+)”)'
    r'\s*[.!?]?',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class KeywordRouteResult:
    route: Literal["direct", "agent"]
    reason: str
    text: str | None = None
    keywords: list[Keyword] | None = None
    tool_elapsed_ms: float | None = None


def extract_keyword_payload(request: str) -> str | None:
    """Accept one explicit quoted payload; otherwise defer interpretation."""
    match = _REQUEST.fullmatch(request.strip())
    if match is None:
        return None
    text = match.group("straight") or match.group("curly")
    return text if text.strip() else None


def try_direct_keyword(
    request: str, *, intent: str, confidence: float, threshold: float
) -> KeywordRouteResult:
    """Use an upstream prediction and its configured threshold to gate execution.

    An agent result is only a handoff decision: no agent has been invoked.
    The caller will supply the saved model metadata's routing threshold.
    """
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("Routing threshold must be finite and in (0, 1]")
    if intent != "keyword_extraction":
        return KeywordRouteResult("agent", "intent_not_keyword")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return KeywordRouteResult("agent", "invalid_confidence")
    if confidence < threshold:
        return KeywordRouteResult("agent", "low_confidence")

    text = extract_keyword_payload(request)
    if text is None:
        return KeywordRouteResult("agent", "payload_not_unambiguous")
    started = perf_counter()
    try:
        result = extract_keywords(text)
    except Exception:
        # Exception text may contain sensitive payloads or configuration details.
        return KeywordRouteResult("direct", "keyword_unavailable", text,
                                  tool_elapsed_ms=(perf_counter() - started) * 1000)
    return KeywordRouteResult("direct", "safe_keyword_payload", text, result,
                              (perf_counter() - started) * 1000)
