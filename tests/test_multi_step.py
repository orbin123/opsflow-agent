"""One-agent protocol verification with scripted orchestration and writing tools."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.core import agent, runtime
from app.chat import sessions
from app.main import app
from app.tools.email_drafting import EmailDraft, EmailDraftResult, _ACTION_INSTRUCTIONS
from app.tools.summarization import SummaryResult, SummarizationError

SOURCE = "The service failed twice today. It is NOT resolved."
REQUEST = "Analyze the sentiment, extract keywords, summarize this complaint, and draft an email to Alex about it: " + SOURCE


def call(name, args, ident):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": ident}],
                     response_metadata={"finish_reason": "tool_calls"})


def final(status="completed", reply="Done"):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(sessions, "_sessions", {})
    classify = Mock(return_value=("compound_request", 1, .71))
    monkeypatch.setattr(runtime, "classify_request", classify)
    model = Mock()
    create = Mock(return_value=Mock(invoke=lambda messages: model.invoke(list(messages))))
    monkeypatch.setattr(agent, "_create_model", create)
    summary = Mock(return_value=SummaryResult(summary=SOURCE, key_points=[]))
    draft = Mock(side_effect=lambda **args: EmailDraftResult(
        email_draft=EmailDraft(recipient=args["recipient"], subject="Service complaint", body=args["content"]),
        action_instructions=list(_ACTION_INSTRUCTIONS)))
    monkeypatch.setitem(agent._TOOLS, "summarize_text", (agent.TextArguments, summary, "summary"))
    monkeypatch.setitem(agent._TOOLS, "draft_email", (agent.DraftArguments, draft, "draft"))
    return TestClient(app), model, create, classify, summary, draft


def post(client, message=REQUEST):
    return client.post("/api/v1/chat", json={"session_id": "multi", "message": message})


def steps():
    return [call("analyze_sentiment", {"text": SOURCE}, "s"),
            call("extract_keywords", {"text": SOURCE}, "k"),
            call("summarize_text", {"text": SOURCE}, "m")]


@pytest.mark.parametrize("with_draft", [False, True])
def test_three_four_tools_one_agent_observations_and_retained_outcomes(flow, with_draft):
    client, model, create, classify, summary, draft = flow
    def respond(messages):
        index = model.invoke.call_count - 1
        observations = [item for item in messages if isinstance(item, ToolMessage)]
        assert len(observations) == min(index, 4 if with_draft else 3)
        if index < 3:
            return steps()[index]
        if index == 3 and with_draft:
            # Construct the dependent call from the actual preceding observation.
            content = json.loads(observations[-1].content)["summary"]
            return call("draft_email", {"recipient": "Alex", "content": content}, "d")
        return final(reply="Sent!" if with_draft else "Sentiment, keywords, and summary completed.")
    model.invoke.side_effect = respond
    response = post(client, REQUEST if with_draft else "Analyze sentiment, extract keywords and summarize: " + SOURCE)
    data = response.json()
    assert response.status_code == 200 and data["route"] == "agent" and data["status"] == "completed"
    create.assert_called_once()
    classify.assert_called_once()
    expected = ["analyze_sentiment", "extract_keywords", "summarize_text"] + (["draft_email"] if with_draft else [])
    assert [step["tool"] for step in data["trace"]] == expected
    assert all(step["status"] == "completed" and step["elapsed_ms"] >= 0 for step in data["trace"])
    assert all(step["arguments"] == {"text": SOURCE} for step in data["trace"][:3])
    summary.assert_called_once_with(text=SOURCE)
    for index, invocation in enumerate(model.invoke.call_args_list[1:], 1):
        observations = [item for item in invocation.args[0] if isinstance(item, ToolMessage)]
        assert [json.loads(item.content) for item in observations] == [step["result"] for step in data["trace"][:index]]
    saved = json.loads(sessions._sessions["multi"].history.messages[-1].content)
    assert saved["trace"] == data["trace"] and saved["reply"] == data["reply"]
    if with_draft:
        assert draft.call_args.kwargs["content"] == data["trace"][2]["result"]["summary"]
        assert all(label in data["reply"] for label in ["Sentiment:", "Keywords:", "Summary", "Email draft", "What you should do"])
        assert SOURCE in data["reply"] and "Sent!" not in data["reply"]
        assert all(action in data["reply"] for action in _ACTION_INSTRUCTIONS)
    else:
        draft.assert_not_called()


def test_later_tool_failure_stops_dependents_and_retains_success(flow):
    client, model, create, classify, summary, draft = flow
    summary.side_effect = SummarizationError("timeout")
    model.invoke.side_effect = steps()
    response = post(client)
    data = response.json()
    assert response.status_code == 503 and data["status"] == "partial_failure"
    assert [step["status"] for step in data["trace"]] == ["completed", "completed", "failed"]
    assert data["trace"][0]["result"] and data["trace"][1]["result"]
    assert data["agent_reason"] == "timeout" and "unfinished" in data["reply"]
    assert model.invoke.call_count == 3
    summary.assert_called_once()
    draft.assert_not_called()
    assert json.loads(sessions._sessions["multi"].history.messages[-1].content)["trace"] == data["trace"]


def test_missing_recipient_after_success_clarifies_without_discarding_results(flow):
    client, model, create, classify, summary, draft = flow
    model.invoke.side_effect = steps() + [call("draft_email", {"content": SOURCE}, "d")]
    response = post(client, REQUEST.replace(" to Alex", ""))
    data = response.json()
    assert response.status_code == 200 and data["status"] == "needs_clarification"
    assert data["reply"] == "Who should I draft this email for?"
    assert len(data["trace"]) == 3 and all(step["status"] == "completed" for step in data["trace"])
    draft.assert_not_called()
    assert json.loads(sessions._sessions["multi"].history.messages[-1].content)["trace"] == data["trace"]


@pytest.mark.parametrize("over_budget", [False, True])
def test_five_tools_can_finish_sixth_cannot_execute(flow, over_budget):
    client, model, create, classify, summary, draft = flow
    calls = [call("summarize_text", {"text": SOURCE}, f"m{i}") for i in range(6)]
    model.invoke.side_effect = calls if over_budget else calls[:5] + [final()]
    response = post(client, "Summarize each of these six notes separately" if over_budget else "Summarize each of these five notes separately")
    data = response.json()
    assert response.status_code == (503 if over_budget else 200)
    assert data["status"] == ("partial_failure" if over_budget else "completed")
    assert len(data["trace"]) == summary.call_count == 5 and model.invoke.call_count == 6
    if over_budget:
        assert data["agent_reason"] == "tool_limit" and "unfinished" in data["reply"]
    draft.assert_not_called()


def test_time_budget_after_third_tool_keeps_result_without_draft(flow, monkeypatch):
    client, model, create, classify, summary, draft = flow
    clock = [0.0]
    monkeypatch.setattr(agent, "perf_counter", lambda: clock[0])
    def delayed(**args):
        clock[0] = 121
        return SummaryResult(summary=SOURCE, key_points=[])
    summary.side_effect = delayed
    model.invoke.side_effect = steps()
    data = post(client).json()
    assert data["status"] == "partial_failure" and data["agent_reason"] == "time_limit"
    assert len(data["trace"]) == 3 and data["trace"][2]["result"]["summary"] == SOURCE
    assert model.invoke.call_count == 3
    draft.assert_not_called()
