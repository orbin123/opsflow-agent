import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.routes import sentiment_route
from app.tools.sentiment import analyze_sentiment


@pytest.mark.parametrize(
    ("message", "text"),
    [
        ('Analyze the sentiment of "I am sad"', "I am sad"),
        ('get the sentiment for this text "I am sad"', "I am sad"),
        (' PLEASE check sentiment of: "I love this!". ', "I love this!"),
        ('Sentiment: “I am sad”', "I am sad"),
        ('Assess sentiment for "I hate this.\nIt is awful."', "I hate this.\nIt is awful."),
        ('Sentiment: "  I am sad  "', "  I am sad  "),
        ('Analyse sentiment of "I can\'t stand this"', "I can't stand this"),
        ('Sentiment: "Email me and remind me tomorrow"', "Email me and remind me tomorrow"),
    ],
)
def test_extracts_only_supplied_text(message, text):
    assert sentiment_route.extract_sentiment_payload(message) == text


@pytest.mark.parametrize(
    "message",
    [
        "", 'Sentiment: ""', 'Sentiment: "   "',
        "Analyze the sentiment of I am sad",
        "Analyze the sentiment of the previous message",
        'Analyze the sentiment of "sad',
        'Sentiment: “sad"',
        'Sentiment: "sad" "happy"',
        'Sentiment: "He said "sad" today"',
        'Sentiment: "sad" and email me',
        'Sentiment: "sad"\nRemind me tomorrow',
        'Remind me to analyze sentiment of "sad"',
        'Summarize and analyze the sentiment of "sad"',
        'Like before, analyze sentiment of "sad"',
        "Sentiment: 'sad'",
    ],
)
def test_uncertain_requests_fall_back_without_tool_execution(message, monkeypatch):
    scorer = Mock(side_effect=AssertionError("Fallback must not execute the tool"))
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", scorer)
    result = sentiment_route.try_direct_sentiment(
        message, intent="sentiment_analysis", confidence=1, threshold=0.71
    )
    assert result.route == "agent"
    assert result.reason == "payload_not_unambiguous"
    assert result.text is None and result.sentiment is None
    scorer.assert_not_called()


@pytest.mark.parametrize(
    ("intent", "confidence", "reason"),
    [
        ("sentiment_analysis", 0.7099, "low_confidence"),
        ("sentiment_analysis", float("nan"), "invalid_confidence"),
        ("sentiment_analysis", float("inf"), "invalid_confidence"),
        ("sentiment_analysis", -0.1, "invalid_confidence"),
        ("sentiment_analysis", 1.1, "invalid_confidence"),
        ("reminder_creation", 1, "intent_not_sentiment"),
        ("compound_request", 1, "intent_not_sentiment"),
        ("keyword_extraction", 1, "intent_not_sentiment"),
        ("faq_retrieval", 1, "intent_not_sentiment"),
        ("summarization", 1, "intent_not_sentiment"),
        ("email_drafting", 1, "intent_not_sentiment"),
        ("out_of_scope", 1, "intent_not_sentiment"),
    ],
)
def test_prediction_gate_never_executes_on_fallback(intent, confidence, reason, monkeypatch):
    scorer = Mock(side_effect=AssertionError("Fallback must not execute the tool"))
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", scorer)
    result = sentiment_route.try_direct_sentiment(
        'Sentiment: "I am sad"', intent=intent, confidence=confidence, threshold=0.71
    )
    assert result.route == "agent"
    assert result.reason == reason
    assert result.sentiment is None
    scorer.assert_not_called()


def test_direct_route_passes_exact_payload_once_at_saved_threshold(monkeypatch):
    metadata = Path(__file__).resolve().parents[1] / "artifacts/models/intent_router_svm_metadata.json"
    threshold = json.loads(metadata.read_text())["routing_threshold"]["selected"]
    scorer = Mock(wraps=analyze_sentiment)
    monkeypatch.setattr(sentiment_route, "analyze_sentiment", scorer)
    result = sentiment_route.try_direct_sentiment(
        'Analyze the sentiment of "I am sad"',
        intent="sentiment_analysis", confidence=threshold, threshold=threshold,
    )
    assert result.route == "direct"
    assert result.text == "I am sad"
    assert result.sentiment == analyze_sentiment("I am sad")
    scorer.assert_called_once_with("I am sad")


@pytest.mark.parametrize("threshold", [0, -1, 1.1, float("nan"), float("inf")])
def test_invalid_threshold_is_a_configuration_error(threshold):
    with pytest.raises(ValueError, match="Routing threshold"):
        sentiment_route.try_direct_sentiment(
            'Sentiment: "sad"', intent="sentiment_analysis", confidence=1, threshold=threshold
        )
