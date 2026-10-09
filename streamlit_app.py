"""Local chat with completed inline execution details. Run from the repository root."""

import base64
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from app.ui_client import ChatClientError, create_chat, get_chat, list_chats, submit_chat, rename_chat, delete_chat, list_reminders
from app.chat_menu import chat_menu, HTML, CSS, JS
from app.email_catalogue import saved_email_entries


st.set_page_config(page_title="OpsFlow · Console", layout="wide")
_CHAT_MENU = st.components.v2.component("chat_actions", html=HTML, css=CSS, js=JS)


def console_styles() -> str:
    assets = Path(__file__).parent / "ui"
    css = (assets / "console.css").read_text()
    for family, filename in (("VT323", "VT323-Regular.ttf"),
                             ("IBM Plex Mono", "IBMPlexMono-Regular.ttf")):
        encoded = base64.b64encode((assets / "fonts" / filename).read_bytes()).decode("ascii")
        css += f'@font-face {{font-family: "{family}"; src: url(data:font/ttf;base64,{encoded}); font-display: swap;}}'
    return css


def show_execution(execution: dict, demo_policy: bool = False) -> None:
    status = execution["status"]
    if status in {"error", "partial_failure"}:
        st.error(f"Execution: {status}")
    elif status == "agent_required":
        st.warning(f"Execution: {status}")
    elif status != "needs_clarification":
        st.caption(f"Execution: {status}")
    summary = None
    draft = None
    if status == "completed" and execution["route"] == "agent" and len(execution["trace"]) == 1:
        step = execution["trace"][0]
        if step["tool"] == "summarize_text" and step["status"] == "completed":
            result = step["result"]
            if (isinstance(result, dict) and isinstance(result.get("summary"), str)
                    and result["summary"].strip() and isinstance(result.get("key_points"), list)
                    and all(isinstance(point, str) for point in result["key_points"])):
                summary = result
        elif step["tool"] == "draft_email" and step["status"] == "completed":
            result = step["result"]
            if isinstance(result, dict):
                content = result.get("email_draft")
                actions = result.get("action_instructions")
                if (isinstance(content, dict)
                        and all(isinstance(content.get(field), str) and content[field].strip()
                                for field in ("recipient", "subject", "body"))
                        and isinstance(actions, list) and actions
                        and all(isinstance(action, str) and action.strip() for action in actions)):
                    draft = result
    if summary is not None:
        st.caption("Summary")
        st.text(summary["summary"])
        if summary["key_points"]:
            st.caption("Key points")
            for point in summary["key_points"]:
                st.text("• " + point)
    elif draft is not None:
        if demo_policy:
            st.text("Policy information below is fictional demo policy.")
        st.caption("Email draft")
        st.text("Intended recipient: " + draft["email_draft"]["recipient"])
        st.text("Subject: " + draft["email_draft"]["subject"])
        st.text(draft["email_draft"]["body"])
        st.caption("What you should do")
        for action in draft["action_instructions"]:
            st.text("• " + action)
    elif execution["reply"] is not None:
        st.text(execution["reply"])
    if execution["result"] is not None:
        if execution["predicted_intent"] == "sentiment_analysis" and execution["route"] in {"direct", "llm_assisted"}:
            st.text("Sentiment: " + execution["result"]["label"])
        elif execution["predicted_intent"] == "keyword_extraction" and execution["route"] == "llm_assisted":
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
                if step["tool"] == "schedule_reminder" and step["result"] is None:
                    st.text("No reminder was created by this call." if step.get("reason") == "reminder_clarification"
                            else "No scheduling result was returned by this call.")
                else:
                    st.json(step["result"])


st.html(f"<style>{console_styles()}</style>")
if os.environ.get("OPSFLOW_TEMPORARY_DEMO") == "1":
    st.warning("Temporary demo: chats, drafts and reminders may disappear when the service sleeps, "
               "restarts or redeploys. Reminder emails are disabled. Use synthetic data only.")
for name, value in {"session_id": None, "turns": [], "pending": False,
                    "running": False, "queued": None, "drafts": {}, "uncertain": {},
                    "catalogue": [], "action": None, "composer_error": None,
                    "clear_composer": False, "blocked": False, "inflight": None,
                    "management": None, "deleted_selection": False, "view": "chat"}.items():
    st.session_state.setdefault(name, value)
