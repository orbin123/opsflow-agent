import io
import json
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from streamlit.testing.v1 import AppTest

from app import sessions, ui_client
from tests.test_streamlit_ui import SCRIPT, execution, connect_api


def event(event_name, sequence, **data):
    return dict(version=1, session_id="one", turn_id="turn", sequence=sequence, event=event_name, **data)


def terminal(sequence=2, status="completed"):
    data = execution(status=status)
    data.pop("session_id")
    return event("final", sequence, execution=data, outcome="saved",
                 http_status=503 if status in {"error", "partial_failure"} else 200)


def frame(data, newline="\n"):
    return (f"id: {data['sequence']}{newline}event: {data['event']}{newline}"
            f"data: {json.dumps(data, ensure_ascii=False)}{newline}{newline}").encode()


class Stream(io.BytesIO):
    status = 200
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}


def submit(monkeypatch, frames, callback=None):
    send = Mock(return_value=Stream(frames))
    monkeypatch.setattr(ui_client, "urlopen", send)
    result = ui_client.submit_chat("http://localhost", "one", "Source\n☀", turn_id="turn",
                                   on_event=callback or Mock())
    assert send.call_count == 1
    request = send.call_args.args[0]
    assert request.full_url.endswith("/api/v1/chat/stream")
    assert json.loads(request.data)["message"] == "Source\n☀"
    return result


def test_incremental_progress_precedes_saved_final_and_preserves_failed_observations(monkeypatch):
    observed = []
    data = terminal(5, "partial_failure")
    data["execution"]["trace"] = [dict(tool="analyze_sentiment", arguments={"text": "☀"},
        status="completed", result={"label": "positive"}, reason=None, elapsed_ms=1.23456789)]
    frames = [event("turn", 1), event("classification", 2, predicted_intent="compound", confidence=.51),
              event("step_started", 3, name="analyze_sentiment", kind="tool", arguments={"text": "☀"}),
              event("step_finished", 4, step_id=3, status="completed", elapsed_ms=1.23456789,
                    result={"label": "positive"}), data]

    class Incremental(Stream):
        def __iter__(self):
            for number, item in enumerate(frames):
                # Each previous callback must have run before reading the next frame.
                assert len(observed) == number
                yield from io.BytesIO(frame(item, "\r\n"))

    monkeypatch.setattr(ui_client, "urlopen", Mock(return_value=Incremental(b"")))
    result = ui_client.submit_chat("http://localhost", "one", "Hi", turn_id="turn", on_event=observed.append)
    assert result["status"] == "partial_failure"
    assert result["trace"][0] == data["execution"]["trace"][0]
    assert observed[-1]["execution"] == result
    assert [item["event"] for item in observed] == [item["event"] for item in frames]


@pytest.mark.parametrize("change", [
    {"turn_id": "wrong"}, {"session_id": "wrong"}, {"sequence": 3}, {"version": 2},
    {"event": "private_debug"}, {"event": "classification", "confidence": "private log"},
    {"event": "step_finished", "step_id": 99, "status": "completed", "elapsed_ms": 1.0},
    {"execution": {"private": "credentials"}}, {"outcome": "unsaved"}, {"http_status": 503},
])
def test_invalid_events_stop_without_retry_or_raw_details(monkeypatch, change):
    data = {**terminal(), **change}
    send = Mock(return_value=Stream(frame(event("turn", 1)) + frame(data)))
    monkeypatch.setattr(ui_client, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError) as error:
        ui_client.submit_chat("http://localhost", "one", "Hi", turn_id="turn", on_event=Mock())
    assert "private" not in str(error.value) and "credentials" not in str(error.value)
    assert send.call_count == 1


@pytest.mark.parametrize("ending", [b"", b"data: not json\n\n", b"id: 2\ndata: {}\n\n", b"data: {}"])
def test_truncated_or_malformed_stream_never_returns_success(monkeypatch, ending):
    with pytest.raises(ui_client.ChatClientError, match="Check saved chat"):
        submit(monkeypatch, frame(event("turn", 1)) + ending)


@pytest.mark.parametrize("outcome", ["not_started", "unsaved", "saved", "unknown"])
def test_terminal_failure_keeps_outcome_without_exposing_backend_message(monkeypatch, outcome):
    failure = event("failure", 2, code="chat_persistence" if outcome in {"not_started", "unsaved"}
                    else "runtime_unavailable" if outcome == "saved" else "execution_unknown",
                    http_status=503, outcome=outcome, message="private provider logs")
    with pytest.raises(ui_client.ChatClientError) as error:
        submit(monkeypatch, frame(event("turn", 1)) + frame(failure))
    assert error.value.outcome == outcome and "private" not in str(error.value)


def test_connection_failure_no_retry(monkeypatch):
    send = Mock(side_effect=URLError("private credentials"))
    monkeypatch.setattr(ui_client, "urlopen", send)
    with pytest.raises(ui_client.ChatClientError, match="Check saved chat"):
        ui_client.submit_chat("http://localhost", "one", "Hi", turn_id="turn", on_event=Mock())
    assert send.call_count == 1


def test_heartbeat_and_replay_final_without_steps(monkeypatch):
    result = submit(monkeypatch, b": keep-alive\n\n" + frame(event("turn", 1)) + frame(terminal()))
    assert result["reply"] == "Draft only"


@pytest.mark.parametrize("state", ["finished", "running", "missing"])
def test_interrupted_subscriber_rerun_reads_saved_turn_without_submission(monkeypatch, state):
    recorded = connect_api(monkeypatch)
    store = sessions._get_store()
    if state != "missing":
        store.begin("one", "Hi", "turn")
    else:
        store.create_chat("one")
    if state == "finished":
        store.finish("turn", execution={k: v for k, v in execution().items() if k != "session_id"})
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params["chat"] = "one"
    ui.session_state["session_id"] = "one"
    ui.session_state["pending"] = True
    ui.session_state["queued"] = None
    ui.session_state["inflight"] = {"session_id": "one", "turn_id": "turn", "message": "Hi"}
    ui.run()
    assert not ui.exception and not recorded
    assert not ui.session_state["pending"]
    if state == "finished":
        assert not ui.session_state["uncertain"]
        assert "Draft only" in [item.value for item in ui.text]
        assert not ui.button(key="send_message").disabled
    else:
        assert ui.session_state["uncertain"]
        assert ui.button(key="send_message").disabled and ui.error
