import io
import json
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest
from streamlit.testing.v1 import AppTest

from app import agent, runtime, sessions, ui_client
from app.main import app
from app.tools.summarization import SummaryResult
from app.tools.email_drafting import EmailDraftResult, _ACTION_INSTRUCTIONS


SCRIPT = Path(__file__).resolve().parents[1] / "streamlit_app.py"


class StreamResponse(io.BytesIO):
    def __init__(self, text):
        super().__init__(text.encode())
        self.status = 200
        self.headers = {"Content-Type": "text/event-stream"}


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(json.dumps(payload).encode())
        self.status = status


def execution(session_id="one", status="completed"):
    return dict(session_id=session_id, status=status, predicted_intent="email_drafting",
                confidence=0.52, route="agent", reason="intent_requires_agent", result=None,
                trace=[], elapsed_ms=12.3456789, reply="Draft only", agent_reason=None, workflow_trace=[])


@pytest.fixture(autouse=True)
def offline_sessions(monkeypatch, sentiment_provider, keyword_provider):
    monkeypatch.setattr(sessions, "_sessions", {})
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected provider initialization"))


def test_client_preserves_request_and_backend_fields(monkeypatch):
    data = execution()
    send = Mock(return_value=Response(data))
    monkeypatch.setattr(ui_client, "urlopen", send)
    assert ui_client.submit_chat("http://localhost:8000/", "one", "  Hi\nthere  ") == data
    request = send.call_args.args[0]
    assert request.full_url == "http://localhost:8000/api/v1/chat"
    assert request.method == "POST"
    assert json.loads(request.data) == {"session_id": "one", "message": "  Hi\nthere  "}
    assert send.call_args.kwargs == {"timeout": 210}
    assert send.call_count == 1


def test_client_retains_http_503_partial_observations(monkeypatch):
    data = execution(status="partial_failure")
    data["agent_reason"] = "provider_unavailable"
    data["trace"] = [dict(tool="draft_email", arguments={"recipient": "Alex", "content": "Friday"},
                          status="completed", result={"email_draft": {"recipient": "Alex", "subject": "Friday",
                          "body": "Hi Alex,\nFriday."}, "action_instructions": ["Review before sending."]},
                          reason=None, elapsed_ms=1.23456789)]
    data["trace"].append(dict(tool="summarize_text", arguments={"text": "Friday"}, status="failed",
                              result=None, reason="timeout", elapsed_ms=2.3456789))
    error = HTTPError("http://localhost", 503, "unavailable", {}, Response(data))
    monkeypatch.setattr(ui_client, "urlopen", Mock(side_effect=error))
    assert ui_client.submit_chat("http://localhost", "one", "Hi") == data


@pytest.mark.parametrize("failure", [URLError("private key"), TimeoutError("private key")])
def test_transport_failure_safe_and_never_retried(monkeypatch, failure):
    send = Mock(side_effect=failure)
    monkeypatch.setattr(ui_client, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError, match="may have executed") as error:
        ui_client.submit_chat("http://localhost", "one", "private message")
    assert "private" not in str(error.value)
    assert send.call_count == 1


@pytest.mark.parametrize("status,payload", [
    (422, {"detail": "private input"}), (503, {"detail": "private server"}),
    (200, {"unexpected": "private response"}), (200, execution("another-session")),
    (200, execution(status="error")), (503, execution()),
])
def test_rejected_invalid_or_mismatched_response_not_displayed(monkeypatch, status, payload):
    monkeypatch.setattr(ui_client, "urlopen", lambda *args, **kwargs: Response(payload, status))
    with pytest.raises(ui_client.ChatClientError) as error:
        ui_client.submit_chat("http://localhost", "one", "Hi")
    assert "private" not in str(error.value)


def test_malformed_json_safe(monkeypatch):
    response = Response({})
    response.seek(0)
    response.write(b"not json")
    response.seek(0)
    monkeypatch.setattr(ui_client, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ui_client.ChatClientError, match="invalid response"):
        ui_client.submit_chat("http://localhost", "one", "Hi")


def connect_api(monkeypatch):
    client = TestClient(app)
    recorded = []

    def send(request, **kwargs):
        body = json.loads(request.data) if request.data else None
        response = client.request(request.method, request.full_url, json=body)
        if request.full_url.endswith("/api/v1/chat/stream"):
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            final_event = events[-1]
            if final_event["event"] == "final":
                recorded.append((body, {"session_id": body["session_id"], "turn_id": body["turn_id"],
                                       **final_event["execution"]}))
            else:
                recorded.append((body, final_event))
            return StreamResponse(response.text)
        if request.full_url.endswith("/api/v1/chat"):
            recorded.append((body, response.json()))
        return Response(response.json(), response.status_code)

    monkeypatch.setattr(ui_client, "urlopen", send)
    return recorded


