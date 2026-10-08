from unittest.mock import Mock

import pytest

from app import sessions, ui_client
from tests.test_workspace_navigation import workspace, open_chat, text
from tests.test_streamlit_ui import send_message


def open_actions(ui, key, operation):
    ui.session_state['management'] = {**next(c for c in sessions.list_chats() if c['session_id'] == key),
                                      'operation': operation}
    ui.session_state['rename_title'] = ui.session_state['management']['title']
    ui.run()
    assert not ui.exception


def test_rename_ui_literal_title_and_refresh_preserve_history(workspace):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, 'Saved source')
    key = ui.session_state['session_id']
    before = sessions.get_chat(key)['turns']
    open_actions(ui, key, 'rename')
    ui.text_input(key='rename_title').set_value('Release **review** <today>').run()
    ui.button(key='save_chat_name').click().run()
    assert not ui.exception and ui.session_state['management'] is None
    assert sessions.get_chat(key)['title'] == 'Release **review** <today>'
    refreshed = open_chat(key)
    assert refreshed.button(key='chat_' + key)
    assert 'Reply: Saved source' in text(refreshed)
    assert sessions.get_chat(key)['turns'] == before
    assert len(recorded) == execute.call_count == 1


def test_delete_cancel_then_selected_deletion_restores_other_and_last_welcome(workspace):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, 'First chat')
    first = ui.session_state['session_id']
    ui.button(key='new_chat').click().run()
    send_message(ui, 'Second chat')
    second = ui.session_state['session_id']
    ui.text_area(key='composer').set_value('Unsent text').run()
    before = sessions.get_chat(second)
    open_actions(ui, second, 'delete')
    ui.button(key='cancel_delete').click().run()
    assert sessions.get_chat(second) == before
    open_actions(ui, second, 'delete')
    ui.button(key='confirm_delete_chat').click().run()
    assert not ui.exception and sessions.get_chat(second) is None
    assert ui.session_state['session_id'] == first and ui.query_params['chat'] == first
    assert second not in ui.session_state['drafts']
    assert 'Reply: First chat' in text(ui) and 'Reply: Second chat' not in text(ui)
    open_actions(ui, first, 'delete')
    ui.button(key='confirm_delete_chat').click().run()
    assert not ui.exception and not sessions.list_chats()
    assert ui.session_state['session_id'] is None and 'chat' not in ui.query_params
    assert not ui.chat_message and ui.info
    assert ui.text_area(key='composer').value == ''
    assert len(recorded) == execute.call_count == 2


@pytest.mark.parametrize('operation', ['rename', 'delete'])
def test_management_failure_keeps_chat_and_dialog(workspace, monkeypatch, operation):
    recorded, execute = workspace
    ui = open_chat()
    send_message(ui, 'Saved chat')
    key = ui.session_state['session_id']
    before = sessions.get_chat(key)
    change = Mock(side_effect=ui_client.ChatClientError('Saved chats are unavailable. No automatic retry.'))
    monkeypatch.setattr(ui_client, operation + '_chat', change)
    open_actions(ui, key, operation)
    ui.button(key='save_chat_name' if operation == 'rename' else 'confirm_delete_chat').click().run()
    assert not ui.exception and ui.error and ui.session_state['management']
    assert sessions.get_chat(key) == before
    assert ui.session_state['session_id'] == key and change.call_count == 1
    assert len(recorded) == execute.call_count == 1


def test_running_chat_does_not_open_management_dialog(workspace):
    _, execute = workspace
    sessions._get_store().begin('one', 'Running work', 'running-work')
    ui = open_chat('one')
    open_actions(ui, 'one', 'delete')
    assert ui.session_state['management'] is None
    assert not any(button.key == 'confirm_delete_chat' for button in ui.button)
    execute.assert_not_called()
