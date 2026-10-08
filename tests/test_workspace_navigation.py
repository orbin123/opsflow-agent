from dataclasses import asdict, replace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from app import sessions, ui_client
from tests.test_chat_catalogue import BASE
from tests.test_streamlit_ui import SCRIPT, connect_api, send_message


@pytest.fixture
def workspace(monkeypatch):
    recorded = connect_api(monkeypatch)
    execute = Mock(side_effect=lambda message, **kwargs: replace(BASE, reply="Reply: " + message))
    monkeypatch.setattr(sessions, "execute_request", execute)
    return recorded, execute


def open_chat(key=None):
    ui = AppTest.from_file(str(SCRIPT))
    if key is not None:
        ui.query_params["chat"] = key
    ui.run()
    assert not ui.exception
    return ui


def text(ui):
    return "\n".join(element.value for element in ui.text)


def test_empty_start_does_not_create_and_new_chat_is_durable(workspace):
    recorded, execute = workspace
    ui = open_chat()
    assert sessions.list_chats() == [] and "chat" not in ui.query_params
    ui.run()
    assert sessions.list_chats() == []
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    assert ui.query_params["chat"] == key
    assert sessions.get_chat(key)["turns"] == []
    assert ui.text_area(key="composer").value == ""
    assert not recorded
    execute.assert_not_called()


def test_two_chats_restore_drafts_context_and_read_only_activity(workspace):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, "First chat")
    first = ui.session_state["session_id"]
    ui.text_area(key="composer").set_value("Unsent first draft").run()
    ui.button(key="new_chat").click().run()
    assert ui.text_area(key="composer").value == ""
    send_message(ui, "Second chat")
    second = ui.session_state["session_id"]
    assert second != first and len(execute.call_args_list[1].kwargs["history"]) == 0
    ui.text_area(key="composer").set_value("Unsent second draft").run()
    ui.button(key="chat_" + first).click().run()
    assert ui.text_area(key="composer").value == "Unsent first draft"
    assert "Reply: First chat" in text(ui) and "Second chat" not in text(ui)
    send_message(ui, "First follow-up")
    assert execute.call_args.kwargs["history"][0].content == "First chat"
    ui.run()
    assert len(recorded) == 3 and execute.call_count == 3
    ui.button(key="chat_" + second).click().run()
    assert ui.text_area(key="composer").value == "Unsent second draft"
    assert "First chat" not in text(ui)


def test_selected_url_refresh_restart_and_latest_start(workspace):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, "Older chat")
    older = ui.session_state["session_id"]
    ui.button(key="new_chat").click().run()
    send_message(ui, "Latest chat")
    latest = ui.session_state["session_id"]
    sessions.close_chat_store()
    sessions._sessions.clear()
    restored = open_chat(older)
    assert "Reply: Older chat" in text(restored) and "Latest chat" not in text(restored)
    outcome = sessions.get_chat(older)["turns"][0]["execution"]
    assert restored.session_state["turns"][0]["execution"] == {
        "session_id": older, "turn_id": recorded[0][0]["turn_id"], **outcome}
    default = open_chat()
    assert default.session_state["session_id"] == latest
    assert "Reply: Latest chat" in text(default)
    assert execute.call_count == 2 and len(recorded) == 2


@pytest.mark.parametrize("locator", ["missing", " ", "x" * 129, ["one", "two"]],
                         ids=["unknown", "blank", "long", "duplicate"])
def test_bad_locator_never_falls_back_or_submits(workspace, locator):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, "Saved source")
    ui.query_params["chat"] = locator
    ui.run()
    assert not ui.exception and ui.error
    assert not ui.chat_message and not ui.json
    assert ui.button(key="send_message").disabled
    assert len(recorded) == 1 and execute.call_count == 1


def test_read_failure_hides_old_chat_and_retry_only_reads(workspace, monkeypatch):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, "First chat")
    first = ui.session_state["session_id"]
    ui.button(key="new_chat").click().run()
    send_message(ui, "Second chat")
    original = ui_client.get_chat
    monkeypatch.setattr(ui_client, "get_chat", Mock(side_effect=ui_client.ChatClientError("Saved chat unavailable.")))
    ui.button(key="chat_" + first).click().run()
    assert not ui.chat_message and ui.button(key="send_message").disabled
    monkeypatch.setattr(ui_client, "get_chat", original)
    ui.button(key="recover_chat").click().run()
    assert "Reply: First chat" in text(ui) and "Second chat" not in text(ui)
    assert len(recorded) == 2 and execute.call_count == 2


def test_catalogue_failure_blocks_creation_without_empty_fallback(workspace, monkeypatch):
    monkeypatch.setattr(ui_client, "list_chats", Mock(side_effect=ui_client.ChatClientError("Chat list unavailable.")))
    create = Mock()
    monkeypatch.setattr(ui_client, "create_chat", create)
    ui = open_chat()
    assert ui.error and ui.button(key="new_chat").disabled and ui.button(key="send_message").disabled
    assert not ui.info or all("Start with" not in element.value for element in ui.info)
    create.assert_not_called()