def send_message(ui, message):
    ui.text_area(key="composer").set_value(message).run()
    ui.button(key="send_message").click().run()
    return ui


def test_ui_sentiment_workflow_and_activity_match_backend_without_resubmit(monkeypatch, sentiment_provider):
    model = sentiment_provider("I am happy", "VADER classified this text as positive.")
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    assert not ui.exception
    send_message(ui, "Just check the sentiment of this I am happy")
    assert not ui.exception
    data = recorded[0][1]
    assert data["result"]["label"] == "positive"
    assert data["route"] == "llm_assisted" and model.invoke.call_count == 2
    assert ui.session_state["turns"][0]["execution"] == data
    displayed_json = [json.loads(element.value) for element in ui.json]
    assert data["result"] in displayed_json
    assert data["trace"][0]["arguments"] in displayed_json
    text = "\n".join(element.value for element in ui.text)
    for value in (data["predicted_intent"], str(data["confidence"]), data["route"], data["reason"],
                  str(data["elapsed_ms"]), str(data["trace"][0]["elapsed_ms"])):
        assert value in text
    assert data["reply"] in text
    assistant = ui.chat_message[1]
    assert "Sentiment: positive" in [element.value for element in assistant.text]
    assert not assistant.json
    for stage in data["workflow_trace"]:
        assert stage["stage"] in text and str(stage["elapsed_ms"]) in text
    assert not ui.button(key="send_message").disabled
    ui.run()
    assert len(recorded) == 1
    assert model.invoke.call_count == 2
    assert ui.session_state["pending"] is False


@pytest.mark.parametrize("scenario", ["matched", "no_match", "presentation_failure"])
def test_ui_faq_reply_and_activity_preserve_outcome_without_resubmit(monkeypatch, faq_provider, scenario):
    question = "What is the cafeteria policy?" if scenario == "no_match" else "What is the remote-work policy?"
    model = faq_provider(question)
    if scenario == "presentation_failure":
        model.invoke.side_effect = [
            AIMessage(content=json.dumps({"status": "ready", "question": question, "reason": "explicit_question"}),
                      response_metadata={"finish_reason": "stop"}),
            RuntimeError("private credentials"),
        ]
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Please answer this FAQ: " + question)
    assert not ui.exception
    data = recorded[0][1]
    assert data["route"] == "llm_assisted"
    assert data["status"] == {"matched": "completed", "no_match": "needs_clarification",
                              "presentation_failure": "partial_failure"}[scenario]
    assert "FAQ workflow stages" in [element.label for element in ui.expander]
    assistant = ui.chat_message[1]
    assert data["reply"] in [element.value for element in assistant.text]
    assert len(assistant.json) == 0
    assert data["result"] in [json.loads(element.value) for element in ui.expander[0].json]
    assert "Fictional demo policy — verify your actual company policy." not in [
        element.value for element in ui.caption
    ]
    assert data["result"] in [json.loads(element.value) for element in ui.json]
    text = "\n".join(element.value for element in ui.text)
    for stage in data["workflow_trace"]:
        assert stage["stage"] in text and str(stage["elapsed_ms"]) in text
    captions = [element.value for element in ui.caption]
    assert captions.count("LLM stage") == (1 if scenario == "no_match" else 2)
    assert captions.count("Local tool stage") == 1
    calls = 1 if scenario == "no_match" else 2
    assert model.invoke.call_count == calls
    saved = json.loads(sessions._sessions[data["session_id"]].history.messages[-1].content)
    for field in ("result", "reply", "trace", "workflow_trace", "status"):
        assert saved[field] == data[field]
    ui.run()
    assert not ui.exception and len(recorded) == 1
    assert model.invoke.call_count == calls and ui.session_state["pending"] is False


def final(status="completed", reply="Done"):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


def test_ui_agent_clarification_followup_and_browser_isolation(monkeypatch):
    recorded = connect_api(monkeypatch)
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("email_drafting", 1, 0.71))
    model = Mock()
    model.invoke.side_effect = [final("needs_clarification", "Who is the recipient?"), final(), final()]
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Draft an email")
    assert not ui.warning and not ui.error
    assert "Execution: needs_clarification" not in [element.value for element in ui.caption]
    assert "Who is the recipient?" in [element.value for element in ui.text]
    send_message(ui, "Alex")
    assert not ui.exception
    assert recorded[0][0]["session_id"] == recorded[1][0]["session_id"]
    messages = model.invoke.call_args_list[1].args[0]
    assert messages[-3].content == "Draft an email" and messages[-1].content == "Alex"
    other = AppTest.from_file(str(SCRIPT)).run()
    other.button(key="new_chat").click().run()
    send_message(other, "Another email")
    assert recorded[2][0]["session_id"] != recorded[0][0]["session_id"]
    assert len(model.invoke.call_args_list[2].args[0]) == 2
    ui.run()
    assert len(recorded) == 3
    assert "STATUS  needs_clarification" in "\n".join(element.value for element in ui.text)


