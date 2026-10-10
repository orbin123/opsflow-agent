"""Validated one-shot SSE consumption for the local console; never reconnects."""

import json
from dataclasses import asdict
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.ui import ui_client
from app.core.agent import AgentTrace
from app.api.chat import ChatRequest, ChatResponse


class ProgressEvent(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)
    version: Literal[1]
    session_id: str
    turn_id: str
    sequence: int = Field(ge=1)
    event: Literal["turn", "classification", "routing", "step_started", "step_finished", "final", "failure"]
    predicted_intent: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    route: Literal["direct", "llm_assisted", "agent"] | None = None
    reason: str | None = None
    name: str | None = None
    kind: Literal["workflow", "model", "tool"] | None = None
    arguments: dict | None = None
    result: dict | list | None = None
    step_id: int | None = Field(default=None, ge=1)
    status: Literal["completed", "failed"] | None = None
    elapsed_ms: float | None = Field(default=None, ge=0)
    http_status: Literal[200, 409, 503] | None = None
    outcome: Literal["saved", "not_started", "unsaved", "unknown"] | None = None
    code: Literal["chat_persistence", "chat_turn_conflict", "runtime_unavailable", "execution_unknown"] | None = None
    execution: dict | None = None


def submit_stream(base_url, session_id, message, turn_id, on_event):
    if turn_id is None:
        raise ui_client.ChatClientError("A turn ID is required before streaming. No turn was submitted.", outcome="not_started")
    body = ChatRequest(session_id=session_id, message=message, turn_id=turn_id)
    request = Request(base_url.rstrip("/") + "/api/v1/chat/stream",
                      data=body.model_dump_json().encode("utf-8"),
                      headers={"Content-Type": "application/json", "Accept": "text/event-stream"}, method="POST")
    previous = 0
    steps = {}
    try:
        with ui_client.urlopen(request, timeout=210) as response:
            if response.status != 200 or not response.headers.get("Content-Type", "").startswith("text/event-stream"):
                raise ValueError("Invalid stream transport")
            frame = {}
            for raw in response:
                line = raw.decode("utf-8").rstrip("\r\n")
                if line.startswith(":"):
                    continue
                if line:
                    field, _, value = line.partition(":")
                    if field in {"id", "event", "data"}:
                        if field in frame:
                            raise ValueError("Duplicate SSE field")
                        frame[field] = value.lstrip(" ")
                    continue
                if not frame:
                    continue
                raw_event = json.loads(frame["data"])
                event = ProgressEvent.model_validate(raw_event)
                if (event.session_id != session_id or event.turn_id != turn_id
                        or event.sequence != previous + 1 or frame.get("id") != str(event.sequence)
                        or frame.get("event") != event.event):
                    raise ValueError("Mismatched event")
                previous = event.sequence
                frame = {}
                required = {"classification": (event.predicted_intent, event.confidence),
                            "routing": (event.route, event.reason),
                            "step_started": (event.name, event.kind),
                            "step_finished": (event.step_id, event.status, event.elapsed_ms),
                            "final": (event.execution, event.http_status, event.outcome),
                            "failure": (event.code, event.http_status)}.get(event.event, ())
                if any(value is None for value in required):
                    raise ValueError("Missing event fields")
                if event.event == "step_started":
                    steps[event.sequence] = False
                if event.event == "step_finished":
                    if event.step_id not in steps or steps[event.step_id]:
                        raise ValueError("Mismatched step")
                    steps[event.step_id] = True
                if event.event == "failure":
                    outcome = event.outcome or "unknown"
                    messages = {"not_started": "Chat history could not be saved or restored. No new turn was executed.",
                                "unsaved": "The turn ran, but its outcome was not saved. No automatic retry.",
                                "saved": "Execution failed. Check saved chat for the retained outcome."}
                    raise ui_client.ChatClientError(messages.get(outcome,
                        "Turn completion is unknown. Check saved chat; no automatic retry."), outcome=outcome)
                if event.event == "final":
                    data = {"session_id": session_id, "turn_id": turn_id, **event.execution}
                    execution = ChatResponse.model_validate(data)
                    if (execution.session_id != session_id or execution.turn_id != turn_id
                            or event.outcome != "saved" or event.http_status not in {200, 503}
                            or (event.http_status == 503) != (execution.status in {"error", "partial_failure"})):
                        raise ValueError("Invalid final outcome")
                    payload = execution.model_dump(mode="json")
                    for index, step in enumerate(data["trace"]):
                        if "reason" in step:
                            payload["trace"][index] = asdict(TypeAdapter(AgentTrace).validate_python(step))
                    on_event({"event": "final", "execution": payload})
                    return payload
                progress = event.model_dump(mode="json", exclude_none=True)
                if event.event == "step_finished" and "result" in raw_event:
                    progress["result"] = event.result
                on_event(progress)
            raise ValueError("Stream ended without a terminal outcome")
    except HTTPError as exc:
        raise ui_client.ChatClientError(f"Backend rejected the stream (HTTP {exc.code}). No automatic retry.") from None
    except (URLError, OSError):
        raise ui_client.ChatClientError("Activity connection interrupted. The turn may still be running. Check saved chat; no automatic retry.") from None
    except (ValueError, KeyError, TypeError):
        raise ui_client.ChatClientError("Activity stream was invalid or interrupted. The turn may have executed. Check saved chat; no automatic retry.") from None
