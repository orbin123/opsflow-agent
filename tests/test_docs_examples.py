"""Published prompts with real routing/local tools and scripted language stages."""

from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage

from app.core import runtime
from app.tools import summarization, email_drafting
from tests.test_agent import call, final, install


PROMPTS = [line[2:] for line in (Path(__file__).resolve().parents[1] / "docs" / "user-guide.md")
           .read_text().splitlines() if line.startswith("> ")]


@pytest.mark.parametrize("index,tools", [
    (0, ["analyze_sentiment"]), (1, ["extract_keywords"]), (2, ["retrieve_faq"]),
    (3, ["summarize_text"]), (4, ["draft_email"]),
    (6, ["analyze_sentiment", "extract_keywords", "summarize_text", "draft_email"]),
])
def test_published_demo_prompt_contract(monkeypatch, sentiment_provider, keyword_provider,
                                       faq_provider, index, tools):
    sentiment_provider("I am happy")
    keyword_provider("The server failed after the deployment")
    faq_provider("What is the remote work policy?")
    source = ("The service failed twice today and I am frustrated." if index == 6 else
              "The deployment failed on Tuesday. The team rolled back the release. Service was restored at 10 am.")
    summary_model = Mock(return_value=AIMessage(content='{"summary":"' + source + '","key_points":[]}',
        response_metadata={"finish_reason": "stop"}))
    draft_model = Mock(return_value=AIMessage(content='{"subject":"Update","body":"' + source + '"}',
        response_metadata={"finish_reason": "stop"}))
    monkeypatch.setattr(summarization, "_create_model", lambda: Mock(invoke=summary_model))
    monkeypatch.setattr(email_drafting, "_create_model", lambda: Mock(invoke=draft_model))
    arguments = {"analyze_sentiment": {"text": "I am happy" if index == 0 else source},
        "extract_keywords": {"text": "The server failed after the deployment" if index == 1 else source},
        "retrieve_faq": {"question": "What is the remote work policy?"},
        "summarize_text": {"text": source},
        "draft_email": {"recipient": "Alex", "content": source, "instructions": "Keep it professional."}}
    install(monkeypatch, [call(tool, arguments[tool], f"demo{number}")
                          for number, tool in enumerate(tools)] + [final()])
    result = runtime.execute_request(PROMPTS[index])
    saved = asdict(result)
    assert result.status == "completed"
    assert [step.tool for step in result.trace] == tools
    assert all(step.status == "completed" for step in result.trace)
    if "draft_email" in tools:
        assert result.trace[-1].result["email_draft"]["recipient"] == "Alex"
        assert result.trace[-1].result["action_instructions"]
    if index == 0:
        assert saved["trace"][0]["result"]["label"] == "positive"
    if index == 2:
        assert saved["trace"][0]["result"]["status"] == "matched"
