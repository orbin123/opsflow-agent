"""Explicit provider doubles for classifier-first workflow integration checks."""

import json
from unittest.mock import Mock

from langchain_core.messages import AIMessage
import pytest

from app import sentiment_workflow, keyword_workflow


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
def keyword_provider(monkeypatch):
    monkeypatch.setattr(keyword_workflow, "_create_model",
                        lambda *args: pytest.fail("Unexpected keyword provider initialization"))

    def install(source, reply="YAKE extracted the returned keyword phrases."):
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
