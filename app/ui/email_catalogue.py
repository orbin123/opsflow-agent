"""Read-only projection of retained draft observations; never executes tools."""

from datetime import datetime

from pydantic import ValidationError

from app.chat.profile import PROFILE_ID
from app.tools.email_drafting import EmailDraftResult


def saved_email_entries(chats: list[dict]) -> tuple[list[dict], int]:
    entries = []
    unavailable = 0
    for chat in chats:
        demo_policy = False
        for turn in chat["turns"]:
            demo_policy = demo_policy or turn["demo_policy"]
            execution = turn["execution"]
            if turn["state"] != "finished" or execution is None:
                continue
            for index, step in enumerate(execution["trace"]):
                if step["tool"] != "draft_email" or step["status"] != "completed":
                    continue
                try:
                    result = step["result"]
                    validated = EmailDraftResult.model_validate(result)
                    if (not validated.email_draft.recipient.strip()
                            or not validated.action_instructions
                            or any(not action.strip() for action in validated.action_instructions)):
                        raise ValueError("Incomplete draft")
                    completed = datetime.fromisoformat(turn["finished_at"])
                    if completed.tzinfo is None:
                        raise ValueError("Missing timezone")
                except (ValidationError, ValueError, TypeError):
                    unavailable += 1
                    continue
                entries.append({"profile_id": PROFILE_ID, "session_id": chat["session_id"], "title": chat["title"],
                    "turn_id": turn["turn_id"], "sequence": turn["sequence"], "trace_index": index,
                    "completed": completed, "message": turn["message"],
                    "demo_policy": demo_policy, "status": execution["status"],
                    "draft": result["email_draft"], "actions": result["action_instructions"]})
    entries.sort(key=lambda entry: (-entry["completed"].timestamp(), entry["session_id"],
                                   entry["sequence"], entry["trace_index"]))
    return entries, unavailable
