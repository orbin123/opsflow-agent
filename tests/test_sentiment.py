import socket

import pytest

from app.tools.sentiment import analyze_sentiment


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("I love this service!", "positive"),
        ("I am sad", "negative"),
        ("The meeting starts at noon.", "neutral"),
        ("This is good", "positive"),
        ("This is not good", "negative"),
    ],
)
def test_sentiment_labels_and_score_ranges(text, label):
    result = analyze_sentiment(text)
    assert result.label == label
    assert -1 <= result.compound <= 1
    assert all(0 <= value <= 1 for value in (result.positive, result.neutral, result.negative))
    assert result.positive + result.neutral + result.negative == pytest.approx(1, abs=0.002)


@pytest.mark.parametrize("text", ["", "  \n\t"])
def test_empty_text_is_rejected(text):
    with pytest.raises(ValueError, match="must not be empty"):
        analyze_sentiment(text)


@pytest.mark.parametrize("text", [None, 12, ["happy"]])
def test_non_string_text_is_rejected(text):
    with pytest.raises(TypeError, match="must be a string"):
        analyze_sentiment(text)


def test_repeatable_scoring_without_network(monkeypatch):
    def unexpected_network(*args, **kwargs):
        pytest.fail("Sentiment scoring must not connect to the network")

    monkeypatch.setattr(socket.socket, "connect", unexpected_network)
    first = analyze_sentiment("I am sad")
    assert first.compound == -0.4767
    assert all(analyze_sentiment("I am sad") == first for _ in range(3))
