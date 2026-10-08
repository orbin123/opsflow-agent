"""Local chat with completed inline execution details. Run from the repository root."""

import base64
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from app.ui_client import ChatClientError, create_chat, get_chat, list_chats, submit_chat


st.set_page_config(page_title="OpsFlow · Console", layout="wide")


def console_styles() -> str:
    assets = Path(__file__).parent / "ui"
    css = (assets / "console.css").read_text()
    for family, filename in (("VT323", "VT323-Regular.ttf"),
                             ("IBM Plex Mono", "IBMPlexMono-Regular.ttf")):
        encoded = base64.b64encode((assets / "fonts" / filename).read_bytes()).decode("ascii")
        css += f'@font-face {{font-family: "{family}"; src: url(data:font/ttf;base64,{encoded}); font-display: swap;}}'
    return css


def show_execution(execution: dict) -> None:
    status = execution["status"]
    if status in {"error", "partial_failure"}:
        st.error(f"Execution: {status}")
    elif status == "agent_required":
        st.warning(f"Execution: {status}")
    elif status != "needs_clarification":
        st.caption(f"Execution: {status}")
    if execution["reply"] is not None:
        st.text(execution["reply"])
    if execution["result"] is not None:
        if execution["predicted_intent"] == "keyword_extraction" and execution["route"] == "llm_assisted":
            if execution["result"]:
                st.dataframe(
                    [{"Phrase": item["phrase"], "Score": item["score"]} for item in execution["result"]],
                    hide_index=True, height="content",
                    column_config={"Score": st.column_config.NumberColumn(format="%.5f")},
                    alt="Extracted keyword phrases and YAKE relevance scores in ranked order",
                )
                st.caption("Lower scores indicate greater relevance; scores are not confidence probabilities.")
        elif not (execution["predicted_intent"] == "faq_retrieval" and execution["route"] == "llm_assisted"):
            st.json(execution["result"], expanded=True)


def show_activity(execution: dict) -> None:
    with st.expander("Activity", expanded=False, key="activity_" + execution["turn_id"]):
        st.text(f"INTENT  {execution['predicted_intent']}\nCONFIDENCE  {execution['confidence']}\n"
                f"ROUTE  {execution['route']}\nSTATUS  {execution['status']}")
        st.text(f"Routing reason: {execution['reason']}")
        if execution["agent_reason"] is not None:
            st.text(f"Agent outcome reason: {execution['agent_reason']}")
        st.text(f"Backend elapsed: {execution['elapsed_ms']} ms")
        st.caption("Includes session waiting/history; excludes HTTP transport. Confidence is the classifier score.")
        if execution.get("workflow_trace"):
            capability = {"keyword_extraction": "Keyword", "faq_retrieval": "FAQ",
                          "sentiment_analysis": "Sentiment"}[execution["predicted_intent"]]
            with st.expander(f"{capability} workflow stages", expanded=False,
                             key="workflow_" + execution["turn_id"]):
                for stage in execution["workflow_trace"]:
                    st.caption("LLM stage" if stage["stage"] in {"extract_source", "extract_question", "explain_result"}
                               else "Local tool stage")
                    st.text(f"{stage['stage']} · {stage['status']}\n"
                            f"Stage elapsed: {stage['elapsed_ms']} ms")
                    if stage["reason"] is not None:
                        st.text(f"Stage reason: {stage['reason']}")
        if not execution["trace"]:
            st.caption("No tool executions reported.")
        for number, step in enumerate(execution["trace"], 1):
            with st.expander(literal_label(f"{number}. {step['tool']} · {step['status']}"),
                             expanded=False, key=f"tool_{execution['turn_id']}_{number}"):
                st.text(f"Step elapsed: {step['elapsed_ms']} ms")
                if step.get("reason") is not None:
                    st.text(f"Step reason: {step['reason']}")
                st.caption("ARGUMENTS")
                st.json(step["arguments"])
                st.caption("OBSERVATION")
                st.json(step["result"])


