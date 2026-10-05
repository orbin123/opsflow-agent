"""Local keyword extraction for supplied English text."""

from dataclasses import dataclass

from yake import KeywordExtractor


@dataclass(frozen=True)
class Keyword:
    phrase: str
    score: float


def extract_keywords(text: str) -> list[Keyword]:
    """Return up to five phrases, ranked by ascending YAKE score.

    Lower scores mean greater relevance, not probability or routing confidence.
    Callers supply English text; language detection and translation are excluded.
    Nonblank text without keyword candidates returns an empty list.
    """
    if not isinstance(text, str):
        raise TypeError("Keyword text must be a string")
    if not text.strip():
        raise ValueError("Keyword text must not be empty")

    extractor = KeywordExtractor(lan="en", n=3, top=5, dedup_lim=0.9)
    return [Keyword(phrase, float(score)) for phrase, score in extractor.extract_keywords(text)]