def test_ui_partial_failure_retains_successful_step(monkeypatch):
    recorded = connect_api(monkeypatch)
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("compound_request", 1, 0.71))
    model = Mock()
    model.invoke.side_effect = [AIMessage(content="", tool_calls=[{
        "name": "analyze_sentiment", "args": {"text": "I am happy"}, "id": "call1",
    }], response_metadata={"finish_reason": "tool_calls"}), RuntimeError("private credentials")]
    monkeypatch.setattr(agent, "_create_model", lambda: model)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Analyze and then draft")
    assert not ui.exception
    data = recorded[0][1]
    assert data["status"] == "partial_failure"
    assert ui.session_state["turns"][0]["execution"] == data
    assert "Execution: partial_failure" in [element.value for element in ui.error]
    assert data["trace"][0]["result"] in [json.loads(element.value) for element in ui.json]
    assert "private credentials" not in str(ui)


def test_ui_sentiment_presentation_failure_retains_score_stages_and_reply_without_retry(monkeypatch, sentiment_provider):
    model = sentiment_provider("I am happy")
    extraction = AIMessage(content=json.dumps({"status": "ready", "source_text": "I am happy", "reason": "explicit_source"}),
                           response_metadata={"finish_reason": "stop"})
    model.invoke.side_effect = [extraction, RuntimeError("private credentials")]
    sent_pairs = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Just check the sentiment of this I am happy")
    assert not ui.exception
    data = sent_pairs[0][1]
    assert data["route"] == "llm_assisted" and data["status"] == "partial_failure"
    assert data["reason"] == "presentation_failed" and data["result"]["label"] == "positive"
    assert data["trace"][0]["status"] == "completed"
    assert data["workflow_trace"][-1]["status"] == "failed"
    assert ui.session_state["turns"][0]["execution"] == data
    assert data["result"] in [json.loads(element.value) for element in ui.json]
    assert data["reply"] in [element.value for element in ui.text]
    assert "Sentiment: positive" in [element.value for element in ui.chat_message[1].text]
    assert not ui.chat_message[1].json
    session_id = data["session_id"]
    saved = json.loads(sessions._sessions[session_id].history.messages[-1].content)
    assert saved["result"] == data["result"] and saved["reply"] == data["reply"]
    assert saved["workflow_trace"] == data["workflow_trace"]
    ui.run()
    assert not ui.exception and len(sent_pairs) == 1 and model.invoke.call_count == 2
    assert len(sessions._sessions[session_id].history.messages) == 2
    assert "private credentials" not in str(ui)


def test_ui_connection_failure_persists_without_retry_or_stale_activity(monkeypatch):
    send = Mock(side_effect=ui_client.ChatClientError("Connection failed; outcome unknown."))
    connect_api(monkeypatch)
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Hi")
    assert not ui.exception and ui.session_state["pending"] is False
    assert ui.session_state["turns"][0]["execution"] is None
    assert len(ui.error) == 1
    assert ui.button(key="send_message").disabled
    ui.run()
    assert send.call_count == 1


@pytest.mark.parametrize("message", [" \n", "x" * 10001], ids=["blank", "too-long"])
def test_ui_input_bounds_before_submission(monkeypatch, message):
    send = Mock()
    connect_api(monkeypatch)
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, message)
    assert not ui.exception
    assert not ui.session_state["turns"]
    if len(message) > 10000:
        # Native text_area truncates oversized input before the application sees it.
        assert send.call_count == 1 and send.call_args.args[2] == message[:10000]
    else:
        send.assert_not_called()


def test_ui_source_is_plain_text_not_executable_markup(monkeypatch):
    def send(url, session_id, message, *, turn_id, on_event=None):
        data = execution(session_id)
        data["reply"] = '<script>private()</script> ![remote](https://example.com/image)'
        store = sessions._get_store()
        store.begin(session_id, message, turn_id)
        data["turn_id"] = turn_id
        store.finish(turn_id, execution={k: v for k, v in data.items() if k not in {"session_id", "turn_id"}})
        return data

    connect_api(monkeypatch)
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "<b>input</b>")
    assert not ui.exception
    assert "<b>input</b>" in [element.value for element in ui.text]
    assert any("<script>" in element.value for element in ui.text)


