from unittest.mock import Mock

import pytest

from app import ui_client
from tests.test_reminder_catalogue import database, seed
from tests.test_workspace_navigation import workspace, open_chat, text
from tests.test_emails_navigation import save


def test_page_read_refresh_return_preserves_draft_without_execution(workspace, database):
    save(steps=[])
    seed(database, "accepted")
    seed(database, "unknown", "two", "America/New_York")
    before = database.read_bytes()
    ui = open_chat("one")
    ui.text_area(key="composer").set_value("Unsent\nSecond line").run()
    ui.button(key="open_reminders").click().run()
    assert not ui.exception and not ui.text_area
    assert "SMTP accepted — inbox delivery unconfirmed" in text(ui)
    assert "Unknown — no automatic retry" in text(ui)
    assert "01 Nov 2026 · 09:00:00 -0500 · America/New_York" in text(ui)
    assert "01 Nov 2026 · 09:00:00 +0530 · Asia/Kolkata" in text(ui)
    assert "Review **literal**\nSecond line" in text(ui)
    assert not any(button.label == "Open chat" for button in ui.button)
    ui.button(key="refresh_reminders").click().run()
    ui.button(key="open_docs").click().run()
    ui.button(key="open_reminders").click().run()
    ui.button(key="return_to_chat").click().run()
    assert not ui.exception and ui.query_params["chat"] == "one"
    assert ui.text_area(key="composer").value == "Unsent\nSecond line"
    assert database.read_bytes() == before and not workspace[0]
    workspace[1].assert_not_called()


def test_empty_failure_and_refresh_recovery(workspace, database, monkeypatch):
    ui = open_chat()
    ui.button(key="open_reminders").click().run()
    assert any("No stored reminders yet" in element.value for element in ui.info)
    original = ui_client.list_reminders
    monkeypatch.setattr(ui_client, "list_reminders", Mock(side_effect=ui_client.ChatClientError("private")))
    ui.button(key="refresh_reminders").click().run()
    assert not ui.exception and ui.error and not ui.info
    monkeypatch.setattr(ui_client, "list_reminders", original)
    seed(database, "submitting")
    ui.button(key="refresh_reminders").click().run()
    assert "Submitting — outcome pending" in text(ui)
    assert not ui.exception and not ui.error
    workspace[1].assert_not_called()


@pytest.mark.parametrize("state", ["pending", "running", "unknown"])
def test_work_locks_reminders_page(workspace, database, state):
    from app import sessions
    save(steps=[])
    ui = open_chat()
    if state == "running":
        sessions._get_store().begin("one", "Running", "running")
    elif state == "pending":
        ui.session_state["pending"] = True
    else:
        ui.session_state["uncertain"] = {"one": dict(session_id="one", turn_id="unknown",
            message="Pending", execution=None, state="unknown", error="Unconfirmed")}
    ui.run()
    ui.button(key="open_reminders").click().run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    workspace[1].assert_not_called()
