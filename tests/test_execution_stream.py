"""Real event hooks and SSE transport; no live providers or email delivery."""

import asyncio
import json
import socket
from threading import Event, Thread
from time import monotonic, sleep
from unittest.mock import Mock

import httpx2
import pytest
import uvicorn
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.core import agent, runtime
from app.chat import sessions
from app.api import chat
from app.chat.chat_store import ChatPersistenceError
from app.chat.chat_stream import drain_stream_workers, stream_turn
from app.main import app
from app.workflows import sentiment_workflow, keyword_workflow, faq_workflow


def decode(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def post(body):
    with TestClient(app) as client:
        response = client.post("/api/v1/chat/stream", json=body)
    return response, decode(response.text)


BODY = {"session_id": "events", "turn_id": "turn-one", "message": "Analyze I am happy"}


@pytest.mark.parametrize("intent,provider,source,workflow,tool", [
    ("sentiment_analysis", "sentiment_provider", "I am happy", sentiment_workflow, "analyze_sentiment"),
    ("keyword_extraction", "keyword_provider", "I am happy", keyword_workflow, "extract_keywords"),
    ("faq_retrieval", "faq_provider", "What is the annual leave policy?", faq_workflow, "retrieve_faq"),
])
def test_fixed_workflow_events_match_saved_outcome(request, monkeypatch, intent, provider, source, workflow, tool):
    request.getfixturevalue(provider)(source)
    monkeypatch.setattr(runtime, "classify_request", lambda _: (intent, 1, 0.71))
    body = {**BODY, "message": "Please analyze: " + source}
    response, events = post(body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["session_id"] == body["session_id"] and e["turn_id"] == body["turn_id"] and e["version"] == 1 for e in events)
    assert [e["event"] for e in events] == ["turn", "classification", "routing", "step_started", "step_finished",
                                           "step_started", "step_finished", "step_started", "step_finished", "final"]
    starts = {e["sequence"]: e for e in events if e["event"] == "step_started"}
    final = events[-1]
    assert final["outcome"] == "saved" and final["http_status"] == 200
    saved = sessions.get_chat(body["session_id"])["turns"][0]
    assert saved["state"] == "finished" and jsonable_encoder(saved["execution"]) == final["execution"]
    finishes = [e for e in events if e["event"] == "step_finished"]
    for event, stage in zip(finishes, final["execution"]["workflow_trace"]):
        assert starts[event["step_id"]]["name"] == stage["stage"]
        assert all(event[key] == value for key, value in stage.items())
    actual_tool = finishes[1]
    trace = final["execution"]["trace"][0]
    assert starts[actual_tool["step_id"]]["kind"] == "tool"
    assert actual_tool["arguments"] == trace["arguments"] and actual_tool["result"] == trace["result"]
    assert trace["tool"] == tool
    before = sessions.get_chat(body["session_id"])
    monkeypatch.setattr(sessions, "execute_request", Mock(side_effect=AssertionError("Replay executed")))
    _, replay = post(body)
    assert [e["event"] for e in replay] == ["turn", "final"]
    assert replay[-1]["execution"] == final["execution"]
    assert sessions.get_chat(body["session_id"]) == before


def final_reply():
    return AIMessage(content=json.dumps({"status": "completed", "reply": "Done"}),
                     response_metadata={"finish_reason": "stop"})


def test_handoff_and_agent_failed_tool_retains_validated_events(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, .71))
    extraction = sentiment_workflow._Extraction(status="agent_required", source_text=None, reason="compound_request")
    monkeypatch.setattr(sentiment_workflow, "_invoke", lambda *args: extraction)
    model = Mock()
    model.invoke.side_effect = [AIMessage(content="private model text", tool_calls=[{
        "name": "analyze_sentiment", "args": {"text": "I am happy"}, "id": "first",
    }], response_metadata={"finish_reason": "tool_calls"})]
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    monkeypatch.setitem(agent._TOOLS, "analyze_sentiment", (agent.TextArguments,
        Mock(side_effect=RuntimeError("private credentials")), "sentiment"))
    _, events = post(BODY)
    assert [e["route"] for e in events if e["event"] == "routing"] == ["llm_assisted", "agent"]
    assert "private model text" not in json.dumps(events) and "private credentials" not in json.dumps(events)
    final = events[-1]
    assert final["http_status"] == 503 and final["execution"]["status"] == "error"
    tool = next(e for e in events if e.get("tool") == "analyze_sentiment")
    trace = final["execution"]["trace"][0]
    assert all(tool[key] == value for key, value in trace.items())
    assert tool["arguments"] == {"text": "I am happy"} and tool["status"] == "failed"
    assert final["execution"]["workflow_trace"][0]["reason"] == "compound_request"


