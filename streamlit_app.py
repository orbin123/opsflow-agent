"""Local chat and execution inspector. Run from the repository root."""

import base64
import os
from pathlib import Path
from uuid import uuid4

import streamlit as st

from app.ui_client import ChatClientError, submit_chat


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
    elif status in {"needs_clarification", "agent_required"}:
        st.warning(f"Execution: {status}")
    else:
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
        else:
            if isinstance(execution["result"], dict) and execution["result"].get("is_demo"):
                st.caption("Fictional demo policy — verify your actual company policy.")
            st.json(execution["result"], expanded=True)


st.html(f"<style>{console_styles()}</style>")
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid4().hex
    st.session_state.turns = []
    st.session_state.pending = False

st.title(">_ OpsFlow")
st.caption("Analyze communications, find demo policies, summarize text, and compose email drafts.")

with st.sidebar:
    st.subheader("Workspace")
    st.caption("Email drafts need your review and sending. Chat cannot schedule reminders or send email.")

chat_column, inspector_column = st.columns([2, 1], gap="large")
with chat_column:
    st.subheader("Conversation")
    conversation = st.container()
    with conversation:
        if not st.session_state.turns:
            st.info('Start with: Sentiment: "I am happy"')
        for turn in st.session_state.turns:
            with st.chat_message("user"):
                st.text(turn["message"])
            with st.chat_message("assistant"):
                if turn["execution"] is not None:
                    show_execution(turn["execution"])
                else:
                    st.error(turn["error"])
    message = st.chat_input("Message OpsFlow", key="message", max_chars=10000,
                            disabled=st.session_state.pending, submit_mode="disable")
    if message is not None:
        if not message.strip() or len(message) > 10000:
            st.error("Enter a nonblank message of at most 10,000 characters.")
        else:
            st.session_state.pending = True
            turn = {"message": message, "execution": None, "error": None}
            # Retain the submitted turn even if the HTTP outcome is unknown.
            st.session_state.turns.append(turn)
            try:
                with st.spinner("Running request…"):
                    turn["execution"] = submit_chat(os.environ.get("OPSFLOW_API_URL", "http://127.0.0.1:8000"),
                                                    st.session_state.session_id, message)
            except ChatClientError as exc:
                turn["error"] = str(exc)
            finally:
                st.session_state.pending = False
            st.rerun()

with inspector_column:
    st.subheader("Execution inspector")
    st.caption("Observable tool activity and backend timings.")
    if not st.session_state.turns:
        st.info("Submit a message to inspect its execution.")
    else:
        index = st.selectbox("Inspect turn", range(len(st.session_state.turns)),
                             index=len(st.session_state.turns) - 1,
                             format_func=lambda value: f"Turn {value + 1}")
        turn = st.session_state.turns[index]
        execution = turn["execution"]
        if execution is None:
            st.error(turn["error"] or "Waiting for backend results.")
        else:
            st.text(f"INTENT  {execution['predicted_intent']}\nCONFIDENCE  {execution['confidence']}\n"
                    f"ROUTE  {execution['route']}\nSTATUS  {execution['status']}")
            st.text(f"Routing reason: {execution['reason']}")
            if execution["agent_reason"] is not None:
                st.text(f"Agent outcome reason: {execution['agent_reason']}")
            st.text(f"Backend elapsed: {execution['elapsed_ms']} ms")
            st.caption("Includes session waiting/history; excludes HTTP transport. Confidence is the classifier score.")
            if execution.get("workflow_trace"):
                capability = "Keyword" if execution["predicted_intent"] == "keyword_extraction" else "Sentiment"
                with st.expander(f"{capability} workflow stages", expanded=True):
                    for stage in execution["workflow_trace"]:
                        st.caption("LLM stage" if stage["stage"] in {"extract_source", "explain_result"}
                                   else "Local tool stage")
                        st.text(f"{stage['stage']} · {stage['status']}\n"
                                f"Stage elapsed: {stage['elapsed_ms']} ms")
                        if stage["reason"] is not None:
                            st.text(f"Stage reason: {stage['reason']}")
            if not execution["trace"]:
                st.caption("No tool executions reported.")
            for number, step in enumerate(execution["trace"], 1):
                with st.expander(f"{number}. {step['tool']} · {step['status']}", expanded=True):
                    st.text(f"Step elapsed: {step['elapsed_ms']} ms")
                    if step.get("reason") is not None:
                        st.text(f"Step reason: {step['reason']}")
                    st.caption("ARGUMENTS")
                    st.json(step["arguments"])
                    st.caption("OBSERVATION")
                    st.json(step["result"])