def test_ui_keyword_workflow_and_activity_match_backend_without_resubmit(monkeypatch, keyword_provider):
    model = keyword_provider("The server failed after the deployment", "Here are the keywords extracted from your text and their scores.")
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    assert not ui.exception
    send_message(ui, "Find keywords in this The server failed after the deployment")
    assert not ui.exception
    data = recorded[0][1]
    assert data["result"] and data["trace"][0]["tool"] == "extract_keywords"
    assert "Keyword workflow stages" in [element.label for element in ui.expander]
    assert [element.value for element in ui.caption].count("LLM stage") == 2
    assert "Local tool stage" in [element.value for element in ui.caption]
    assert data["route"] == "llm_assisted" and model.invoke.call_count == 2
    assert ui.session_state["turns"][0]["execution"] == data
    displayed_json = [json.loads(element.value) for element in ui.json]
    assert displayed_json.count(data["result"]) == 1  # Activity only.
    assert len(ui.dataframe) == 1
    table = ui.dataframe[0]
    assert table.value.to_dict("records") == [
        {"Phrase": item["phrase"], "Score": item["score"]} for item in data["result"]
    ]
    assert json.loads(table.proto.columns)["Score"]["type_config"]["format"] == "%.5f"
    assert "not confidence probabilities" in "\n".join(element.value for element in ui.caption)
    assert data["trace"][0]["arguments"] in displayed_json
    text = "\n".join(element.value for element in ui.text)
    for value in (data["predicted_intent"], str(data["confidence"]), data["route"], data["reason"],
                  str(data["elapsed_ms"]), str(data["trace"][0]["elapsed_ms"])):
        assert value in text
    assert data["reply"] in text
    for stage in data["workflow_trace"]:
        assert stage["stage"] in text and str(stage["elapsed_ms"]) in text
    assert not ui.button(key="send_message").disabled
    ui.run()
    assert len(recorded) == 1
    assert model.invoke.call_count == 2
    assert ui.session_state["pending"] is False


def test_ui_keyword_presentation_failure_retains_phrases_stages_and_reply_without_retry(monkeypatch, keyword_provider):
    model = keyword_provider("The server failed after the deployment")
    extraction = AIMessage(content=json.dumps({"status": "ready", "source_text": "The server failed after the deployment", "reason": "explicit_source"}),
                           response_metadata={"finish_reason": "stop"})
    model.invoke.side_effect = [extraction, RuntimeError("private credentials")]
    sent_pairs = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Find keywords in this The server failed after the deployment")
    assert not ui.exception
    data = sent_pairs[0][1]
    assert data["route"] == "llm_assisted" and data["status"] == "partial_failure"
    assert data["reason"] == "presentation_failed" and bool(data["result"])
    assert data["trace"][0]["status"] == "completed"
    assert data["workflow_trace"][-1]["status"] == "failed"
    assert ui.session_state["turns"][0]["execution"] == data
    assert [json.loads(element.value) for element in ui.json].count(data["result"]) == 1
    assert ui.dataframe[0].value.to_dict("records") == [
        {"Phrase": item["phrase"], "Score": item["score"]} for item in data["result"]
    ]
    assert "introduction is unavailable" in data["reply"]
    assert data["reply"] in [element.value for element in ui.text]
    session_id = data["session_id"]
    saved = json.loads(sessions._sessions[session_id].history.messages[-1].content)
    assert saved["result"] == data["result"] and saved["reply"] == data["reply"]
    assert saved["workflow_trace"] == data["workflow_trace"]
    ui.run()
    assert not ui.exception and len(sent_pairs) == 1 and model.invoke.call_count == 2
    assert len(sessions._sessions[session_id].history.messages) == 2
    assert "private credentials" not in str(ui)


def test_ui_keyword_empty_result_has_reply_without_empty_table(monkeypatch, keyword_provider):
    source = "!!!"
    model = keyword_provider(source, "No keyword candidates were found in the supplied text.")
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0.71))
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Find keywords: !!!")
    assert not ui.exception
    data = recorded[0][1]
    assert data["status"] == "completed" and data["result"] == []
    assert data["reply"] in [element.value for element in ui.text]
    assert not ui.dataframe
    assert [json.loads(element.value) for element in ui.json].count([]) == 1
    ui.run()
    assert len(recorded) == 1 and model.invoke.call_count == 2


