"""Local, deterministic sentiment scoring for supplied English text."""

from dataclasses import dataclass
from typing import Literal

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


@dataclass(frozen=True)
class SentimentResult:
    label: Literal["positive", "neutral", "negative"]
    compound: float
    positive: float
    neutral: float
    negative: float


_analyzer = SentimentIntensityAnalyzer()


def analyze_sentiment(text: str) -> SentimentResult:
    """Score payload only; scores describe sentiment, not routing confidence.

    Uses VADER's standard +/-0.05 compound thresholds. Language detection and
    translation are outside this tool's scope; callers supply English text.
    """
    if not isinstance(text, str):
        raise TypeError("Sentiment text must be a string")
    if not text.strip():
        raise ValueError("Sentiment text must not be empty")

    scores = _analyzer.polarity_scores(text)
    label = "neutral"
    if scores["compound"] >= 0.05:
        label = "positive"
    elif scores["compound"] <= -0.05:
        label = "negative"

    return SentimentResult(
        label=label,
        compound=scores["compound"],
        positive=scores["pos"],
        neutral=scores["neu"],
        negative=scores["neg"],
    )
