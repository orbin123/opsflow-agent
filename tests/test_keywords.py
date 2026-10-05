import math
import socket

import pytest

from app.tools.keywords import extract_keywords


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Employees need VPN access to use the payroll portal. "
         "VPN access requires approval from IT support.", {"vpn access", "payroll portal"}),
        ("A payroll discrepancy affected the monthly salary. "
         "Please report the payroll discrepancy to the payroll team.",
         {"payroll discrepancy", "monthly salary"}),
    ],
)
def test_relevant_phrases_are_ranked_and_bounded(text, expected):
    result = extract_keywords(text)
    assert 1 <= len(result) <= 5
    phrases = [item.phrase.lower() for item in result]
    assert expected <= set(phrases)
    assert len(phrases) == len(set(phrases))
    assert all(1 <= len(phrase.split()) <= 3 for phrase in phrases)
    assert all(phrase in text.lower() for phrase in phrases)
    scores = [item.score for item in result]
    assert all(math.isfinite(score) and score >= 0 for score in scores)
    assert scores == sorted(scores)


@pytest.mark.parametrize("text", ["", "  \n\t"])
def test_empty_text_is_rejected(text):
    with pytest.raises(ValueError, match="must not be empty"):
        extract_keywords(text)


@pytest.mark.parametrize("text", [None, 12, ["payroll"]])
def test_non_string_text_is_rejected(text):
    with pytest.raises(TypeError, match="must be a string"):
        extract_keywords(text)


@pytest.mark.parametrize("text", ["the and or", "!!!"])
def test_no_candidates_returns_empty_list(text):
    assert extract_keywords(text) == []


def test_single_word_does_not_pad_results():
    result = extract_keywords("Payroll")
    assert [item.phrase for item in result] == ["Payroll"]


def test_repeatable_extraction_without_network(monkeypatch):
    def unexpected_network(*args, **kwargs):
        pytest.fail("Keyword extraction must not connect to the network")

    monkeypatch.setattr(socket.socket, "connect", unexpected_network)
    text = "Employees need VPN access to use the payroll portal."
    first = extract_keywords(text)
    extract_keywords("Unrelated expense reimbursement policy.")
    assert first
    assert all(extract_keywords(text) == first for _ in range(3))
