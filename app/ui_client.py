"""One-shot HTTP client for the local Streamlit console; no execution retries."""

import json
from dataclasses import asdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import TypeAdapter, ValidationError

from app.api.chat import ChatRequest, ChatResponse
from app.agent import AgentTrace


class ChatClientError(Exception):
    """Safe user-facing failure without raw server, request or transport details."""


def submit_chat(base_url: str, session_id: str, message: str) -> dict:
    body = ChatRequest(session_id=session_id, message=message)
    request = Request(base_url.rstrip("/") + "/api/v1/chat",
                      data=body.model_dump_json().encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        try:
            response = urlopen(request, timeout=210)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.status
            if status not in {200, 503}:
                raise ChatClientError(f"Backend rejected the request (HTTP {status}). No automatic retry.")
            data = json.loads(response.read())
        if status == 503 and isinstance(data, dict) and "detail" in data:
            detail = data["detail"]
            if isinstance(detail, dict) and detail.get("code") == "chat_persistence":
                if detail.get("outcome") == "unsaved":
                    raise ChatClientError("The turn ran, but its outcome was not saved. No automatic retry.")
                raise ChatClientError("Chat history could not be saved or restored. No new turn was executed.")
            raise ChatClientError("Backend unavailable. No execution results were returned.")
        execution = ChatResponse.model_validate(data)
        if execution.session_id != session_id:
            raise ChatClientError("Backend returned a different session. Results were not displayed.")
        if (status == 503) != (execution.status in {"error", "partial_failure"}):
            raise ChatClientError("Backend returned an inconsistent execution status.")
        payload = execution.model_dump(mode="json")
        # The shared union can select ToolTrace for an agent sentiment step,
        # dropping its outcome reason. Preserve the agent trace contract explicitly.
        for index, step in enumerate(data["trace"]):
            if "reason" in step:
                payload["trace"][index] = asdict(TypeAdapter(AgentTrace).validate_python(step))
        return payload
    except (URLError, OSError):
        raise ChatClientError("Backend connection failed or timed out. The turn may have executed; no automatic retry.") from None
    except (ValueError, ValidationError):
        raise ChatClientError("Backend returned an invalid response. The turn may have executed; no automatic retry.") from None