st.html(f"<style>{console_styles()}</style>")
for name, value in {"session_id": None, "turns": [], "pending": False,
                    "running": False, "queued": None, "drafts": {}, "uncertain": {},
                    "catalogue": [], "action": None, "composer_error": None,
                    "clear_composer": False, "blocked": False}.items():
    st.session_state.setdefault(name, value)
api_url = os.environ.get("OPSFLOW_API_URL", "http://127.0.0.1:8000")


def save_draft() -> None:
    st.session_state.drafts[st.session_state.session_id] = st.session_state.get("composer", "")


def navigate(session_id: str | None = None) -> None:
    if st.session_state.pending or st.session_state.running:
        return
    save_draft()
    if session_id is None:
        st.session_state.action = "new"
    else:
        st.query_params["chat"] = session_id


def queue_message() -> None:
    if st.session_state.blocked:
        return
    save_draft()
    message = st.session_state.get("composer", "")
    if not message.strip() or len(message) > 10000:
        st.session_state.composer_error = "Enter a nonblank message of at most 10,000 characters."
        return
    st.session_state.composer_error = None
    st.session_state.queued = {"session_id": st.session_state.session_id,
                               "message": message, "turn_id": uuid4().hex}
    st.session_state.pending = True


def literal_label(title: str) -> str:
    # Native button labels support Markdown; supplied titles must remain literal.
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~:$])", r"\\\1", title)


catalogue_error = read_error = navigation_error = None
if st.session_state.action == "new":
    st.session_state.action = None
    try:
        created = create_chat(api_url)
        st.query_params["chat"] = created["session_id"]
    except ChatClientError as exc:
        navigation_error = str(exc)

if not st.session_state.pending:
    try:
        st.session_state.catalogue = list_chats(api_url)
    except ChatClientError as exc:
        catalogue_error = str(exc)

locators = st.query_params.get_all("chat")
invalid_locator = bool(locators) and (len(locators) != 1 or not locators[0].strip() or len(locators[0]) > 128)
selected = locators[0] if locators and not invalid_locator else None
if st.session_state.pending or st.session_state.running:
    # Navigation never moves a queued/known-running operation to another chat.
    selected = st.session_state.session_id
    invalid_locator = False
    if selected is not None:
        st.query_params["chat"] = selected
elif not locators and catalogue_error is None and st.session_state.catalogue:
    selected = st.session_state.catalogue[0]["session_id"]
    st.query_params["chat"] = selected

if selected != st.session_state.session_id:
    save_draft()
    st.session_state.session_id = selected
    st.session_state.composer = st.session_state.drafts.get(selected, "")
    st.session_state.composer_error = None
    st.session_state.turns = []
if st.session_state.clear_composer:
    st.session_state.composer = ""
    st.session_state.clear_composer = False

if invalid_locator:
    read_error = "This chat link is invalid. Choose a saved chat or start a new one."
    st.session_state.turns = []
elif selected is not None and not st.session_state.pending:
    try:
        saved = get_chat(api_url, selected)
        st.session_state.turns = []
        uncertain = st.session_state.uncertain.get(selected)
        for turn in saved["turns"]:
            execution = turn["execution"]
            if execution is not None:
                execution = {"session_id": selected, "turn_id": turn["turn_id"], **execution}
            error = turn["failure_reply"]
            if turn["state"] == "running":
                error = "Running or unsaved: this turn has no confirmed final outcome. Check saved chat to recover; it will not be retried."
                if uncertain is not None and uncertain["turn_id"] == turn["turn_id"]:
                    error = uncertain["error"] + " " + error
            st.session_state.turns.append({**turn, "execution": execution, "error": error})
        st.session_state.running = any(turn["state"] == "running" for turn in saved["turns"])
        if uncertain is not None:
            matched = next((turn for turn in saved["turns"] if turn["turn_id"] == uncertain["turn_id"]), None)
            if matched is not None and matched["state"] != "running":
                del st.session_state.uncertain[selected]
            elif matched is None:
                st.session_state.turns.append(uncertain)
    except ChatClientError as exc:
        read_error = str(exc)
        st.session_state.turns = []

blocked = (st.session_state.pending or st.session_state.running or read_error is not None
           or catalogue_error is not None or selected in st.session_state.uncertain)
st.session_state.blocked = blocked

