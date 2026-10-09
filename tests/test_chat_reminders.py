"""Real SQLite scheduling behind scripted agent calls; no provider or SMTP."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import Mock

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest

from app import agent, chat_reminders, runtime, sessions
from app.chat_store import ChatPersistenceError, ChatTurnConflict
from app.main import app
from app.tools import reminders
from app.reminder_catalogue import list_saved_reminders


NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)
DEMO = "Remind me tomorrow at 10 am in Asia/Kolkata to review the deployment report."
ARGS = {"task": "review the deployment report", "date": "tomorrow", "time": "10 am",
        "timezone": "Asia/Kolkata"}


def call(args=None, ident="one"):
    return AIMessage(content="", tool_calls=[{"name": "schedule_reminder", "id": ident,
        "args": ARGS if args is None else args}], response_metadata={"finish_reason": "tool_calls"})


def final(status="completed", reply="The email was delivered."):
    return AIMessage(content=json.dumps({"status": status, "reply": reply}),
                     response_metadata={"finish_reason": "stop"})


def model(monkeypatch, responses):
    fake = Mock()
    fake.invoke.side_effect = responses
    monkeypatch.setattr(agent, "_create_model", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("OPSFLOW_REMINDERS_DB", str(tmp_path / "reminders.sqlite3"))
    monkeypatch.setenv("OPSFLOW_TIMEZONE", "Asia/Kolkata")
    monkeypatch.setattr(agent, "_create_model", lambda: pytest.fail("Unexpected provider"))
    monkeypatch.setattr(runtime, "classify_request", lambda message: ("reminder_creation", 1, .71))
    real_schedule = reminders.schedule_reminder
    monkeypatch.setattr(chat_reminders, "schedule_reminder",
                        lambda *args, **kwargs: real_schedule(*args, now=NOW, **kwargs))
    real_context = chat_reminders.reminder_turn
    monkeypatch.setattr(sessions, "reminder_turn", lambda ident: real_context(ident, now=NOW))


def test_demo_routing_exact_saved_result_and_truthful_acknowledgement(monkeypatch):
    from tests.test_docs_examples import PROMPTS
    assert PROMPTS[5] == DEMO
    fake = model(monkeypatch, [call(), final()])
    result = sessions.execute_session_request("one", DEMO, turn_id="demo")
    assert result.route == "agent" and result.predicted_intent == "reminder_creation"
    assert result.status == "completed"
    record = result.trace[0].result
    assert record["task"] == ARGS["task"]
    assert record["due_at"] == "2026-10-10T04:30:00+00:00"
    assert record["local_due"] == "2026-10-10T10:00:00+05:30"
    assert "creation_key" not in record
    assert "Reminder scheduled" in result.reply and "The email was delivered" not in result.reply
    assert "SMTP acceptance does not confirm inbox arrival" in result.reply
    assert list_saved_reminders()[0].state == "pending"
    assert json.loads(fake.invoke.call_args_list[1].args[0][-1].content) == record
    assert sessions.get_chat("one")["turns"][0]["execution"] == asdict(result)


@pytest.mark.parametrize("confidence", [.01, 1])
def test_reminders_always_use_agent(monkeypatch, confidence):
    monkeypatch.setattr(runtime, "classify_request", lambda _: ("reminder_creation", confidence, .71))
    model(monkeypatch, [final("needs_clarification", "What time?")])
    assert sessions.execute_session_request("one", "Remind me tomorrow").route == "agent"
    assert list_saved_reminders() == []


@pytest.mark.parametrize("args,message", [
    ({**ARGS, "time": None}, "Remind me tomorrow to review the deployment report in Asia/Kolkata"),
    ({**ARGS, "date": None}, "Remind me at 10 am in Asia/Kolkata to review the deployment report"),
    ({**ARGS, "task": None}, "Remind me tomorrow at 10 am in Asia/Kolkata"),
    ({**ARGS, "time": "10"}, DEMO.replace("10 am", "10")),
    ({**ARGS, "date": "10/11/2026"}, DEMO.replace("tomorrow", "10/11/2026")),
    ({**ARGS, "date": "next Friday"}, DEMO.replace("tomorrow", "next Friday")),
    ({**ARGS, "date": "2026-10-08"}, DEMO.replace("tomorrow", "2026-10-08")),
    ({**ARGS, "timezone": "Wrong/Zone"}, DEMO.replace("Asia/Kolkata", "Wrong/Zone")),
    ({**ARGS, "time": "11 am"}, DEMO),
    ({**ARGS, "time": "10:00"}, DEMO),
    ({**ARGS, "timezone": None}, DEMO),
    ({**ARGS, "timezone": None}, DEMO.replace("Asia/Kolkata", "IST")),
    (ARGS, DEMO.replace("10 am", "10 am or 11 am")),
    (ARGS, DEMO.replace("tomorrow", "every day starting tomorrow")),
    ({**ARGS, "utc_offset": "+05:30"}, DEMO),
    (ARGS, "Analyze this: review the deployment report tomorrow at 10 am in Asia/Kolkata"),
    (ARGS, 'Analyze this: "' + DEMO + '"'),
    (ARGS, DEMO.replace("review the deployment report", "Review the deployment report")),
])
def test_unsafe_or_ambiguous_arguments_clarify_without_writes(monkeypatch, args, message):
    model(monkeypatch, [call(args)])
    result = sessions.execute_session_request("one", message)
    assert result.status == "needs_clarification"
    assert result.trace[0].reason == "reminder_clarification"
    assert list_saved_reminders() == []


def test_clarification_followup_restores_literal_details(monkeypatch):
    model(monkeypatch, [call({**ARGS, "time": None})])
    first = sessions.execute_session_request("one", DEMO.replace(" at 10 am", ""))
    assert first.status == "needs_clarification" and list_saved_reminders() == []
    sessions.close_chat_store()
    model(monkeypatch, [call(), final()])
    second = sessions.execute_session_request("one", "10 am")
    assert second.status == "completed" and len(list_saved_reminders()) == 1


def test_context_is_not_available_across_chats_or_after_success(monkeypatch):
    model(monkeypatch, [call(), final()])
    sessions.execute_session_request("one", DEMO)
    for chat in ("one", "other"):
        model(monkeypatch, [call()])
        result = sessions.execute_session_request(chat, "10 am")
        assert result.status == "needs_clarification"
    assert len(list_saved_reminders()) == 1


def test_alternative_time_clarifies_then_accepts_selected_choice(monkeypatch):
    model(monkeypatch, [call()])
    assert sessions.execute_session_request("one", DEMO.replace("10 am", "10 am or 11 am")).status == "needs_clarification"
    assert list_saved_reminders() == []
    model(monkeypatch, [call(), final()])
    assert sessions.execute_session_request("one", "10 am").status == "completed"
    assert len(list_saved_reminders()) == 1


@pytest.mark.parametrize("instant,expected", [
    (datetime(2026, 10, 9, 18, 29, tzinfo=UTC), "2026-10-10T10:00:00+05:30"),
    (datetime(2026, 10, 9, 18, 31, tzinfo=UTC), "2026-10-11T10:00:00+05:30"),
])
def test_relative_date_uses_request_zone_at_midnight(instant, expected):
    with chat_reminders.reminder_turn("boundary", now=instant):
        result = chat_reminders.schedule_chat_reminder(sources=[DEMO], **ARGS)
    assert result.local_due == expected


@pytest.mark.parametrize("phrase", ["2026-10-10", "10 October 2026", "October 10, 2026"])
def test_explicit_calendar_date_and_default_zone(phrase):
    args = {**ARGS, "date": phrase, "timezone": None, "time": "22:00"}
    source = f"Remind me on {phrase} at 22:00 to review the deployment report"
    with chat_reminders.reminder_turn("calendar", now=NOW):
        result = chat_reminders.schedule_chat_reminder(sources=[source], **args)
    assert result.local_due == "2026-10-10T22:00:00+05:30"


@pytest.mark.parametrize("date,time,offset,expected", [
    ("2027-03-14", "2:30 am", None, None),
    ("2026-11-01", "1:30 am", None, None),
    ("2026-11-01", "1:30 am", "-04:00", "2026-11-01T05:30:00+00:00"),
    ("2026-11-01", "1:30 am", "-05:00", "2026-11-01T06:30:00+00:00"),
    ("2026-11-01", "1:30 am", "-06:00", None),
])
def test_dst_requires_real_confirmed_offset(date, time, offset, expected):
    args = {**ARGS, "date": date, "time": time, "timezone": "America/New_York", "utc_offset": offset}
    source = f"Remind me on {date} at {time} in America/New_York {offset or ''} to review the deployment report"
    with chat_reminders.reminder_turn("dst", now=NOW):
        if expected is None:
            with pytest.raises(chat_reminders.ReminderClarification):
                chat_reminders.schedule_chat_reminder(sources=[source], **args)
            assert list_saved_reminders() == []
        else:
            assert chat_reminders.schedule_chat_reminder(sources=[source], **args).due_at == expected


def test_second_model_call_cannot_create_another_reminder(monkeypatch):
    model(monkeypatch, [call(), call({**ARGS, "task": "another task"}, ident="two")])
    result = sessions.execute_session_request("one", DEMO)
    assert result.status == "partial_failure" and result.agent_reason == "reminder_already_created"
    assert len(result.trace) == len(list_saved_reminders()) == 1
    assert "Reminder scheduled" in result.reply


def test_same_operation_key_conflicts_and_concurrent_calls_deduplicate():
    def create():
        with chat_reminders.reminder_turn("concurrent", now=NOW):
            return chat_reminders.schedule_chat_reminder(sources=[DEMO], **ARGS)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda _: create(), range(2)))
    assert records[0].reminder_id == records[1].reminder_id
    with chat_reminders.reminder_turn("concurrent", now=NOW):
        with pytest.raises(chat_reminders.ReminderClarification):
            chat_reminders.schedule_chat_reminder(sources=[DEMO.replace("10 am", "11 am")],
                                                 **{**ARGS, "time": "11 am"})
    assert len(list_saved_reminders()) == 1


def test_http_replay_restart_concurrency_and_reads_never_repeat_work(monkeypatch):
    fake = model(monkeypatch, [call(), final()])
    client = TestClient(app)
    body = {"session_id": "one", "message": DEMO, "turn_id": "same"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post("/api/v1/chat", json=body), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert results[0].json() == results[1].json()
    sessions.close_chat_store()
    assert client.post("/api/v1/chat", json=body).json() == results[0].json()
    assert client.get("/api/v1/chats/one").status_code == 200
    assert client.get("/api/v1/reminders").json()[0]["state"] == "pending"
    assert fake.invoke.call_count == 2 and len(list_saved_reminders()) == 1


def test_model_failure_after_schedule_keeps_ack_and_record(monkeypatch):
    model(monkeypatch, [call(), RuntimeError("private provider details")])
    result = sessions.execute_session_request("one", DEMO)
    assert result.status == "partial_failure" and result.trace[0].status == "completed"
    assert "Reminder scheduled" in result.reply and "private" not in result.reply
    assert len(list_saved_reminders()) == 1


def test_reminder_commit_failure_never_reports_success(monkeypatch):
    monkeypatch.setattr(chat_reminders, "schedule_reminder", Mock(side_effect=reminders.ReminderPersistenceError("private")))
    model(monkeypatch, [call()])
    result = sessions.execute_session_request("one", DEMO)
    assert result.status == "error" and result.agent_reason == "reminder_persistence"
    assert "scheduled" not in result.reply and "private" not in result.reply
    assert list_saved_reminders() == []


def test_unsaved_chat_after_schedule_never_reexecutes(monkeypatch):
    fake = model(monkeypatch, [call(), final()])
    store = sessions._get_store()
    monkeypatch.setattr(store, "finish", Mock(side_effect=ChatPersistenceError("unavailable")))
    with pytest.raises(ChatPersistenceError, match="outcome was not saved"):
        sessions.execute_session_request("one", DEMO, turn_id="unsaved")
    assert len(list_saved_reminders()) == 1
    with pytest.raises(ChatTurnConflict):
        sessions.execute_session_request("one", DEMO, turn_id="unsaved")
    sessions.close_chat_store()
    with pytest.raises(ChatTurnConflict):
        sessions.execute_session_request("one", DEMO, turn_id="unsaved")
    assert fake.invoke.call_count == 2 and len(list_saved_reminders()) == 1


def test_creation_reuse_preserves_actual_worker_state():
    with chat_reminders.reminder_turn("accepted", now=NOW):
        first = chat_reminders.schedule_chat_reminder(sources=[DEMO], **ARGS)
    with sqlite3.connect(reminders._database_path(None)) as connection:
        connection.execute("UPDATE reminders SET state='accepted'")
    with chat_reminders.reminder_turn("accepted", now=NOW):
        again = chat_reminders.schedule_chat_reminder(sources=[DEMO], **ARGS)
    assert again == first
    assert list_saved_reminders()[0].state == "accepted"
    assert "awaiting" not in chat_reminders.scheduling_reply(again.model_dump())


def test_standalone_agent_has_no_durable_creation_authority(monkeypatch):
    model(monkeypatch, [call()])
    assert agent.run_agent(DEMO).status == "needs_clarification"
    assert list_saved_reminders() == []


def test_model_cannot_claim_creation_without_a_successful_tool(monkeypatch):
    model(monkeypatch, [final()])
    result = sessions.execute_session_request("one", DEMO)
    assert result.status == "needs_clarification" and "No new reminder was created" in result.reply
    assert "delivered" not in result.reply
    assert list_saved_reminders() == []


@pytest.mark.parametrize("kind,status,http_status", [
    ("success", "completed", 200),
    ("clarification", "needs_clarification", 200),
    ("later_failure", "partial_failure", 503),
])
def test_stream_events_and_client_validation_preserve_scheduling(monkeypatch, kind, status, http_status):
    from io import BytesIO
    from app import ui_client
    args = {**ARGS, "time": None} if kind == "clarification" else ARGS
    model(monkeypatch, [call(args)] + ([] if kind == "clarification" else
                                     [RuntimeError("private") if kind == "later_failure" else final()]))
    body = {"session_id": "stream", "turn_id": "stream-turn", "message": DEMO}
    with TestClient(app) as client:
        response = client.post("/api/v1/chat/stream", json=body)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["http_status"] == http_status
    assert events[-1]["execution"]["status"] == status
    tool = next(item for item in events if item.get("tool") == "schedule_reminder")
    assert tool["result"] == events[-1]["execution"]["trace"][0]["result"]
    stream = BytesIO(response.content)
    stream.status = 200
    stream.headers = {"Content-Type": "text/event-stream"}
    monkeypatch.setattr(ui_client, "urlopen", Mock(return_value=stream))
    result = ui_client.submit_chat("http://localhost", "stream", DEMO, turn_id="stream-turn", on_event=lambda _: None)
    assert result["status"] == status
    assert len(list_saved_reminders()) == (0 if kind == "clarification" else 1)


def test_chat_record_runs_through_existing_worker_with_controlled_transport(monkeypatch):
    from app import reminder_worker
    from app.tools.email_notifications import NotificationResult
    model(monkeypatch, [call(), final()])
    result = sessions.execute_session_request("worker", DEMO)
    record = result.trace[0].result
    sender = Mock(side_effect=lambda reminder, attempt_id, **kwargs: NotificationResult(
        status="accepted", reason=None, message_id=f"<{attempt_id}@opsflow.local>"))
    monkeypatch.setattr(reminder_worker, "send_reminder_notification", sender)
    with reminder_worker.ReminderWorker(clock=lambda: NOW) as worker:
        assert worker.run_once() == []
        sender.assert_not_called()
        worker.clock = lambda: datetime.fromisoformat(record["due_at"])
        assert worker.run_once()[0]["state"] == "accepted"
        assert worker.run_once() == []
    assert sender.call_count == 1
    assert sender.call_args.args[0].task == ARGS["task"]
    assert list_saved_reminders()[0].state == "accepted"


@pytest.mark.parametrize("extra", [{"creation_key": "model-key"}, {"db_path": "bad"}, {"task": 42}])
def test_model_cannot_supply_identity_storage_or_wrong_types(monkeypatch, extra):
    model(monkeypatch, [call({**ARGS, **extra})])
    result = sessions.execute_session_request("one", DEMO)
    assert result.status == "error" and result.agent_reason == "invalid_tool_arguments"
    assert list_saved_reminders() == []


def test_saved_reminder_clarification_renders_no_result_without_json_error(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from tests.test_streamlit_ui import SCRIPT, connect_api
    model(monkeypatch, [call({**ARGS, "time": None})])
    sessions.execute_session_request("ui", DEMO, turn_id="missing-time")
    requests = connect_api(monkeypatch)
    ui = AppTest.from_file(str(SCRIPT))
    ui.query_params["chat"] = "ui"
    for _ in range(2):
        ui.run()
        assert not ui.exception
        activity = ui.get_by_key("details_missing-time")
        assert "No reminder was created by this call." in [item.value for item in activity.text]
        assert all(json.loads(item.value) is not None for item in activity.json)
        assert "What time should I use for the reminder?" in [item.value for item in ui.chat_message[1].text]
    assert list_saved_reminders() == [] and not requests
