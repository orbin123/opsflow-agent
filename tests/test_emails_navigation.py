from dataclasses import asdict
from unittest.mock import Mock

import pytest

from app.chat import sessions
from app.ui import ui_client
from tests.test_chat_catalogue import BASE
from tests.test_email_catalogue import draft_step
from tests.test_workspace_navigation import workspace, open_chat, text


def save(key="one", turn_id="draft", steps=None, status="completed", demo=False):
    store = sessions._get_store()
    store.begin(key, "Original\nrequest <literal>", turn_id)
    execution = asdict(BASE)
    execution.update(trace=steps if steps is not None else [draft_step()], status=status)
    store.finish(turn_id, execution=execution, demo_policy=demo)


def test_emails_read_only_restart_refresh_return_and_source_chat(workspace):
    recorded, execute = workspace
    save("source")
    sessions.rename_chat("source", "Literal **source**")
    save("selected", "other", steps=[])
    sessions.close_chat_store()
    ui = open_chat("selected")
    draft = "Unsent composer\nSecond line"
    ui.text_area(key="composer").set_value(draft).run()
    ui.button(key="open_emails").click().run()
    assert not ui.exception and not ui.text_area and ui.query_params["chat"] == "selected"
    assert "First line\n<Second line>" in text(ui)
    assert "Original\nrequest <literal>" in text(ui) and "Chat: Literal **source**" in text(ui)
    ui.button(key="refresh_emails").click().run()
    ui.button(key="open_docs").click().run()
    ui.run()
    ui.button(key="return_to_chat").click().run()
    assert ui.text_area(key="composer").value == draft
    ui.button(key="open_emails").click().run()
    ui.run()
    ui.button(key="email_source_source_draft_0").click().run()
    assert ui.query_params["chat"] == "source" and ui.session_state["view"] == "chat"
    ui.button(key="chat_selected").click().run()
    assert ui.text_area(key="composer").value == draft
    assert not recorded
    execute.assert_not_called()


def test_compound_partial_and_contextual_demo_cards(workspace):
    save(steps=[], demo=True)
    save(turn_id="compound", steps=[draft_step(), draft_step("failed"), draft_step()], status="partial_failure")
    ui = open_chat()
    ui.button(key="open_emails").click().run()
    assert not ui.exception
    assert sum(element.value == "Intended recipient: Alex" for element in ui.text) == 2
    assert text(ui).count("Policy information below is fictional demo policy.") == 2
    assert text(ui).count("Source turn outcome: partial_failure") == 2


def test_rename_and_delete_are_reflected_on_refresh(workspace):
    save()
    ui = open_chat()
    ui.button(key="open_emails").click().run()
    sessions.rename_chat("one", "Renamed source")
    ui.button(key="refresh_emails").click().run()
    assert "Chat: Renamed source" in text(ui)
    sessions.delete_chat("one")
    ui.button(key="refresh_emails").click().run()
    assert not ui.exception and "Intended recipient: Alex" not in text(ui)
    assert any("No saved email drafts yet" in element.value for element in ui.info)


@pytest.mark.parametrize("read", ["list_chats", "get_chat"])
def test_read_failure_never_shows_partial_list_or_empty_state(workspace, monkeypatch, read):
    save("one")
    save("two", "second")
    ui = open_chat()
    original = getattr(ui_client, read)
    def fail(*args):
        if read == "get_chat" and args[1] != "one":
            return original(*args)
        raise ui_client.ChatClientError("Unavailable")
    monkeypatch.setattr(ui_client, read, Mock(side_effect=fail))
    ui.button(key="open_emails").click().run()
    assert not ui.exception and "Intended recipient: Alex" not in text(ui)
    assert any("Saved email drafts could not be loaded" in element.value for element in ui.error)
    assert not any("No saved email drafts yet" in element.value for element in ui.info)
    monkeypatch.setattr(ui_client, read, original)
    ui.button(key="refresh_emails").click().run()
    assert text(ui).count("Intended recipient: Alex") == 2
    workspace[1].assert_not_called()


def test_malformed_record_notice_and_empty_state(workspace):
    ui = open_chat()
    ui.button(key="open_emails").click().run()
    assert any("No saved email drafts yet" in element.value for element in ui.info)
    malformed = draft_step()
    malformed["result"] = {"email_draft": {"recipient": "Alex", "subject": "Subject", "body": ""},
                           "action_instructions": []}
    save(steps=[malformed])
    ui.button(key="refresh_emails").click().run()
    assert not ui.exception and ui.warning
    assert not any("No saved email drafts yet" in element.value for element in ui.info)


def test_source_deleted_after_listing_shows_existing_not_found_state(workspace):
    save()
    ui = open_chat()
    ui.button(key="open_emails").click().run()
    sessions.delete_chat("one")
    ui.button(key="email_source_one_draft_0").click().run()
    assert not ui.exception and ui.query_params["chat"] == "one"
    assert ui.error and not ui.chat_message
    assert ui.button(key="send_message").disabled
    workspace[1].assert_not_called()


@pytest.mark.parametrize("state", ["pending", "running", "unknown"])
def test_unconfirmed_work_blocks_emails(workspace, state):
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
    ui.button(key="open_emails").click().run()
    assert not ui.exception and ui.session_state["view"] == "chat"
    workspace[1].assert_not_called()