def test_creation_failure_preserves_draft_without_submission(workspace, monkeypatch):
    recorded, execute = workspace
    monkeypatch.setattr(ui_client, "create_chat", Mock(side_effect=ui_client.ChatClientError("Creation unavailable.")))
    ui = open_chat()
    send_message(ui, "Keep this draft")
    assert ui.text_area(key="composer").value == "Keep this draft" and ui.error
    assert not recorded and sessions.list_chats() == []
    execute.assert_not_called()


def test_running_restoration_locks_navigation_and_interruption_allows_new_turn(workspace):
    recorded, execute = workspace
    sessions._get_store().begin("one", "Pending request", "pending")
    ui = open_chat("one")
    assert ui.button(key="new_chat").disabled and ui.button(key="chat_one").disabled
    assert ui.button(key="send_message").disabled and any("Running or unsaved" in error.value for error in ui.error)
    ui.query_params["chat"] = "other"
    ui.run()
    assert ui.session_state["session_id"] == "one" and ui.query_params["chat"] == "one"
    sessions.close_chat_store()
    ui.button(key="recover_chat").click().run()
    assert not ui.button(key="send_message").disabled
    assert any("interrupted" in error.value for error in ui.error)
    send_message(ui, "Explicit continuation")
    assert len(recorded) == 1 and execute.call_count == 1
    history = execute.call_args.kwargs["history"]
    assert history[0].content == "Pending request" and "interrupted" in history[1].content


def test_lost_reply_recovers_committed_outcome_without_repeat(workspace, monkeypatch):
    recorded, execute = workspace
    original = ui_client.submit_chat

    def lost(*args, **kwargs):
        original(*args, **kwargs)
        raise ui_client.ChatClientError("Reply lost. Completion unknown; no automatic retry.")

    monkeypatch.setattr(ui_client, "submit_chat", lost)
    ui = open_chat()
    send_message(ui, "Saved despite timeout")
    assert "Reply: Saved despite timeout" in text(ui)
    assert not ui.session_state["uncertain"] and not ui.button(key="send_message").disabled
    ui.run()
    assert len(recorded) == 1 and execute.call_count == 1


def test_unknown_missing_outcome_blocks_submission_until_read_resolves(workspace, monkeypatch):
    recorded, execute = workspace
    send = Mock(side_effect=ui_client.ChatClientError("Outcome unknown; no automatic retry."))
    monkeypatch.setattr(ui_client, "submit_chat", send)
    ui = open_chat()
    send_message(ui, "Unknown request")
    key = ui.session_state["session_id"]
    uncertain = ui.session_state["uncertain"][key]
    assert ui.button(key="send_message").disabled and not ui.button(key="new_chat").disabled
    ui.button(key="recover_chat").click().run()
    assert send.call_count == 1
    store = sessions._get_store()
    store.begin(key, uncertain["message"], uncertain["turn_id"])
    store.finish(uncertain["turn_id"], execution=asdict(BASE))
    ui.button(key="recover_chat").click().run()
    assert not ui.button(key="send_message").disabled and not ui.session_state["uncertain"]
    assert len(ui.chat_message) == 2 and send.call_count == 1
    execute.assert_not_called()


@pytest.mark.parametrize("phase", ["begin", "finish"])
def test_storage_failure_draft_and_running_recovery(workspace, monkeypatch, phase):
    from app.chat_store import ChatPersistenceError
    recorded, execute = workspace
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    store = sessions._get_store()
    original = getattr(store, phase)
    monkeypatch.setattr(store, phase, Mock(side_effect=ChatPersistenceError("Chat records unavailable.")))
    send_message(ui, "Storage check")
    assert not ui.exception
    if phase == "begin":
        assert execute.call_count == 0 and sessions.get_chat(key)["turns"] == []
        assert ui.text_area(key="composer").value == "Storage check"
        assert not ui.button(key="send_message").disabled
        assert any("No new turn was executed" in error.value for error in ui.error)
    else:
        assert execute.call_count == 1 and sessions.get_chat(key)["turns"][0]["state"] == "running"
        assert ui.button(key="new_chat").disabled and ui.button(key="send_message").disabled
        assert any("outcome was not saved" in error.value for error in ui.error)
        sessions.close_chat_store()
        ui.button(key="recover_chat").click().run()
        assert not ui.button(key="send_message").disabled and not ui.session_state["uncertain"]
        assert any("interrupted" in error.value for error in ui.error)
    monkeypatch.setattr(store, phase, original)
    assert len(recorded) == 1


def test_submission_renders_disabled_controls_before_http(workspace, monkeypatch):
    recorded, execute = workspace
    original = ui_client.submit_chat
    ui = open_chat()

    def inspect(*args, **kwargs):
        from streamlit import session_state
        assert session_state.pending and session_state.queued is None
        return original(*args, **kwargs)

    monkeypatch.setattr(ui_client, "submit_chat", inspect)
    send_message(ui, "One submission")
    assert not ui.exception and len(recorded) == 1 and execute.call_count == 1


def test_title_markup_is_literal_and_long_title_keeps_full_label(workspace):
    ui = open_chat()
    title = "![remote](https://example.com/image) **literal** " + "x" * 100
    send_message(ui, title)
    key = ui.session_state["session_id"]
    button = ui.button(key="chat_" + key)
    assert "\\[" in button.label and "\\*" in button.label
    assert button.label.endswith("…") and button.proto.wrap is False
    assert not ui.get("imgs") and not ui.get("iframe")
