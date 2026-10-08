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


SCRIPT = Path(__file__).resolve().parents[1] / "streamlit_app.py"


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
        body = json.loads(request.data)
        response = client.post("/api/v1/chat", json=body)
        recorded.append((body, response.json()))
        return Response(response.json(), response.status_code)

    monkeypatch.setattr(ui_client, "urlopen", send)
    return recorded


def test_ui_sentiment_workflow_and_inspector_match_backend_without_resubmit(monkeypatch, sentiment_provider):
    model = sentiment_provider("I am happy", "VADER classified this text as positive.")
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    assert not ui.exception
    ui.chat_input[0].set_value("Just check the sentiment of this I am happy").run()
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
    for stage in data["workflow_trace"]:
        assert stage["stage"] in text and str(stage["elapsed_ms"]) in text
    assert ui.chat_input[0].proto.submit_mode == ui.chat_input[0].proto.SUBMIT_MODE_DISABLE
    ui.run()
    assert len(recorded) == 1
    assert model.invoke.call_count == 2
    assert ui.session_state["pending"] is False


@pytest.mark.parametrize("scenario", ["matched", "no_match", "presentation_failure"])
def test_ui_faq_reply_and_inspector_preserve_outcome_without_resubmit(monkeypatch, faq_provider, scenario):
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
    ui.chat_input[0].set_value("Please answer this FAQ: " + question).run()
    assert not ui.exception
    data = recorded[0][1]
    assert data["route"] == "llm_assisted"
    assert data["status"] == {"matched": "completed", "no_match": "needs_clarification",
                              "presentation_failure": "partial_failure"}[scenario]
    assert "FAQ workflow stages" in [element.label for element in ui.expander]
    assistant = ui.chat_message[1]
    assert data["reply"] in [element.value for element in assistant.text]
    assert len(assistant.json) == 0
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
    ui.chat_input[0].set_value("Draft an email").run()
    assert ui.warning[0].value == "Execution: needs_clarification"
    assert "Who is the recipient?" in [element.value for element in ui.text]
    ui.chat_input[0].set_value("Alex").run()
    assert not ui.exception
    assert recorded[0][0]["session_id"] == recorded[1][0]["session_id"]
    messages = model.invoke.call_args_list[1].args[0]
    assert messages[-3].content == "Draft an email" and messages[-1].content == "Alex"
    other = AppTest.from_file(str(SCRIPT)).run()
    other.chat_input[0].set_value("Another email").run()
    assert recorded[2][0]["session_id"] != recorded[0][0]["session_id"]
    assert len(model.invoke.call_args_list[2].args[0]) == 2
    ui.selectbox[0].select(0).run()
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
    ui.chat_input[0].set_value("Analyze and then draft").run()
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
    client = TestClient(app)
    sent = []

    def send(request, **kwargs):
        result = client.post("/api/v1/chat", json=json.loads(request.data))
        sent.append(result.json())
        assert result.status_code == 503
        raise HTTPError("http://localhost", 503, "unavailable", {}, Response(result.json()))

    monkeypatch.setattr(ui_client, "urlopen", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("Just check the sentiment of this I am happy").run()
    assert not ui.exception
    data = sent[0]
    assert data["route"] == "llm_assisted" and data["status"] == "partial_failure"
    assert data["reason"] == "presentation_failed" and data["result"]["label"] == "positive"
    assert data["trace"][0]["status"] == "completed"
    assert data["workflow_trace"][-1]["status"] == "failed"
    assert ui.session_state["turns"][0]["execution"] == data
    assert data["result"] in [json.loads(element.value) for element in ui.json]
    assert data["reply"] in [element.value for element in ui.text]
    session_id = data["session_id"]
    saved = json.loads(sessions._sessions[session_id].history.messages[-1].content)
    assert saved["result"] == data["result"] and saved["reply"] == data["reply"]
    assert saved["workflow_trace"] == data["workflow_trace"]
    ui.run()
    assert not ui.exception and len(sent) == 1 and model.invoke.call_count == 2
    assert len(sessions._sessions[session_id].history.messages) == 2
    assert "private credentials" not in str(ui)


def test_ui_connection_failure_persists_without_retry_or_stale_inspector(monkeypatch):
    send = Mock(side_effect=ui_client.ChatClientError("Connection failed; outcome unknown."))
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("Hi").run()
    assert not ui.exception and ui.session_state["pending"] is False
    assert ui.session_state["turns"][0]["execution"] is None
    assert len(ui.error) == 2
    ui.run()
    assert send.call_count == 1


@pytest.mark.parametrize("message", [" \n", "x" * 10001])
def test_ui_invalid_message_never_submitted(monkeypatch, message):
    send = Mock()
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value(message).run()
    assert not ui.exception
    assert not ui.session_state["turns"]
    send.assert_not_called()


def test_ui_source_is_plain_text_not_executable_markup(monkeypatch):
    def send(url, session_id, message):
        data = execution(session_id)
        data["reply"] = '<script>private()</script> ![remote](https://example.com/image)'
        return data

    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("<b>input</b>").run()
    assert not ui.exception
    assert "<b>input</b>" in [element.value for element in ui.text]
    assert any("<script>" in element.value for element in ui.text)


def test_ui_keyword_workflow_and_inspector_match_backend_without_resubmit(monkeypatch, keyword_provider):
    model = keyword_provider("The server failed after the deployment", "Here are the keywords extracted from your text and their scores.")
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    assert not ui.exception
    ui.chat_input[0].set_value("Find keywords in this The server failed after the deployment").run()
    assert not ui.exception
    data = recorded[0][1]
    assert data["result"] and data["trace"][0]["tool"] == "extract_keywords"
    assert "Keyword workflow stages" in [element.label for element in ui.expander]
    assert [element.value for element in ui.caption].count("LLM stage") == 2
    assert "Local tool stage" in [element.value for element in ui.caption]
    assert data["route"] == "llm_assisted" and model.invoke.call_count == 2
    assert ui.session_state["turns"][0]["execution"] == data
    displayed_json = [json.loads(element.value) for element in ui.json]
    assert displayed_json.count(data["result"]) == 1  # Inspector only.
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
    assert ui.chat_input[0].proto.submit_mode == ui.chat_input[0].proto.SUBMIT_MODE_DISABLE
    ui.run()
    assert len(recorded) == 1
    assert model.invoke.call_count == 2
    assert ui.session_state["pending"] is False


def test_ui_keyword_presentation_failure_retains_phrases_stages_and_reply_without_retry(monkeypatch, keyword_provider):
    model = keyword_provider("The server failed after the deployment")
    extraction = AIMessage(content=json.dumps({"status": "ready", "source_text": "The server failed after the deployment", "reason": "explicit_source"}),
                           response_metadata={"finish_reason": "stop"})
    model.invoke.side_effect = [extraction, RuntimeError("private credentials")]
    client = TestClient(app)
    sent = []

    def send(request, **kwargs):
        result = client.post("/api/v1/chat", json=json.loads(request.data))
        sent.append(result.json())
        assert result.status_code == 503
        raise HTTPError("http://localhost", 503, "unavailable", {}, Response(result.json()))

    monkeypatch.setattr(ui_client, "urlopen", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("Find keywords in this The server failed after the deployment").run()
    assert not ui.exception
    data = sent[0]
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
    assert not ui.exception and len(sent) == 1 and model.invoke.call_count == 2
    assert len(sessions._sessions[session_id].history.messages) == 2
    assert "private credentials" not in str(ui)


def test_ui_keyword_empty_result_has_reply_without_empty_table(monkeypatch, keyword_provider):
    source = "!!!"
    model = keyword_provider(source, "No keyword candidates were found in the supplied text.")
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("keyword_extraction", 1, 0.71))
    recorded = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("Find keywords: !!!").run()
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

    def send(url, session_id, message):
        data = execution(session_id)
        data.update(predicted_intent="keyword_extraction", route="llm_assisted",
                    result=scores, reply="Here are the extracted keywords and their scores.")
        return data

    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = AppTest.from_file(str(SCRIPT)).run()
    ui.chat_input[0].set_value("Find keywords from supplied source").run()
    assert not ui.exception
    table = ui.dataframe[0]
    assert table.value.to_dict("records") == [{"Phrase": phrase, "Score": 0.0123456789}]
    assert "Phrase" not in json.loads(table.proto.columns)  # Default plain-text cells.
    assert not ui.get("imgs") and not ui.get("iframe")