def test_ui_keyword_table_keeps_phrases_as_literal_text(monkeypatch):
    phrase = "![remote](https://example.com/image) <script>private()</script>"
    scores = [{"phrase": phrase, "score": 0.0123456789}]

    def send(url, session_id, message, *, turn_id, on_event=None):
        data = execution(session_id)
        data.update(predicted_intent="keyword_extraction", route="llm_assisted",
                    result=scores, reply="Here are the extracted keywords and their scores.")
        store = sessions._get_store()
        store.begin(session_id, message, turn_id)
        data["turn_id"] = turn_id
        store.finish(turn_id, execution={k: v for k, v in data.items() if k not in {"session_id", "turn_id"}})
        return data

    connect_api(monkeypatch)
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, "Find keywords from supplied source")
    assert not ui.exception
    table = ui.dataframe[0]
    assert table.value.to_dict("records") == [{"Phrase": phrase, "Score": 0.0123456789}]
    assert "Phrase" not in json.loads(table.proto.columns)  # Default plain-text cells.
    assert not ui.get("imgs") and not ui.get("iframe")


@pytest.mark.parametrize("route,status,with_tool", [
    ("direct", "completed", True), ("agent", "completed", True),
    ("agent", "completed", False), ("agent", "needs_clarification", False),
    ("agent", "error", True), ("agent", "partial_failure", True),
])
def test_restored_activity_belongs_to_each_turn_without_execution(monkeypatch, route, status, with_tool):
    recorded = connect_api(monkeypatch)
    execute = Mock(side_effect=AssertionError("Restoration must not execute"))
    monkeypatch.setattr(sessions, "execute_request", execute)
    chat = sessions.create_chat()["session_id"]
    store = sessions._get_store()
    outcomes = []
    for number in range(2):
        data = execution(chat, status)
        data.update(route=route, reason=f"route_reason_{number}",
                    confidence=0.8 + number / 10, elapsed_ms=10.123 + number,
                    reply=f"Answer {number}", agent_reason=f"outcome_{number}")
        if route == "direct":
            data.update(predicted_intent="sentiment_analysis", agent_reason=None)
        if with_tool:
            data["trace"] = [dict(tool="analyze_sentiment", arguments={"text": f"Source {number}"},
                                  result={"label": "positive"} if status != "error" else None,
                                  status="failed" if status == "error" else "completed",
                                  reason="tool_failed" if status == "error" else None,
                                  elapsed_ms=1.234 + number)]
        store.begin(chat, f"Message {number}", f"saved-{number}")
        store.finish(f"saved-{number}", execution={k: v for k, v in data.items() if k != "session_id"})
        outcomes.append(data)
    sessions.close_chat_store()
    sessions._sessions.clear()
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params["chat"] = chat
    ui.run()
    assert not ui.exception and not ui.selectbox
    assert "Execution inspector" not in [item.value for item in ui.subheader]
    for number, data in enumerate(outcomes):
        assistant = ui.chat_message[number * 2 + 1]
        assert data["reply"] in [item.value for item in assistant.text]
        prompt = ui.get_by_key("prompt_saved-" + str(number))
        details = ui.get_by_key("details_saved-" + str(number))
        answer = ui.get_by_key("answer_saved-" + str(number))
        assert f"Message {number}" in [item.value for item in prompt.text]
        assert data["reply"] in [item.value for item in answer.text]
        assert not assistant.expander
        activity = details.expander[0]
        assert activity.label == "Activity" and not activity.proto.expanded
        text = "\n".join(item.value for item in activity.text)
        for value in (data["reason"], str(data["confidence"]),
                      str(data["elapsed_ms"]), f"ROUTE  {route}", f"STATUS  {status}"):
            assert value in text
        if data["agent_reason"] is not None:
            assert data["agent_reason"] in text
        assert outcomes[1 - number]["reason"] not in text
        if with_tool:
            tool = activity.expander[0]
            assert not tool.proto.expanded
            assert str(data["trace"][0]["elapsed_ms"]) in "\n".join(item.value for item in tool.text)
            if status == "error":
                assert "Step reason: tool_failed" in [item.value for item in tool.text]
            assert data["trace"][0]["arguments"] in [json.loads(item.value) for item in tool.json]
            assert data["trace"][0]["result"] in [json.loads(item.value) for item in tool.json]
        else:
            assert "No tool executions reported." in [item.value for item in activity.caption]
    ui.run()
    assert not ui.exception and not recorded
    execute.assert_not_called()


