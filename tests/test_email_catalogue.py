from copy import deepcopy

import pytest

from app.ui.email_catalogue import saved_email_entries


def draft_step(status="completed"):
    return {"tool": "draft_email", "status": status, "arguments": {}, "reason": None,
            "elapsed_ms": 1, "result": {"email_draft": {"recipient": "Alex",
                "subject": "Literal **subject**", "body": "  First line\n<Second line>  "},
                "action_instructions": ["Review first.", "Send using your email client."]}}


def chat(key="one", steps=None, status="completed", completed="2026-10-08T10:00:00+00:00"):
    return {"session_id": key, "title": "Literal [chat]", "turns": [{
        "turn_id": key + "-turn", "sequence": 1, "message": "Exact\nrequest",
        "demo_policy": False, "state": "finished", "finished_at": completed,
        "execution": {"status": status, "trace": steps if steps is not None else [draft_step()]}}]}


def test_equal_content_separate_calls_compound_order_and_literal_fields():
    source = chat(steps=[{"tool": "summarize_text", "status": "completed"}, draft_step(), draft_step()])
    before = deepcopy(source)
    entries, unavailable = saved_email_entries([source])
    assert [entry["trace_index"] for entry in entries] == [1, 2]
    assert entries[0]["draft"]["body"] == "  First line\n<Second line>  "
    assert entries[0]["message"] == "Exact\nrequest" and source == before
    assert unavailable == 0


@pytest.mark.parametrize("status", ["partial_failure", "needs_clarification"])
def test_successful_draft_remains_when_source_turn_stops(status):
    entries, unavailable = saved_email_entries([chat(status=status)])
    assert len(entries) == 1 and entries[0]["status"] == status and unavailable == 0


def test_newest_completion_order_timezone_and_tie_break():
    entries, _ = saved_email_entries([chat("z"), chat("a"),
        chat("latest", completed="2026-10-08T16:30:00+05:30")])
    assert [entry["session_id"] for entry in entries] == ["latest", "a", "z"]


def test_running_interrupted_failed_tools_and_prior_demo_context():
    source = chat(steps=[draft_step("failed"), draft_step()])
    earlier = deepcopy(source["turns"][0])
    earlier.update(execution=None, demo_policy=True)
    source["turns"].insert(0, earlier)
    running = chat("running")
    running["turns"][0]["state"] = "running"
    interrupted = chat("interrupted")
    interrupted["turns"][0]["state"] = "interrupted"
    entries, unavailable = saved_email_entries([running, source, interrupted])
    assert len(entries) == 1 and entries[0]["demo_policy"] and unavailable == 0


@pytest.mark.parametrize("field,value", [("result", None), ("recipient", " "),
    ("body", ""), ("action_instructions", []), ("finished_at", "invalid")])
def test_invalid_completed_draft_is_reported(field, value):
    source = chat()
    turn = source["turns"][0]
    result = turn["execution"]["trace"][0]["result"]
    if field == "result":
        turn["execution"]["trace"][0]["result"] = value
    elif field == "finished_at":
        turn[field] = value
    elif field == "action_instructions":
        result[field] = value
    else:
        result["email_draft"][field] = value
    assert saved_email_entries([source]) == ([], 1)
