import io
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app import sessions, ui_client
from app.chat_store import ChatPersistenceError
from app.main import app
from app.runtime import ExecutionResult, RuntimeUnavailable


client = TestClient(app)
BASE = ExecutionResult("completed", "out_of_scope", 1, "agent", "intent_requires_agent",
                       None, [], 0, reply="Done")


def submit(session_id, turn_id="first", message="  Exact\nsource  "):
    return client.post("/api/v1/chat", json=dict(session_id=session_id, turn_id=turn_id, message=message))


def test_catalogue_roundtrip_and_read_only_restart(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, "execute_request", execute)
    assert client.get("/api/v1/chats").json() == []
    response = client.post("/api/v1/chats", json={})
    assert response.status_code == 201
    chat = response.json()
    key = chat["session_id"]
    assert chat["title"] == "New chat"
    assert client.get(f"/api/v1/chats/{key}").json() == {**chat, "turns": []}
    assert client.get("/api/v1/chats").json() == [chat]
    execute.assert_not_called()
    outcome = submit(key).json()
    loaded = client.get(f"/api/v1/chats/{key}").json()
    assert loaded["title"] == "Exact source"
    turn = loaded["turns"][0]
    assert turn["message"] == "  Exact\nsource  " and turn["sequence"] == 1
    assert turn["state"] == "finished" and turn["finished_at"]
    assert turn["execution"] == {k: v for k, v in outcome.items() if k not in {"session_id", "turn_id"}}
    sessions.close_chat_store()
    sessions._sessions.clear()
    assert client.get(f"/api/v1/chats/{key}").json() == loaded
    assert submit(key).json() == outcome
    assert execute.call_count == 1
    assert submit(key, message="Changed").status_code == 409
    assert submit("other").status_code == 409
    assert execute.call_count == 1
    assert client.get("/api/v1/chats/other").status_code == 404


def test_order_and_unknown_reads_never_create(monkeypatch):
    monkeypatch.setattr(sessions, "execute_request", Mock(return_value=BASE))
    first = client.post("/api/v1/chats", json={}).json()["session_id"]
    second = client.post("/api/v1/chats", json={}).json()["session_id"]
    submit(first)
    assert [c["session_id"] for c in client.get("/api/v1/chats").json()] == [first, second]
    assert client.get("/api/v1/chats/missing").status_code == 404
    assert len(client.get("/api/v1/chats").json()) == 2
    with sessions._get_store()._connection(write=True) as connection:
        connection.execute("UPDATE chats SET updated_at='same'")
    assert [c["session_id"] for c in client.get("/api/v1/chats").json()] == sorted([first, second])


def test_running_and_interrupted_reads_no_reexecution(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, "execute_request", execute)
    sessions._get_store().begin("one", "Pending", "pending")
    assert client.get("/api/v1/chats/one").json()["turns"][0]["state"] == "running"
    conflict = submit("one", "pending", "Pending")
    assert conflict.status_code == 409 and conflict.json()["detail"]["state"] == "running"
    sessions.close_chat_store()
    turn = client.get("/api/v1/chats/one").json()["turns"][0]
    assert turn["state"] == "interrupted" and turn["execution"] is None
    assert turn["finished_at"] is None and turn["failure_reason"] == "interrupted"
    conflict = submit("one", "pending", "Pending")
    assert conflict.status_code == 409 and conflict.json()["detail"]["state"] == "interrupted"
    execute.assert_not_called()


@pytest.mark.parametrize("status", ["needs_clarification", "partial_failure", "error"])
def test_retained_outcomes_and_replay_http_status(monkeypatch, status):
    from dataclasses import replace
    execute = Mock(return_value=replace(BASE, status=status))
    monkeypatch.setattr(sessions, "execute_request", execute)
    first = submit("one")
    assert first.status_code == (200 if status == "needs_clarification" else 503)
    assert submit("one").json() == first.json()
    assert client.get("/api/v1/chats/one").json()["turns"][0]["execution"]["status"] == status
    assert execute.call_count == 1


def test_runtime_failure_retained_without_invented_execution(monkeypatch):
    monkeypatch.setattr(sessions, "execute_request", Mock(side_effect=RuntimeUnavailable("Classifier unavailable")))
    assert submit("one").status_code == 503
    turn = client.get("/api/v1/chats/one").json()["turns"][0]
    assert turn["execution"] is None and turn["failure_reply"] == "Classifier unavailable"
    assert turn["state"] == "finished"


@pytest.mark.parametrize("body", [{"title": "Custom"}, [], None])
def test_invalid_creation(body):
    assert client.post("/api/v1/chats", json=body).status_code == 422
    assert client.get("/api/v1/chats").json() == []


