import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.routes import faq_route
from app.tools.faq import retrieve_faq


ENTRIES = json.loads((Path(__file__).resolve().parents[1] / "data/company_faq.json").read_text())["faqs"]


@pytest.mark.parametrize("question", [q for e in ENTRIES for q in [e["question"], *e["alternate_phrasings"]]])
def test_known_questions_are_supported(question):
    assert faq_route.extract_faq_question(question) == question


@pytest.mark.parametrize("message", [
    "What is the remote-work policy?",
    ' FAQ: "What is the remote-work policy?" ',
    'faq: “What is the remote-work policy?”',
])
def test_exact_question_reaches_tool_once_at_threshold(message, monkeypatch):
    tool = Mock(wraps=retrieve_faq)
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    result = faq_route.try_direct_faq(message, intent="faq_retrieval", confidence=0.71, threshold=0.71)
    assert result.route == "direct"
    assert result.faq.policy_id == "REMOTE-01"
    assert result.tool_elapsed_ms >= 0
    tool.assert_called_once_with("What is the remote-work policy?")


@pytest.mark.parametrize("message", [
    "", "  ", "What about that?", "What is the same policy?", "What is that leave policy?",
    "What is the previous policy?", "What is the other policy?",
    "What is the leave policy and remind me tomorrow?",
    "What is the leave and attendance policy?",
    "What is the leave policy? Email me the answer.",
    "What is the leave policy?\nRemind me tomorrow",
    "Remind me to check the leave policy",
    'FAQ: "What is the remote-work policy?" and email me',
    'FAQ: "What is the remote-work policy?" "What is the leave policy?"',
    'FAQ: “What is the remote-work policy?"',
    'FAQ: "What is the leave policy and remind me tomorrow?"',
    'FAQ: "What is the same policy?"',
    "Like before, what is the remote-work policy?",
    "What is the remote-work policy? What is the dress code?",
    "What is the not remote-work policy?",
])
def test_uncertain_questions_do_not_run_tool(message, monkeypatch):
    tool = Mock()
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    result = faq_route.try_direct_faq(message, intent="faq_retrieval", confidence=1, threshold=0.71)
    assert result.route == "agent"
    assert result.reason == "question_not_unambiguous"
    assert result.faq is None and result.question is None and result.tool_elapsed_ms is None
    tool.assert_not_called()


@pytest.mark.parametrize(("intent", "confidence", "reason"), [
    ("faq_retrieval", 0.7099, "low_confidence"),
    ("faq_retrieval", float("nan"), "invalid_confidence"),
    ("faq_retrieval", float("inf"), "invalid_confidence"),
    ("faq_retrieval", -1, "invalid_confidence"),
    ("faq_retrieval", 1.1, "invalid_confidence"),
    *[(intent, 1, "intent_not_faq") for intent in ["reminder_creation", "compound_request", "sentiment_analysis", "keyword_extraction", "summarization", "email_drafting", "out_of_scope"]],
])
def test_prediction_gate_does_not_run_tool(intent, confidence, reason, monkeypatch):
    tool = Mock()
    monkeypatch.setattr(faq_route, "retrieve_faq", tool)
    result = faq_route.try_direct_faq("What is the remote-work policy?", intent=intent, confidence=confidence, threshold=0.71)
    assert result.reason == reason
    assert result.route == "agent"
    tool.assert_not_called()


@pytest.mark.parametrize("threshold", [0, -1, 1.1, float("nan"), float("inf")])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError, match="Routing threshold"):
        faq_route.try_direct_faq("What is the remote-work policy?", intent="faq_retrieval", confidence=1, threshold=threshold)
