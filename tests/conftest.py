"""Explicit provider doubles for classifier-first workflow integration checks."""

import json
from unittest.mock import Mock

from langchain_core.messages import AIMessage
import pytest

from app.workflows import sentiment_workflow, keyword_workflow, faq_workflow


@pytest.fixture(autouse=True)
def isolated_chat_database(tmp_path, monkeypatch):
    from app import sessions

    monkeypatch.setenv("OPSFLOW_CHATS_DB", str(tmp_path / "chats.sqlite3"))
    monkeypatch.setattr(sessions, "_store", None)
    monkeypatch.setattr(sessions, "_sessions", {})
    yield
    sessions.close_chat_store()


@pytest.fixture
def sentiment_provider(monkeypatch):
    monkeypatch.setattr(sentiment_workflow, "_create_model",
                        lambda *args: pytest.fail("Unexpected sentiment provider initialization"))

    def install(source, reply="VADER classified the supplied text."):
        model = Mock()
        model.invoke.side_effect = [
            AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "stop"})
            for payload in [
                {"status": "ready", "source_text": source, "reason": "explicit_source"},
                {"reply": reply},
            ]
        ]
        monkeypatch.setattr(sentiment_workflow, "_create_model", lambda *args: model)
        return model

    return install


@pytest.fixture
def faq_provider(monkeypatch):
    monkeypatch.setattr(faq_workflow, "_create_model",
                        lambda *args: pytest.fail("Unexpected FAQ provider initialization"))

    def install(question, reply="This fictional demo policy requires manager approval.", status="completed"):
        model = Mock()
        model.invoke.side_effect = [
            AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "stop"})
            for payload in [
                {"status": "ready", "question": question, "reason": "explicit_question"},
                {"status": status, "reply": reply},
            ]
        ]
        monkeypatch.setattr(faq_workflow, "_create_model", lambda *args: model)
        return model

    return install


@pytest.fixture
def keyword_provider(monkeypatch):
    monkeypatch.setattr(keyword_workflow, "_create_model",
                        lambda *args: pytest.fail("Unexpected keyword provider initialization"))

    def install(source, reply="Here are the keywords extracted from your text and their scores."):
        model = Mock()
        model.invoke.side_effect = [
            AIMessage(content=json.dumps(payload), response_metadata={"finish_reason": "stop"})
            for payload in [
                {"status": "ready", "source_text": source, "reason": "explicit_source"},
                {"reply": reply},
            ]
        ]
        monkeypatch.setattr(keyword_workflow, "_create_model", lambda *args: model)
        return model

    return install