api_url = os.environ.get("OPSFLOW_API_URL", "http://127.0.0.1:8000")


def save_draft() -> None:
    if "composer" in st.session_state:
        st.session_state.drafts[st.session_state.session_id] = st.session_state.composer


def change_view(view: str) -> None:
    if (st.session_state.pending or st.session_state.running
            or st.session_state.session_id in st.session_state.uncertain):
        return
    save_draft()
    st.session_state.view = view
    if view == "chat":
        st.session_state.composer = st.session_state.drafts.get(st.session_state.session_id, "")


def navigate(session_id: str | None = None) -> None:
    if st.session_state.pending or st.session_state.running:
        return
    save_draft()
    if st.session_state.view != "chat":
        st.session_state.composer = st.session_state.drafts.get(st.session_state.session_id, "")
    st.session_state.view = "chat"
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


def open_management(chat: dict) -> None:
    if st.session_state.blocked:
        return
    action = st.session_state["menu_" + chat["session_id"]].action
    if action in {"rename", "delete"}:
        st.session_state.management = {**chat, "operation": action}
        st.session_state.rename_title = chat["title"]


def close_management() -> None:
    st.session_state.management = None


@st.dialog("Rename chat", on_dismiss=close_management)
def rename_dialog(chat: dict) -> None:
    st.text(chat["title"])
    title = st.text_input("Chat title", key="rename_title", max_chars=120)
    if st.button("Save", key="save_chat_name", disabled=st.session_state.blocked):
        if not title.strip():
            st.error("Enter a nonblank title of at most 120 characters.")
        else:
            try:
                rename_chat(api_url, chat["session_id"], title)
            except ChatClientError as exc:
                st.error(str(exc))
            else:
                close_management()
                st.rerun()
    if st.button("Cancel", key="cancel_rename"):
        close_management()
        st.rerun()


@st.dialog("Delete chat", on_dismiss=close_management)
def delete_dialog(chat: dict) -> None:
    st.text(chat["title"])
    st.text("Delete this chat and its saved messages and Activity? This cannot be undone.")
    if st.button("Delete chat", key="confirm_delete_chat", disabled=st.session_state.blocked):
        try:
            delete_chat(api_url, chat["session_id"])
        except ChatClientError as exc:
            st.error(str(exc))
        else:
            key = chat["session_id"]
            st.session_state.drafts.pop(key, None)
            st.session_state.uncertain.pop(key, None)
            st.session_state.catalogue = [item for item in st.session_state.catalogue if item["session_id"] != key]
            if st.session_state.session_id == key:
                st.query_params.pop("chat", None)
                st.session_state.deleted_selection = True
            close_management()
            st.rerun()
    if st.button("Cancel", key="cancel_delete"):
        close_management()
        st.rerun()


# A rerun can interrupt the UI subscriber, never restart its consumed submission.
if st.session_state.inflight is not None and st.session_state.queued is None:
    interrupted = st.session_state.inflight
    st.session_state.inflight = None
    st.session_state.pending = False
    st.session_state.uncertain[interrupted["session_id"]] = {
        **interrupted, "execution": None, "state": "unknown",
        "error": "Activity connection interrupted. Check saved chat; the turn will not be retried."}

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

if st.session_state.deleted_selection:
    # Reset before instantiating the composer, and don't re-save a deleted draft.
    st.session_state.session_id = None
    st.session_state.composer = ""
    st.session_state.turns = []
    st.session_state.deleted_selection = False

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
if st.session_state.view != "chat" and (st.session_state.pending or st.session_state.running
                                        or selected in st.session_state.uncertain):
    # A turn started in another tab must leave recovery controls reachable.
    st.session_state.view = "chat"
    st.session_state.composer = st.session_state.drafts.get(selected, "")

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
        with st.container(key="workspace_row_" + chat["session_id"], horizontal=True, gap="small"):
            with st.container(key="selected_chat" if current else None, width="stretch"):
                st.button(literal_label(chat["title"]), key="chat_" + chat["session_id"],
                          icon=":material/check:" if current else None, width="stretch", wrap=False,
                          disabled=st.session_state.pending or st.session_state.running or catalogue_error is not None,
                          on_click=navigate, args=(chat["session_id"],))
            chat_menu(_CHAT_MENU, chat["title"], chat["session_id"], disabled=blocked,
                      on_action_change=lambda chat=chat: open_management(chat))
    with st.container(key="settings_footer"):
        with st.popover("Settings", icon=":material/settings:", key="settings_menu_" + st.session_state.view,
                        disabled=st.session_state.pending or st.session_state.running
                        or selected in st.session_state.uncertain):
            st.button("Docs", key="open_docs", icon=":material/menu_book:",
                      width="stretch", on_click=change_view, args=("docs",))
            st.button("Emails", key="open_emails", icon=":material/mail:",
                      width="stretch", on_click=change_view, args=("emails",))
            st.button("Reminders", key="open_reminders", icon=":material/alarm:",
                      width="stretch", on_click=change_view, args=("reminders",))