@pytest.mark.parametrize('route,status,result', [
    ('direct', 'completed', {'label': 'negative', 'compound': -0.3456789,
                            'positive': 0.0, 'neutral': 0.7, 'negative': 0.3}),
    ('llm_assisted', 'completed', {'label': 'neutral', 'compound': 0.0,
                                  'positive': 0.0, 'neutral': 1.0, 'negative': 0.0}),
    ('llm_assisted', 'needs_clarification', None),
    ('llm_assisted', 'error', None),
    ('direct', 'completed', None),
])
def test_restored_sentiment_answer_keeps_scores_in_activity_without_execution(monkeypatch, route, status, result):
    recorded = connect_api(monkeypatch)
    execute = Mock(side_effect=AssertionError('Restoration must not execute'))
    monkeypatch.setattr(sessions, 'execute_request', execute)
    chat = sessions.create_chat()['session_id']
    data = execution(chat, status)
    data.update(predicted_intent='sentiment_analysis', route=route, result=result,
                reply='Please supply the text.' if status == 'needs_clarification' else None)
    if result is not None:
        data['trace'] = [dict(tool='analyze_sentiment', arguments={'text': 'Saved source'},
                              result=result, status='completed', reason=None, elapsed_ms=1.23456789)]
    store = sessions._get_store()
    store.begin(chat, 'Saved request', 'saved-sentiment')
    store.finish('saved-sentiment', execution={k: v for k, v in data.items() if k != 'session_id'})
    sessions.close_chat_store()
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params['chat'] = chat
    for _ in range(2):
        ui.run()
        assert not ui.exception
        assistant = ui.chat_message[1]
        assert not assistant.json
        labels = [item.value for item in assistant.text if item.value.startswith('Sentiment:')]
        assert labels == ([] if result is None else ['Sentiment: ' + result['label']])
        assert bool(assistant.error) == (status == 'error')
        if data['reply']:
            assert data['reply'] in [item.value for item in assistant.text]
        if result is not None:
            activity = ui.get_by_key('details_saved-sentiment')
            assert result in [json.loads(item.value) for item in activity.json]
    assert not recorded and execute.call_count == 0


@pytest.mark.parametrize('points', [['Resolved **outage**; <review> before release.'], []])
def test_single_summary_submission_shows_saved_content_once(monkeypatch, points):
    recorded = connect_api(monkeypatch)
    monkeypatch.setattr(runtime, 'classify_request', lambda _: ('summarization', 1, 0.71))
    result = {'summary': 'The outage is resolved.\n[Next step](literal): review the release.',
              'key_points': points}
    summarize = Mock(return_value=SummaryResult(**result))
    schema, _, description = agent._TOOLS['summarize_text']
    monkeypatch.setitem(agent._TOOLS, 'summarize_text', (schema, summarize, description))
    model = Mock()
    model.invoke.side_effect = [
        AIMessage(content='', tool_calls=[{'name': 'summarize_text',
                  'args': {'text': 'The outage is resolved. Review the release.'}, 'id': 'summary1'}],
                  response_metadata={'finish_reason': 'tool_calls'}),
        AIMessage(content=json.dumps({'status': 'completed', 'reply': 'A generated summary reply.'}),
                  response_metadata={'finish_reason': 'stop'}),
    ]
    monkeypatch.setattr(agent, '_create_model', lambda: model)
    ui = AppTest.from_file(str(SCRIPT)).run()
    send_message(ui, 'Summarize this: The outage is resolved. Review the release.')
    for _ in range(2):
        assert not ui.exception
        answer = ui.chat_message[1]
        assert [item.value for item in answer.text] == [result['summary'], *['• ' + p for p in points]]
        assert ('Key points' in [item.value for item in answer.caption]) == bool(points)
        assert not answer.json and not answer.markdown
        assert result in [json.loads(item.value) for item in ui.get_by_key('details_' + recorded[0][1]['turn_id']).json]
        ui.run()
    assert len(recorded) == 1 and model.invoke.call_count == 2
    summarize.assert_called_once_with(text='The outage is resolved. Review the release.')
    assert recorded[0][1]['reply'] == 'A generated summary reply.'


@pytest.mark.parametrize('scenario', ['summary', 'clarification', 'error', 'partial_failure',
                                      'missing_result', 'missing_points', 'compound', 'draft'])
