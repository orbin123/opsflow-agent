from dataclasses import asdict
import json
import math
from pathlib import Path
import socket

import pytest

from app.tools import faq


DATA_PATH = Path(__file__).resolve().parents[1] / "data/company_faq.json"
DATA = json.loads(DATA_PATH.read_text())
ENTRIES = DATA["faqs"]


def test_demo_dataset_has_25_complete_unique_policies():
    assert DATA["is_demo"] is True
    assert "Fictional" in DATA["notice"]
    assert len(ENTRIES) == 25
    assert len({entry["policy_id"] for entry in ENTRIES}) == 25
    phrasings = []
    for entry in ENTRIES:
        assert set(entry) == {"policy_id", "category", "question", "alternate_phrasings", "answer"}
        assert all(isinstance(entry[key], str) and entry[key].strip()
                   for key in ("policy_id", "category", "question", "answer"))
        assert len(entry["alternate_phrasings"]) == 2
        assert all(isinstance(text, str) and text.strip() for text in entry["alternate_phrasings"])
        phrasings.extend([entry["question"], *entry["alternate_phrasings"]])
    assert len(set(text.casefold() for text in phrasings)) == len(phrasings)


@pytest.mark.parametrize(
    ("entry", "question"),
    [(entry, question) for entry in ENTRIES
     for question in [entry["question"], *entry["alternate_phrasings"]]],
    ids=[f'{entry["policy_id"]}-{i}' for entry in ENTRIES for i in range(3)],
)
def test_all_stored_questions_return_exact_stored_answer(entry, question):
    result = faq.retrieve_faq(question)
    assert result.status == "matched"
    assert result.policy_id == entry["policy_id"]
    assert result.answer == entry["answer"]
    assert result.is_demo is True
    assert len(result.candidates) == 1
    assert result.candidates[0].question == entry["question"]
    assert math.isfinite(result.candidates[0].score)
    assert result.candidates[0].score == pytest.approx(1.0)
    json.dumps(asdict(result))


@pytest.mark.parametrize(
    ("question", "policy_id"),
    [
        ("How do I book annual leave?", "LEAVE-01"),
        ("How do I claim expenses for a business purchase?", "EXPENSE-01"),
        ("Where can I find my leave balance?", "LEAVE-03"),
        ("How do I change my bank details?", "PAYROLL-04"),
        ("  HOW CAN I WORK FROM HOME?!  ", "REMOTE-01"),
    ],
)
def test_clear_paraphrases(question, policy_id):
    assert question.strip().lower() not in {
        text.lower() for entry in ENTRIES for text in [entry["question"], *entry["alternate_phrasings"]]
    }
    result = faq.retrieve_faq(question)
    assert result.status == "matched"
    assert result.policy_id == policy_id
    assert result.answer == next(entry["answer"] for entry in ENTRIES if entry["policy_id"] == policy_id)


@pytest.mark.parametrize("question", [
    "leave", "payroll", "How do I request leave?", "How can I report a phishing email?",
])
def test_ambiguous_or_weak_matches_offer_questions_without_answer(question):
    result = faq.retrieve_faq(question)
    assert result.status == "ambiguous"
    assert result.policy_id is None and result.answer is None
    assert 1 <= len(result.candidates) <= 3
    scores = [candidate.score for candidate in result.candidates]
    assert scores == sorted(scores, reverse=True)
    for candidate in result.candidates:
        assert candidate.question == next(e["question"] for e in ENTRIES if e["policy_id"] == candidate.policy_id)


@pytest.mark.parametrize("question", [
    "What is the cafeteria menu?", "What is the parental leave entitlement?",
    "Does the company pay for fertility treatment?", "What is our salary sacrifice pension scheme?",
    "How do I report a broken office coffee machine?", "What is the capital of France?",
    "!!!", "the and or", "quux xyzzy", "Tell me about the company policy",
    "Who handles incorrect salary payments?",
])
def test_unsupported_questions_have_no_answer(question):
    result = faq.retrieve_faq(question)
    assert result.status == "no_match"
    assert result.policy_id is None and result.answer is None
    assert result.candidates == ()
    assert result.is_demo is True


@pytest.mark.parametrize("question", ["", " \n\t"])
def test_blank_question_is_rejected(question):
    with pytest.raises(ValueError, match="must not be empty"):
        faq.retrieve_faq(question)


@pytest.mark.parametrize("question", [None, 12, ["leave"]])
def test_non_string_question_is_rejected(question):
    with pytest.raises(TypeError, match="must be a string"):
        faq.retrieve_faq(question)


def test_index_loads_from_any_working_directory_without_network(tmp_path, monkeypatch):
    def unexpected_network(*args, **kwargs):
        pytest.fail("FAQ retrieval must not connect to the network")

    monkeypatch.setattr(socket.socket, "connect", unexpected_network)
    monkeypatch.chdir(tmp_path)
    faq._load_index.cache_clear()
    first = faq.retrieve_faq("What is the remote-work policy?")
    faq.retrieve_faq("How do I report sick leave?")
    assert first.status == "matched"
    assert faq.retrieve_faq("What is the remote-work policy?") == first
    faq._load_index.cache_clear()
    assert faq.retrieve_faq("What is the remote-work policy?") == first


def test_two_strong_policy_matches_require_clarification():
    result = faq.retrieve_faq("How do I report sick leave or request annual leave?")
    assert result.status == "ambiguous"
    assert result.answer is None and result.policy_id is None
    assert {candidate.policy_id for candidate in result.candidates} == {"LEAVE-01", "LEAVE-02"}
    assert all(candidate.score > 0.6 for candidate in result.candidates)
