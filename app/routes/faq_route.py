"""Conservative FAQ execution routing; agent handoff is a decision only."""

from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from time import perf_counter
from typing import Literal

from app.tools.faq import FAQResult, retrieve_faq


_DATA_PATH = Path(__file__).resolve().parents[2] / "data/company_faq.json"
_WRAPPER = re.compile(r'faq\s*:\s*(?:"([^"“”]+)"|“([^"“”]+)”)\s*[.!?]?', re.IGNORECASE)
_POLICY = re.compile(r"what is (?:the |our |company )?([a-z]+(?:[ -][a-z]+){0,4}) policy\??", re.IGNORECASE)
# The free-topic form permits a policy topic, not actions or contextual references.
_UNSAFE_TOPIC = frozenset("and or then also remind reminder email send draft summarize analyse analyze extract previous above earlier this that it its these those same other my your their his her not except without ignore instead".split())


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split()).rstrip("?!.")


@lru_cache(maxsize=1)
def _known_questions() -> frozenset[str]:
    entries = json.loads(_DATA_PATH.read_text(encoding="utf-8"))["faqs"]
    return frozenset(_normalize(question) for entry in entries
                     for question in [entry["question"], *entry["alternate_phrasings"]])


def extract_faq_question(request: str) -> str | None:
    question = request.strip()
    wrapped = _WRAPPER.fullmatch(question)
    if wrapped:
        question = (wrapped.group(1) or wrapped.group(2)).strip()
    if _normalize(question) in _known_questions():
        return question
    match = _POLICY.fullmatch(question)
    if match and not (set(re.split(r"[ -]", match.group(1).lower())) & _UNSAFE_TOPIC):
        return question
    return None


@dataclass(frozen=True)
class FAQRouteResult:
    route: Literal["direct", "agent"]
    reason: str
    question: str | None = None
    faq: FAQResult | None = None
    tool_elapsed_ms: float | None = None


def try_direct_faq(request: str, *, intent: str, confidence: float, threshold: float) -> FAQRouteResult:
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("Routing threshold must be finite and in (0, 1]")
    if intent != "faq_retrieval":
        return FAQRouteResult("agent", "intent_not_faq")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        return FAQRouteResult("agent", "invalid_confidence")
    if confidence < threshold:
        return FAQRouteResult("agent", "low_confidence")
    question = extract_faq_question(request)
    if question is None:
        return FAQRouteResult("agent", "question_not_unambiguous")
    started = perf_counter()
    try:
        result = retrieve_faq(question)
    except Exception:
        # Do not expose exception text: it may contain filesystem or input data.
        return FAQRouteResult("direct", "faq_unavailable", question,
                              tool_elapsed_ms=(perf_counter() - started) * 1000)
    return FAQRouteResult("direct", "safe_faq_question", question, result,
                          (perf_counter() - started) * 1000)