def test_restored_summary_and_fallback_answers_never_execute(monkeypatch, scenario):
    recorded = connect_api(monkeypatch)
    execute = Mock(side_effect=AssertionError('Restoration must not execute'))
    monkeypatch.setattr(sessions, 'execute_request', execute)
    chat = sessions.create_chat()['session_id']
    status = {'clarification': 'needs_clarification', 'error': 'error',
              'partial_failure': 'partial_failure'}.get(scenario, 'completed')
    data = execution(chat, status)
    result = {'summary': 'Saved summary.\nSecond line.', 'key_points': ['Saved point.']}
    data['trace'] = [dict(tool='summarize_text', arguments={'text': 'Saved source'},
                          result=result, status='completed', reason=None, elapsed_ms=1.23456789)]
    if scenario == 'missing_result':
        data['trace'][0]['result'] = None
    elif scenario == 'missing_points':
        data['trace'][0]['result'] = {'summary': 'Legacy summary.'}
    elif scenario == 'compound':
        data['trace'].append(dict(tool='analyze_sentiment', arguments={'text': 'Happy'},
                                  result={'label': 'positive'}, status='completed', reason=None, elapsed_ms=2))
    elif scenario == 'draft':
        data['trace'][0]['tool'] = 'draft_email'
        data['trace'][0]['result'] = {'email_draft': {'recipient': 'Alex', 'subject': 'Saved',
                                                   'body': 'Saved draft.'},
                                     'action_instructions': ['Review before sending.']}
    store = sessions._get_store()
    store.begin(chat, 'Saved request', 'saved-summary')
    store.finish('saved-summary', execution={k: v for k, v in data.items() if k != 'session_id'})
    sessions.close_chat_store()
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params['chat'] = chat
    for _ in range(2):
        ui.run()
        assert not ui.exception
        answer = ui.chat_message[1]
        assert [item.value for item in answer.text] == (
            [result['summary'], '• Saved point.'] if scenario == 'summary' else
            ['Intended recipient: Alex', 'Subject: Saved', 'Saved draft.', '• Review before sending.']
            if scenario == 'draft' else [data['reply']])
        assert not answer.json
        activity = ui.get_by_key('details_saved-summary')
        for step in data['trace']:
            if step['result'] is not None:
                assert step['result'] in [json.loads(item.value) for item in activity.json]
    assert not recorded
    execute.assert_not_called()


@pytest.mark.parametrize('demo_history', [False, True])
def test_single_draft_submission_shows_literal_saved_fields_once(monkeypatch, demo_history):
    recorded = connect_api(monkeypatch)
    monkeypatch.setattr(runtime, 'classify_request', lambda _: ('email_drafting', 1, 0.71))
    chat = sessions.create_chat()['session_id']
    if demo_history:
        store = sessions._get_store()
        store.begin(chat, 'What is the policy?', 'policy-turn')
        store.finish('policy-turn', execution=execution(chat), demo_policy=True)
    result = {'email_draft': {'recipient': 'Alex [team](literal)', 'subject': 'Resolved **outage**',
                             'body': 'Hi Alex,\n\nThe outage is resolved.\n<Review> before release.'},
              'action_instructions': list(_ACTION_INSTRUCTIONS)}
    draft = Mock(return_value=EmailDraftResult(**result))
    schema, _, description = agent._TOOLS['draft_email']
    monkeypatch.setitem(agent._TOOLS, 'draft_email', (schema, draft, description))
    model = Mock()
    model.invoke.side_effect = [
        AIMessage(content='', tool_calls=[{'name': 'draft_email',
                  'args': {'recipient': result['email_draft']['recipient'], 'content': 'The outage is resolved.'},
                  'id': 'draft1'}], response_metadata={'finish_reason': 'tool_calls'}),
        final(reply='Generated reply'),
    ]
    monkeypatch.setattr(agent, '_create_model', lambda: model)
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params['chat'] = chat
    ui.run()
    send_message(ui, 'Draft an email to Alex saying the outage is resolved.')
    expected = (['Policy information below is fictional demo policy.'] if demo_history else []) + [
        'Intended recipient: ' + result['email_draft']['recipient'],
        'Subject: ' + result['email_draft']['subject'], result['email_draft']['body'],
        *['• ' + action for action in _ACTION_INSTRUCTIONS]]
    for _ in range(2):
        assert not ui.exception
        answer = ui.chat_message[-1]
        assert [item.value for item in answer.text] == expected
        assert 'Email draft' in [item.value for item in answer.caption]
        assert 'What you should do' in [item.value for item in answer.caption]
        assert not answer.json and not answer.markdown
        activity = ui.get_by_key('details_' + recorded[0][1]['turn_id'])
        assert result in [json.loads(item.value) for item in activity.json]
        ui.run()
    assert len(recorded) == 1 and model.invoke.call_count == 2 and draft.call_count == 1
    assert result['email_draft']['body'] in recorded[0][1]['reply']
    assert ('fictional demo policy' in recorded[0][1]['reply']) == demo_history