def test_agent_partial_failure_preserves_successful_observation(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("compound_request", 1, .71))
    model = Mock()
    model.invoke.side_effect = [AIMessage(content="", tool_calls=[{
        "name": "analyze_sentiment", "args": {"text": "I am happy"}, "id": "first",
    }], response_metadata={"finish_reason": "tool_calls"}), RuntimeError("private provider details")]
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    _, events = post(BODY)
    result = events[-1]["execution"]
    assert result["status"] == "partial_failure" and events[-1]["http_status"] == 503
    assert result["trace"][0]["result"]["label"] == "positive"
    assert any(e.get("status") == "failed" and e.get("reason") == "provider_unavailable" for e in events)
    assert "private provider details" not in json.dumps(events)


def test_presentation_failure_keeps_tool_result(monkeypatch, sentiment_provider):
    model = sentiment_provider("I am happy")
    model.invoke.side_effect = [AIMessage(content=json.dumps({"status": "ready", "source_text": "I am happy", "reason": "explicit_source"}),
                                         response_metadata={"finish_reason": "stop"}), RuntimeError("private")]
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, .71))
    _, events = post(BODY)
    assert events[-2]["stage"] == "explain_result" and events[-2]["status"] == "failed"
    final = events[-1]
    assert final["execution"]["status"] == "partial_failure" and final["outcome"] == "saved"
    assert final["execution"]["result"]["label"] == "positive"


def test_runtime_failure_is_saved_sanitized_and_replayable(monkeypatch):
    classify = Mock(side_effect=RuntimeError("private classifier path"))
    monkeypatch.setattr(runtime, "classify_request", classify)
    _, events = post(BODY)
    assert [e["event"] for e in events] == ["turn", "failure"]
    assert events[-1]["outcome"] == "saved" and events[-1]["code"] == "runtime_unavailable"
    assert sessions.get_chat("events")["turns"][0]["state"] == "finished"
    _, replay = post(BODY)
    assert replay[-1] == events[-1] and classify.call_count == 1
    assert "private classifier path" not in json.dumps(events)


def test_invalid_and_conflicting_submission_never_execute(monkeypatch):
    execute = Mock()
    monkeypatch.setattr(chat, "execute_session_request", execute)
    response, _ = post({**BODY, "message": " "})
    assert response.status_code == 422 and execute.call_count == 0
    # Restore the real session entry point and use a completed turn for a conflict.
    monkeypatch.setattr(chat, "execute_session_request", sessions.execute_session_request)
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("out_of_scope", 1, .71))
    model = Mock(invoke=Mock(return_value=final_reply()))
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    post(BODY)
    _, events = post({**BODY, "message": "Different content"})
    assert events[-1]["http_status"] == 409 and events[-1]["code"] == "chat_turn_conflict"
    assert model.invoke.call_count == 1


def test_unsaved_finalization_and_restart_recovery_never_repeat(monkeypatch, sentiment_provider):
    sentiment_provider("I am happy")
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, .71))
    store = sessions._get_store()
    finish = Mock(side_effect=ChatPersistenceError("private storage detail"))
    monkeypatch.setattr(store, "finish", finish)
    _, events = post(BODY)
    assert events[-1]["event"] == "failure" and events[-1]["outcome"] == "unsaved"
    assert all(e["event"] != "final" for e in events)
    assert any(e.get("stage") == "analyze_sentiment" and e["result"]["label"] == "positive" for e in events)
    # TestClient lifespan closes ownership; the next owner performs recovery.
    saved = sessions.get_chat("events")["turns"][0]
    assert saved["state"] == "interrupted" and saved["execution"] is None
    monkeypatch.setattr(sessions, "execute_request", Mock(side_effect=AssertionError("Repeated execution")))
    _, recovery = post(BODY)
    assert recovery[-1]["http_status"] == 409 and recovery[-1]["state"] == "interrupted"
    assert "private storage detail" not in json.dumps(events)


def test_initial_persistence_failure_prevents_classification(monkeypatch):
    classify = Mock()
    monkeypatch.setattr(runtime, "classify_request", classify)
    monkeypatch.setattr(sessions, "_get_store", Mock(side_effect=ChatPersistenceError("Storage unavailable.")))
    _, events = post(BODY)
    assert events[-1]["outcome"] == "not_started" and classify.call_count == 0


@pytest.fixture
def live_backend():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = monotonic() + 5
    while not server.started and thread.is_alive() and monotonic() < deadline:
        sleep(.01)
    assert server.started
    yield f"http://127.0.0.1:{port}", server, thread
    server.should_exit = True
    thread.join(5)
    assert not thread.is_alive()
    sock.close()


def read_events(response):
    for line in response.iter_lines():
        if line.startswith("data: "):
            yield json.loads(line[6:])


