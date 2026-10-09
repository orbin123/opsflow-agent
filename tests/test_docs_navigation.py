from pathlib import Path
from unittest.mock import Mock

import pytest

from app import sessions, ui_client
from tests.test_workspace_navigation import workspace, open_chat, text
from tests.test_streamlit_ui import send_message


def test_docs_returns_saved_chat_and_multiline_draft_without_execution(workspace):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, "Saved source")
    key = ui.session_state["session_id"]
    draft = "Unsent first line\nSecond line <literal>"
    ui.text_area(key="composer").set_value(draft).run()
    turns = sessions.get_chat(key)["turns"]
    ui.button(key="open_docs").click().run()
    assert not ui.exception and not ui.text_area and not ui.chat_message
    assert ui.query_params["chat"] == key
    assert "# Docs" in ui.markdown[-1].value
    ui.run()  # Hidden composer is cleaned up by Streamlit.
    ui.button(key="return_to_chat").click().run()
    assert not ui.exception
    assert ui.text_area(key="composer").value == draft
    assert "Reply: Saved source" in text(ui)
    assert sessions.get_chat(key)["turns"] == turns
    assert len(recorded) == execute.call_count == 1


def test_docs_empty_welcome_draft_and_available_pages(workspace):
    recorded, execute = workspace
    ui = open_chat()
    ui.text_area(key="composer").set_value("Welcome draft\nNext line").run()
    ui.button(key="open_docs").click().run()
    assert not ui.button(key="open_emails").disabled
    assert not ui.button(key="open_reminders").disabled
    ui.run()
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == "Welcome draft\nNext line"
    assert not ui.exception and not sessions.list_chats() and not recorded
    execute.assert_not_called()


def test_workspace_selection_from_docs_restores_each_draft(workspace):
    recorded, execute = workspace
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    first = ui.session_state["session_id"]
    ui.text_area(key="composer").set_value("First draft").run()
    ui.button(key="new_chat").click().run()
    second = ui.session_state["session_id"]
    ui.text_area(key="composer").set_value("Second draft").run()
    ui.button(key="open_docs").click().run()
    ui.run()
    ui.button(key="chat_" + second).click().run()
    assert ui.text_area(key="composer").value == "Second draft"
    ui.button(key="open_docs").click().run()
    ui.run()
    ui.button(key="chat_" + first).click().run()
    assert ui.text_area(key="composer").value == "First draft"
    assert not ui.exception and not recorded
    execute.assert_not_called()


@pytest.mark.parametrize("state", ["pending", "running", "unknown"])
def test_unconfirmed_work_prevents_docs_navigation(workspace, state):
    recorded, execute = workspace
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    if state == "pending":
        ui.session_state["pending"] = True
    elif state == "running":
        sessions._get_store().begin(key, "Pending request", "in-progress")
    else:
        ui.session_state["uncertain"] = {key: dict(session_id=key, turn_id="unknown",
            message="Pending request", execution=None, state="unknown", error="Unconfirmed")}
    ui.run()
    ui.button(key="open_docs").click().run()
    assert ui.session_state["view"] == "chat" and not ui.exception
    if state != "pending":
        assert ui.button(key="recover_chat")
    assert not recorded
    execute.assert_not_called()


def test_docs_is_readable_without_backend(workspace, monkeypatch):
    recorded, execute = workspace
    monkeypatch.setattr(ui_client, "list_chats", Mock(side_effect=ui_client.ChatClientError("Unavailable")))
    ui = open_chat()
    ui.button(key="open_docs").click().run()
    assert not ui.exception and "# Docs" in ui.markdown[-1].value
    ui.button(key="return_to_chat").click().run()
    assert ui.button(key="send_message").disabled
    assert not recorded
    execute.assert_not_called()


def test_running_turn_detected_in_docs_returns_to_recovery(workspace):
    ui = open_chat()
    ui.button(key="new_chat").click().run()
    key = ui.session_state["session_id"]
    ui.text_area(key="composer").set_value("Preserve me").run()
    ui.button(key="open_docs").click().run()
    ui.run()
    sessions._get_store().begin(key, "Started in another tab", "other-tab")
    ui.run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    assert ui.button(key="recover_chat")
    assert ui.text_area(key="composer").value == "Preserve me"


def test_missing_guide_is_safe_and_return_remains_available(workspace, monkeypatch):
    original = Path.read_text

    def read(path, *args, **kwargs):
        if path.name == "user-guide.md":
            raise OSError("private filesystem details")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    ui = open_chat()
    ui.button(key="open_docs").click().run()
    assert not ui.exception
    assert ui.error[0].value == "The guide is unavailable. Return to chat and try again later."
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer")