st.title(">_ OpsFlow")
st.caption("Analyze communications, find demo policies, summarize text, and compose email drafts.")

with st.sidebar:
    st.subheader("Workspace")
    st.button("New chat", key="new_chat", icon=":material/add:", width="stretch",
              disabled=st.session_state.pending or st.session_state.running or catalogue_error is not None,
              on_click=navigate)
    if catalogue_error:
        st.error(catalogue_error)
        st.button("Retry chat list", key="retry_catalogue")
    elif not st.session_state.catalogue:
        st.caption("No saved chats yet.")
    for chat in st.session_state.catalogue:
        current = chat["session_id"] == selected and not invalid_locator
        with st.container(key="selected_chat" if current else None):
            st.button(literal_label(chat["title"]), key="chat_" + chat["session_id"],
                      icon=":material/check:" if current else None, width="stretch", wrap=False,
                      disabled=st.session_state.pending or st.session_state.running or catalogue_error is not None,
                      on_click=navigate, args=(chat["session_id"],))
        if current:
            st.caption("Selected chat")
        updated = datetime.fromisoformat(chat["updated_at"]).astimezone(ZoneInfo("Asia/Kolkata"))
        st.caption("Updated " + updated.strftime("%d %b · %H:%M") + " IST")
    st.caption("Email drafts need your review and sending. Chat cannot schedule reminders or send email.")

st.subheader("Conversation")
if navigation_error:
    st.error(navigation_error)
if read_error:
    st.error(read_error)
if read_error or st.session_state.running or selected in st.session_state.uncertain:
    st.button("Check saved chat", key="recover_chat", disabled=st.session_state.pending)
if st.session_state.pending:
    st.caption("Running — navigation and submission are paused.")
elif st.session_state.running:
    st.warning("Completion is unconfirmed. Navigation and submission are paused until a saved outcome is available.")
conversation = st.container()
with conversation:
    if not st.session_state.turns and read_error is None and catalogue_error is None and not st.session_state.pending:
        st.info('Start with: Sentiment: "I am happy"')
    for turn in st.session_state.turns:
        with st.chat_message("user"):
            st.text(turn["message"])
        with st.chat_message("assistant"):
            if turn["execution"] is not None:
                show_execution(turn["execution"])
                show_activity(turn["execution"])
            else:
                st.error(turn["error"])
    if st.session_state.queued is not None:
        with st.chat_message("user"):
            st.text(st.session_state.queued["message"])
        with st.chat_message("assistant"):
            st.caption("Running request…")
st.text_area("Message OpsFlow", key="composer", max_chars=10000, height=120,
             disabled=blocked, on_change=save_draft)
st.button("Send", key="send_message", type="primary", disabled=blocked,
          on_click=queue_message)
if st.session_state.composer_error:
    st.error(st.session_state.composer_error)


# A queued button submission runs once after disabled navigation/composer render.
# Clear the queue before HTTP so later reruns/reconnects cannot submit it again.
if st.session_state.queued is not None:
    submission = st.session_state.queued
    st.session_state.queued = None
    try:
        if submission["session_id"] is None:
            created = create_chat(api_url)
            submission["session_id"] = created["session_id"]
            st.session_state.session_id = created["session_id"]
            st.query_params["chat"] = created["session_id"]
        with st.spinner("Running request…"):
            submit_chat(api_url, submission["session_id"], submission["message"], turn_id=submission["turn_id"])
        st.session_state.drafts[submission["session_id"]] = ""
        st.session_state.clear_composer = True
    except ChatClientError as exc:
        if submission["session_id"] is None:
            st.session_state.composer_error = "A new chat could not be confirmed. No turn was submitted."
        else:
            st.session_state.uncertain[submission["session_id"]] = {
                **submission, "execution": None, "error": str(exc), "state": "unknown"}
            if exc.outcome == "not_started":
                st.session_state.composer_error = str(exc)
                del st.session_state.uncertain[submission["session_id"]]
            else:
                st.session_state.drafts[submission["session_id"]] = ""
                st.session_state.clear_composer = True
    finally:
        st.session_state.pending = False
    st.rerun()