def test_real_http_progress_disconnect_recovery_and_shutdown(monkeypatch, sentiment_provider, live_backend):
    sentiment_provider("I am happy")
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, .71))
    entered, release = Event(), Event()
    tool = sentiment_workflow.analyze_sentiment
    calls = []

    def delayed(text):
        calls.append(text)
        entered.set()
        assert release.wait(5), "Controlled tool was not released"
        return tool(text)

    monkeypatch.setattr(sentiment_workflow, "analyze_sentiment", delayed)
    base, server, thread = live_backend
    try:
        with httpx2.Client(base_url=base, timeout=5) as client:
            with client.stream("POST", "/api/v1/chat/stream", json=BODY) as response:
                events = read_events(response)
                while True:
                    event = next(events)
                    if event.get("name") == "analyze_sentiment":
                        break
                assert event["event"] == "step_started" and entered.wait(1)
                assert not release.is_set()
                saved = client.get("/api/v1/chats/events").json()["turns"][0]
                assert saved["state"] == "running" and saved["execution"] is None
            # The real HTTP subscriber has disconnected. Graceful shutdown must
            # wait for this worker before closing storage ownership.
            server.should_exit = True
            sleep(.15)
            assert thread.is_alive()
            release.set()
            thread.join(5)
            assert not thread.is_alive()
        saved = sessions.get_chat("events")["turns"][0]
        assert saved["state"] == "finished" and saved["execution"]["result"]["label"] == "positive"
        monkeypatch.setattr(sessions, "execute_request", Mock(side_effect=AssertionError("Replay executed")))
        _, replay = post(BODY)
        assert [e["event"] for e in replay] == ["turn", "final"]
        assert replay[-1]["execution"] == saved["execution"] and calls == ["I am happy"]
    finally:
        release.set()


def test_event_context_isolates_concurrent_chats(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("out_of_scope", 1, .71))
    monkeypatch.setattr(agent, "_create_model", lambda: Mock(invoke=lambda _: final_reply()))

    async def collect(name):
        return [event async for event in stream_turn(name, "Hello", name + "-turn", sessions.execute_session_request)]

    async def scenario():
        results = await asyncio.gather(collect("one"), collect("two"))
        await drain_stream_workers()
        return results

    for name, frames in zip(["one", "two"], asyncio.run(scenario())):
        events = decode("".join(frames))
        assert all(e["session_id"] == name and e["turn_id"] == name + "-turn" for e in events)
        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        assert events[-1]["outcome"] == "saved"


@pytest.mark.parametrize("status,reason", [
    ("needs_clarification", "missing_source"),
    ("error", "invalid_output"),
])
def test_extraction_stops_without_tool_events(monkeypatch, status, reason):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("sentiment_analysis", 1, .71))
    if status == "error":
        monkeypatch.setattr(sentiment_workflow, "_invoke", Mock(side_effect=sentiment_workflow._WorkflowError(reason)))
    else:
        extraction = sentiment_workflow._Extraction(status=status, source_text=None, reason=reason)
        monkeypatch.setattr(sentiment_workflow, "_invoke", lambda *args: extraction)
    tool = Mock(side_effect=AssertionError("Tool should not run"))
    monkeypatch.setattr(sentiment_workflow, "analyze_sentiment", tool)
    _, events = post(BODY)
    assert [e["name"] for e in events if e["event"] == "step_started"] == ["extract_source"]
    assert events[-1]["execution"]["status"] == status and tool.call_count == 0
    assert events[-2]["reason"] == reason


def test_invalid_agent_arguments_do_not_emit_tool_start(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("out_of_scope", 1, .71))
    response = AIMessage(content="", tool_calls=[{
        "name": "analyze_sentiment", "args": {"text": 42}, "id": "invalid",
    }], response_metadata={"finish_reason": "tool_calls"})
    monkeypatch.setattr(agent, "_create_model", lambda: Mock(invoke=lambda _: response))
    _, events = post(BODY)
    assert events[-1]["execution"]["agent_reason"] == "invalid_tool_arguments"
    assert not any(e.get("kind") == "tool" for e in events)


def test_generated_identity_and_literal_ids_cannot_inject_frames(monkeypatch):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("out_of_scope", 1, .71))
    monkeypatch.setattr(agent, "_create_model", lambda: Mock(invoke=lambda _: final_reply()))
    body = {"session_id": "literal\nevent: injected", "message": "Hello\ndata: injected"}
    response, events = post(body)
    assert len(events[0]["turn_id"]) == 32
    assert all(e["session_id"] == body["session_id"] for e in events)
    assert "\nevent: injected\n" not in response.text
    assert "\ndata: injected\n" not in response.text
    assert all(e["turn_id"] == events[0]["turn_id"] for e in events)
