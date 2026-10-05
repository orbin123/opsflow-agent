import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.routes import keyword_route
from app.tools.keywords import extract_keywords


@pytest.mark.parametrize(
    ("message", "text"),
    [
        ('Extract keywords from "I am sad"', "I am sad"),
        ('get the keywords for this text "I am sad"', "I am sad"),
        (' PLEASE find keywords in: "I love this!". ', "I love this!"),
        ('Keywords: “I am sad”', "I am sad"),
        ('Get keyphrases for "I hate this.\nIt is awful."', "I hate this.\nIt is awful."),
        ('Keywords: "  I am sad  "', "  I am sad  "),
        ('Find key phrases in "I can\'t stand this"', "I can't stand this"),
        ('Keywords: "Email me and remind me tomorrow"', "Email me and remind me tomorrow"),
    ],
)
def test_extracts_only_supplied_text(message, text):
    assert keyword_route.extract_keyword_payload(message) == text


@pytest.mark.parametrize(
    "message",
    [
        "", 'Keywords: ""', 'Keywords: "   "',
        "Extract keywords from I am sad",
        "Extract keywords from the previous message",
        'Extract keywords from "sad',
        'Keywords: “sad"',
        'Keywords: "sad" "happy"',
        'Keywords: "He said "sad" today"',
        'Keywords: "sad" and email me',
        'Keywords: "sad"\nRemind me tomorrow',
        'Remind me to extract keywords from "sad"',
        'Summarize and extract keywords from "sad"',
        'Like before, extract keywords from "sad"',
        "Keywords: 'sad'",
    ],
)
def test_uncertain_requests_fall_back_without_tool_execution(message, monkeypatch):
    scorer = Mock(side_effect=AssertionError("Fallback must not execute the tool"))
    monkeypatch.setattr(keyword_route, "extract_keywords", scorer)
    result = keyword_route.try_direct_keyword(
        message, intent="keyword_extraction", confidence=1, threshold=0.71
    )
    assert result.route == "agent"
    assert result.reason == "payload_not_unambiguous"
    assert result.text is None and result.keywords is None
    scorer.assert_not_called()


@pytest.mark.parametrize(
    ("intent", "confidence", "reason"),
    [
        ("keyword_extraction", 0.7099, "low_confidence"),
        ("keyword_extraction", float("nan"), "invalid_confidence"),
        ("keyword_extraction", float("inf"), "invalid_confidence"),
        ("keyword_extraction", -0.1, "invalid_confidence"),
        ("keyword_extraction", 1.1, "invalid_confidence"),
        ("reminder_creation", 1, "intent_not_keyword"),
        ("compound_request", 1, "intent_not_keyword"),
        ("sentiment_analysis", 1, "intent_not_keyword"),
        ("faq_retrieval", 1, "intent_not_keyword"),
        ("summarization", 1, "intent_not_keyword"),
        ("email_drafting", 1, "intent_not_keyword"),
        ("out_of_scope", 1, "intent_not_keyword"),
    ],
)
def test_prediction_gate_never_executes_on_fallback(intent, confidence, reason, monkeypatch):
    scorer = Mock(side_effect=AssertionError("Fallback must not execute the tool"))
    monkeypatch.setattr(keyword_route, "extract_keywords", scorer)
    result = keyword_route.try_direct_keyword(
        'Keywords: "I am sad"', intent=intent, confidence=confidence, threshold=0.71
    )
    assert result.route == "agent"
    assert result.reason == reason
    assert result.keywords is None
    scorer.assert_not_called()


def test_direct_route_passes_exact_payload_once_at_saved_threshold(monkeypatch):
    metadata = Path(__file__).resolve().parents[1] / "artifacts/models/intent_router_svm_metadata.json"
    threshold = json.loads(metadata.read_text())["routing_threshold"]["selected"]
    scorer = Mock(wraps=extract_keywords)
    monkeypatch.setattr(keyword_route, "extract_keywords", scorer)
    result = keyword_route.try_direct_keyword(
        'Extract keywords from "I am sad"',
        intent="keyword_extraction", confidence=threshold, threshold=threshold,
    )
    assert result.route == "direct"
    assert result.text == "I am sad"
    assert result.keywords == extract_keywords("I am sad")
    scorer.assert_called_once_with("I am sad")


@pytest.mark.parametrize("threshold", [0, -1, 1.1, float("nan"), float("inf")])
def test_invalid_threshold_is_a_configuration_error(threshold):
    with pytest.raises(ValueError, match="Routing threshold"):
        keyword_route.try_direct_keyword(
            'Keywords: "sad"', intent="keyword_extraction", confidence=1, threshold=threshold
        )