if st.session_state.view == "docs":
    with st.container(width=760, key="docs_guide"):
        st.button("Return to chat", key="return_to_chat", icon=":material/arrow_back:",
                  on_click=change_view, args=("chat",))
        try:
            guide = (Path(__file__).parent / "docs" / "user-guide.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            st.error("The guide is unavailable. Return to chat and try again later.")
        else:
            st.markdown(guide)
    st.stop()

if st.session_state.view == "reminders":
    with st.container(width=760, key="reminders_page"):
        st.button("Return to chat", key="return_to_chat", icon=":material/arrow_back:",
                  on_click=change_view, args=("chat",))
        st.header("Reminders")
        st.caption("Stored reminders. Create a one-time reminder in chat; delivery uses the separate reminder worker.")
        st.button("Refresh", key="refresh_reminders", icon=":material/refresh:")
        try:
            reminders = list_reminders(api_url)
        except ChatClientError:
            st.error("Saved reminders could not be loaded. Refresh to try again.")
        else:
            if not reminders:
                st.info("No stored reminders yet.")
            labels = {"pending": "Scheduled — awaiting delivery",
                      "submitting": "Submitting — outcome pending",
                      "retry": "Retry scheduled — definite pre-submission failure",
                      "accepted": "SMTP accepted — inbox delivery unconfirmed",
                      "failed": "Failed — intervention required",
                      "unknown": "Unknown — no automatic retry"}
            for reminder in reminders:
                with st.container(border=True, key="reminder_entry_" + reminder["reminder_id"]):
                    st.text(labels[reminder["state"]])
                    st.text(reminder["task"])
                    due = datetime.fromisoformat(reminder["due_at"]).astimezone(ZoneInfo(reminder["timezone"]))
                    st.text("Due: " + due.strftime("%d %b %Y · %H:%M:%S %z") + " · " + reminder["timezone"])
    st.stop()

if st.session_state.view == "emails":
    with st.container(width=760, key="emails_page"):
        st.button("Return to chat", key="return_to_chat", icon=":material/arrow_back:",
                  on_click=change_view, args=("chat",))
        st.header("Emails")
        st.caption("Saved drafts across chats. Review and send using your email application.")
        st.button("Refresh", key="refresh_emails", icon=":material/refresh:")
        try:
            if catalogue_error:
                raise ChatClientError("Catalogue unavailable")
            chats = [get_chat(api_url, chat["session_id"]) for chat in st.session_state.catalogue]
            entries, unavailable = saved_email_entries(chats)
        except ChatClientError:
            st.error("Saved email drafts could not be loaded. Refresh to try again.")
        else:
            if unavailable:
                st.warning(f"{unavailable} saved draft record(s) are unavailable because their details are invalid.")
            if not entries and not unavailable:
                st.info("No saved email drafts yet. Ask OpsFlow to draft an email in a chat.")
            for entry in entries:
                identity = f"{entry['session_id']}_{entry['turn_id']}_{entry['trace_index']}"
                with st.container(border=True, key="email_entry_" + identity):
                    st.caption("Draft")
                    if entry["status"] != "completed":
                        st.text("Source turn outcome: " + entry["status"])
                    if entry["demo_policy"]:
                        st.text("Policy information below is fictional demo policy.")
                    st.text("Intended recipient: " + entry["draft"]["recipient"])
                    st.text("Subject: " + entry["draft"]["subject"])
                    st.text(entry["draft"]["body"])
                    st.caption("What you should do")
                    for action in entry["actions"]:
                        st.text("• " + action)
                    completed = entry["completed"].astimezone(ZoneInfo("Asia/Kolkata"))
                    st.caption("Saved " + completed.strftime("%d %b %Y · %H:%M") + " IST")
                    st.text("Chat: " + entry["title"])
                    with st.expander("Chat context", key="email_context_" + identity):
                        st.text(entry["message"])
                    st.button("Open chat", key="email_source_" + identity,
                              on_click=navigate, args=(entry["session_id"],))
    st.stop()

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
    demo_policy = False
    for turn in st.session_state.turns:
        with st.container(key="turn_" + turn["turn_id"]):
            with st.container(horizontal_alignment="right"):
                with st.container(width=560, key="prompt_" + turn["turn_id"]):
                    with st.chat_message("user"):
                        st.text(turn["message"])
            if turn["execution"] is not None:
                with st.container(horizontal_alignment="left"):
                    with st.container(width=560, key="details_" + turn["turn_id"]):
                        show_activity(turn["execution"])
            with st.container(horizontal_alignment="left"):
                with st.container(width=560, key="answer_" + turn["turn_id"]):
                    with st.chat_message("assistant"):
                        if turn["execution"] is not None:
                            show_execution(turn["execution"], demo_policy or turn.get("demo_policy", False))
                        else:
                            st.error(turn["error"])
        demo_policy = demo_policy or turn.get("demo_policy", False)
    if st.session_state.queued is not None:
        with st.container(horizontal_alignment="right"):
            with st.container(width=560):
                with st.chat_message("user"):
                    st.text(st.session_state.queued["message"])
        with st.container(horizontal_alignment="left"):
            with st.container(width=560):
                live_activity = st.empty()

with st.container(key="composer_bar"):
    st.text_area("Message OpsFlow", key="composer", max_chars=10000, height=120,
                 disabled=blocked, on_change=save_draft)
    with st.container(horizontal_alignment="right"):
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
        st.session_state.inflight = submission
        with live_activity.container():
            activity = st.status("Activity · running", expanded=True)
            progress_steps = {}

            def update_activity(event):
                kind = event["event"]
                if kind == "classification":
                    activity.text(f"INTENT  {event['predicted_intent']}\nCONFIDENCE  {event['confidence']}")
                elif kind == "routing":
                    activity.text(f"ROUTE  {event['route']}\nRouting reason: {event['reason']}")
                elif kind == "step_started":
                    step = activity.expander(literal_label(event["name"]), expanded=False)
                    step.caption(event["kind"] + " stage")
                    if event.get("arguments") is not None:
                        step.caption("ARGUMENTS")
                        step.json(event["arguments"])
                    progress_steps[event["sequence"]] = step.empty()
                    progress_steps[event["sequence"]].text("Running…")
                elif kind == "step_finished":
                    with progress_steps[event["step_id"]].container():
                        st.text(f"{event['status']} · {event['elapsed_ms']} ms")
                        if event.get("reason") is not None:
                            st.text("Step reason: " + event["reason"])
                        if "result" in event:
                            st.caption("OBSERVATION")
                            if event.get("tool") == "schedule_reminder" and event["result"] is None:
                                st.text("No reminder was created by this call." if event.get("reason") == "reminder_clarification"
                                        else "No scheduling result was returned by this call.")
                            else:
                                st.json(event["result"])
                elif kind == "final":
                    failed = event["execution"]["status"] in {"error", "partial_failure"}
                    activity.update(label="Activity · saved", state="error" if failed else "complete")

            submit_chat(api_url, submission["session_id"], submission["message"],
                        turn_id=submission["turn_id"], on_event=update_activity)
        st.session_state.inflight = None
        st.session_state.drafts[submission["session_id"]] = ""
        st.session_state.clear_composer = True
    except ChatClientError as exc:
        st.session_state.inflight = None
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

if st.session_state.management is not None:
    if blocked:
        close_management()
    elif st.session_state.management["operation"] == "rename":
        rename_dialog(st.session_state.management)
    else:
        delete_dialog(st.session_state.management)