@pytest.mark.parametrize('scenario', ['clarification', 'error', 'partial_failure', 'compound',
                                      'failed_tool', 'missing_result', 'missing_body',
                                      'invalid_recipient', 'missing_actions', 'empty_actions', 'invalid_action'])
def test_restored_draft_fallback_preserves_reply_and_never_executes(monkeypatch, scenario):
    recorded = connect_api(monkeypatch)
    execute = Mock(side_effect=AssertionError('Restoration must not execute'))
    monkeypatch.setattr(sessions, 'execute_request', execute)
    chat = sessions.create_chat()['session_id']
    data = execution(chat, {'clarification': 'needs_clarification', 'error': 'error',
                           'partial_failure': 'partial_failure'}.get(scenario, 'completed'))
    result = {'email_draft': {'recipient': 'Alex', 'subject': 'Saved', 'body': 'Saved body.'},
              'action_instructions': ['Review before sending.']}
    data['trace'] = [dict(tool='draft_email', arguments={'recipient': 'Alex', 'content': 'Saved body.'},
                          result=result, status='completed', reason=None, elapsed_ms=1)]
    if scenario == 'compound':
        data['trace'].append(dict(tool='summarize_text', arguments={'text': 'Saved body.'},
                                  result={'summary': 'Saved summary.', 'key_points': []},
                                  status='completed', reason=None, elapsed_ms=2))
    elif scenario == 'failed_tool':
        data['trace'][0].update(status='failed', result=None, reason='provider_unavailable')
    elif scenario == 'missing_result':
        data['trace'][0]['result'] = None
    elif scenario == 'missing_body':
        del result['email_draft']['body']
    elif scenario == 'invalid_recipient':
        result['email_draft']['recipient'] = 17
    elif scenario == 'missing_actions':
        del result['action_instructions']
    elif scenario == 'empty_actions':
        result['action_instructions'] = []
    elif scenario == 'invalid_action':
        result['action_instructions'] = [None]
    store = sessions._get_store()
    store.begin(chat, 'Saved request', 'saved-draft')
    store.finish('saved-draft', execution={k: v for k, v in data.items() if k != 'session_id'})
    sessions.close_chat_store()
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params['chat'] = chat
    for _ in range(2):
        ui.run()
        assert not ui.exception
        answer = ui.chat_message[1]
        assert [item.value for item in answer.text] == [data['reply']]
        assert 'Email draft' not in [item.value for item in answer.caption]
        assert not answer.json
        activity = ui.get_by_key('details_saved-draft')
        for step in data['trace']:
            assert step['result'] in [json.loads(item.value) for item in activity.json]
    assert not recorded
    execute.assert_not_called()


@pytest.mark.parametrize('policy_location', ['later_turn', 'other_chat'])
def test_draft_qualification_does_not_leak_from_future_or_other_chat(monkeypatch, policy_location):
    recorded = connect_api(monkeypatch)
    chat = sessions.create_chat()['session_id']
    data = execution(chat)
    data['trace'] = [dict(tool='draft_email', arguments={'recipient': 'Alex', 'content': 'Resolved.'},
                          result={'email_draft': {'recipient': 'Alex', 'subject': 'Resolved', 'body': 'Resolved.'},
                                  'action_instructions': ['Review before sending.']},
                          status='completed', reason=None, elapsed_ms=1)]
    store = sessions._get_store()
    store.begin(chat, 'Draft an email', 'earlier-draft')
    store.finish('earlier-draft', execution={k: v for k, v in data.items() if k != 'session_id'})
    policy_chat = chat if policy_location == 'later_turn' else sessions.create_chat()['session_id']
    store.begin(policy_chat, 'Policy question', 'demo-policy')
    policy = execution(policy_chat)
    store.finish('demo-policy', execution={k: v for k, v in policy.items() if k != 'session_id'},
                 demo_policy=True)
    sessions.close_chat_store()
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params['chat'] = chat
    ui.run()
    assert not ui.exception
    answer = ui.get_by_key('answer_earlier-draft')
    assert [item.value for item in answer.text] == [
        'Intended recipient: Alex', 'Subject: Resolved', 'Resolved.', '• Review before sending.']
    assert not recorded


def test_empty_chat_shows_no_welcome_examples_or_execution(monkeypatch):
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    assert not ui.exception
    page_text = '\n'.join(item.value for item in [*ui.text, *ui.info])
    assert 'Just check the sentiment of this I am happy' not in page_text
    assert 'Find keywords in this The server failed after the deployment' not in page_text
    assert 'What is the remote work policy?' not in page_text
    assert 'fictional demo policies' not in page_text
    assert not recorded and not sessions.list_chats()
