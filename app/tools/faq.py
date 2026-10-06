"""Local lexical retrieval of fictional employee policies; no answer generation."""

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_DATA_PATH = Path(__file__).resolve().parents[2] / "data/company_faq.json"
# Conservative demo heuristics, not calibrated confidence thresholds.
_MIN_MATCH_SCORE = 0.60
_MIN_CANDIDATE_SCORE = 0.40
_MIN_MARGIN = 0.12


@dataclass(frozen=True)
class FAQCandidate:
    policy_id: str
    question: str
    score: float


@dataclass(frozen=True)
class FAQResult:
    status: Literal["matched", "ambiguous", "no_match"]
    candidates: tuple[FAQCandidate, ...] = ()
    policy_id: str | None = None
    answer: str | None = None
    is_demo: bool = True


@lru_cache(maxsize=1)
def _load_index():
    """Build once from bundled data; restart the process after editing the file."""
    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    entries = data["faqs"]
    phrasings, owners = [], []
    for index, entry in enumerate(entries):
        for phrasing in [entry["question"], *entry["alternate_phrasings"]]:
            phrasings.append(phrasing)
            owners.append(index)
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(phrasings)
    return entries, owners, vectorizer, matrix


def retrieve_faq(question: str) -> FAQResult:
    """Retrieve a stored answer, candidate questions, or no match.

    Callers supply one self-contained English policy question. Routing, compound
    request handling, and conversation context belong to the later agent slice.
    Scores measure word overlap, not probability or semantic correctness.
    """
    if not isinstance(question, str):
        raise TypeError("FAQ question must be a string")
    if not question.strip():
        raise ValueError("FAQ question must not be empty")

    entries, owners, vectorizer, matrix = _load_index()
    # Unknown words disappear from TF-IDF vectors. Require some vocabulary
    # coverage so a long unsupported question cannot match on one familiar word.
    terms = set(vectorizer.build_tokenizer()(question.lower())) - vectorizer.get_stop_words()
    known = terms & vectorizer.vocabulary_.keys()
    if not terms or len(known) / len(terms) < 0.6:
        return FAQResult("no_match")

    similarities = cosine_similarity(vectorizer.transform([question]), matrix)[0]
    scores = [0.0] * len(entries)
    for owner, score in zip(owners, similarities):
        scores[owner] = max(scores[owner], float(score))
    ranked = sorted(range(len(entries)), key=lambda index: (-scores[index], entries[index]["policy_id"]))
    best, second = ranked[:2]
    if scores[best] < _MIN_CANDIDATE_SCORE:
        return FAQResult("no_match")

    candidates = tuple(
        FAQCandidate(entries[index]["policy_id"], entries[index]["question"], scores[index])
        for index in ranked[:3] if scores[index] >= _MIN_CANDIDATE_SCORE
    )
    if scores[best] < _MIN_MATCH_SCORE or scores[best] - scores[second] < _MIN_MARGIN:
        return FAQResult("ambiguous", candidates)
    return FAQResult("matched", candidates[:1], entries[best]["policy_id"], entries[best]["answer"])
