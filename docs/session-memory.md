# Process-local session memory

```python
from app.sessions import execute_session_request, clear_session_history

first = execute_session_request("local-chat", 'Sentiment: "I am happy"')
followup = execute_session_request("local-chat", "Draft an email to Alex about that result")
print(followup.status, followup.reply)
clear_session_history("local-chat")
```

The entry point returns the existing `ExecutionResult`. It validates a nonblank
message of at most 10,000 characters and an exact, nonblank session ID of at most
128 characters. Invalid input creates no history. Session IDs are caller-owned
keys, not credentials; the local `/api/v1/chat` endpoint exposes turns without an
authorization layer. See [chat-api.md](chat-api.md) for the HTTP contract.
Different keys get separate histories. Existing `execute_request`, `run_agent`
and the FAQ endpoint remain stateless unless history is explicitly supplied.

Each turn saves its user message and an application-generated assistant JSON
record containing reply, classification, route, status, reasons and actual
structured tool outcomes. Direct tools therefore contribute context even though
their `reply` is null. Agent clarification, errors and partial failures preserve
their actual statuses and successful observations. Sanitized classifier/routing
exceptions are saved as error records and still raise `RuntimeUnavailable` to the
caller. Invalid inputs are not conversational turns.

Prior user/assistant messages are passed to the agent only when direct gates
defer; a self-contained direct request does not initialize Groq. History is data,
not new system instructions. The agent prompt asks it to resolve follow-ups using
supplied facts, clarify missing/ambiguous references and respect failed outcomes.
These are model decisions, not guaranteed by memory transport or schema checks.
A revised draft still uses `draft_email`, application-rendered content and fixed
review/send actions. A trusted history marker for a demo FAQ observation causes
subsequent rendered drafts to retain a demo qualification. This is conservative:
an unrelated later draft in that session may also be qualified until clearing.

One lock per session covers the entire turn, including execution and history
updates. Clearing waits for an active turn, then clears all message contents.
The session entry/lock remains to avoid races with waiting callers; a subsequent
turn starts with empty history. Different sessions can execute concurrently.
Total elapsed time returned to the caller includes waiting for the session lock
and history handling. The stored execution record contains the inner runtime
timing rather than that outer duration.

Memory uses the already-pinned LangChain Core 1.6.6 `InMemoryChatMessageHistory`
and `RunnableWithMessageHistory`. Both are deprecated in that installed version
for removal in 2.0. No dependencies were changed; a framework migration is a
future decision. External tracing is disabled around the entire history runnable.
Records contain private source/results and must not be logged wholesale. No raw
orchestration responses, reasoning tokens or intermediate model/tool-message
transcripts are retained across turns.

History is local to one Python process and lost on restart. It is not shared
between workers/hosts or persisted to SQLite. This first slice has no automatic
eviction, truncation or context-token budgeting; callers should explicitly clear
histories when finished. Large histories can exhaust process memory or provider
context, with provider failures reported through the existing agent contract.
Reminder/email execution, UI integration and production-scale memory remain
separate work.

Offline verification covers direct-to-agent context, draft revision and demo/action
preservation, clarification answers, ambiguous-reference responses, session
isolation, clearing, same-session serialization, independent sessions, private
tracing isolation, failure records and rejection before history creation. Provider
doubles verify message/result flow; they do not establish model reliability.

Verification on 2026-10-06: all 631 tests (17 new), `pip check` and whitespace
checks pass. Two expected history-API deprecation warnings remain visible.
No live provider, SMTP/inbox, HTTP/UI or deployment tests were performed.