@pytest.mark.parametrize("turn_id", [" ", "x" * 129, 12])
def test_invalid_turn_ids_prevent_execution(monkeypatch, turn_id):
    execute = Mock()
    monkeypatch.setattr(sessions, "execute_request", execute)
    assert submit("one", turn_id).status_code == 422
    execute.assert_not_called()
    assert client.get("/api/v1/chats").json() == []


def test_legacy_posts_each_get_new_identity(monkeypatch):
    execute = Mock(return_value=BASE)
    monkeypatch.setattr(sessions, "execute_request", execute)
    body = dict(session_id="legacy", message="Same")
    one = client.post("/api/v1/chat", json=body).json()
    two = client.post("/api/v1/chat", json=body).json()
    assert one["turn_id"] != two["turn_id"] and execute.call_count == 2


def test_sanitized_storage_failure_and_corrupt_load(monkeypatch):
    sessions._get_store().begin("one", "Pending", "pending")
    with sessions._get_store()._connection(write=True) as connection:
        connection.execute("UPDATE chat_turns SET execution_json='{}', state='finished'")
    response = client.get("/api/v1/chats/one")
    assert response.status_code == 503 and response.json()["detail"]["code"] == "chat_persistence"
    sessions.close_chat_store()
    monkeypatch.setenv("OPSFLOW_CHATS_DB", ":memory:")
    for method, path in [("GET", "/api/v1/chats"), ("GET", "/api/v1/chats/one"), ("POST", "/api/v1/chats")]:
        response = client.request(method, path, **({"json": {}} if method == "POST" else {}))
        assert response.status_code == 503 and ":memory:" not in response.text


def test_client_catalogue_roundtrip_and_turn_identity(monkeypatch):
    monkeypatch.setattr(sessions, "execute_request", Mock(return_value=BASE))

    def send(request, timeout):
        response = client.request(request.method, request.full_url,
                                  content=request.data, headers=dict(request.header_items()))
        stream = io.BytesIO(response.content)
        stream.status = response.status_code
        return stream

    monkeypatch.setattr(ui_client, "urlopen", send)
    chat = ui_client.create_chat("http://testserver")
    assert ui_client.list_chats("http://testserver") == [chat]
    outcome = ui_client.submit_chat("http://testserver", chat["session_id"], "Hello", turn_id="client-turn")
    assert outcome["turn_id"] == "client-turn"
    assert ui_client.get_chat("http://testserver", chat["session_id"])["turns"][0]["turn_id"] == "client-turn"
    with pytest.raises(ui_client.ChatClientError, match="not found"):
        ui_client.get_chat("http://testserver", "missing")
    # Legacy caller-owned IDs need round-trip URL escaping as well as UUID support.
    ui_client.submit_chat("http://testserver", "space / unicode 雨?", "Hello", turn_id="legacy-key")
    assert ui_client.get_chat("http://testserver", "space / unicode 雨?")["session_id"] == "space / unicode 雨?"


def test_workflow_retrieval_preserves_exact_activity(sentiment_provider):
    model = sentiment_provider("I am happy", "Positive result.")
    body = dict(session_id="workflow", message="Just check the sentiment of this I am happy", turn_id="workflow-turn")
    outcome = client.post("/api/v1/chat", json=body).json()
    saved = client.get("/api/v1/chats/workflow").json()["turns"][0]["execution"]
    for field in ["trace", "workflow_trace", "result", "elapsed_ms", "reply"]:
        assert saved[field] == outcome[field]
    assert model.invoke.call_count == 2


def test_catalogue_fresh_process_recovery_without_execution(monkeypatch):
    from tests.test_durable_chats import child
    sessions._get_store().begin("one", "Pending", "pending")
    path = sessions._get_store().path
    sessions.close_chat_store()
    result = child('''
import json
from app import sessions
def forbidden(*args, **kwargs):
    raise AssertionError("Read executed work")
sessions.execute_request = forbidden
print(json.dumps({"list": sessions.list_chats(), "chat": sessions.get_chat("one")}))
sessions.close_chat_store()
''', path)
    assert result.returncode == 0, result.stderr
    saved = json.loads(result.stdout)
    assert saved["list"][0]["session_id"] == "one"
    assert saved["chat"]["turns"][0]["state"] == "interrupted"


@pytest.mark.parametrize("payload,status", [({"detail": "private path"}, 503), ({}, 200)])
def test_client_safe_read_failure(monkeypatch, payload, status):
    stream = io.BytesIO(json.dumps(payload).encode())
    stream.status = status
    monkeypatch.setattr(ui_client, "urlopen", Mock(return_value=stream))
    with pytest.raises(ui_client.ChatClientError) as error:
        ui_client.get_chat("http://localhost", "one")
    assert "private" not in str(error.value)
