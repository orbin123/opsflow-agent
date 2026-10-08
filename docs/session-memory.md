# Durable local session memory

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

Each turn durably saves its user message and an application-generated assistant JSON
record containing reply, classification, route, status, reasons and actual
structured tool outcomes. Direct tools therefore contribute context even though
their `reply` is null. Agent clarification, errors and partial failures preserve
their actual statuses and successful observations. Sanitized classifier/routing
exceptions are saved as error records and still raise `RuntimeUnavailable` to the
caller. Invalid inputs are not conversational turns.

LLM-assisted sentiment also retains its reply, VADER input/result, and
`workflow_trace` stage records, including clarification, extraction failures,
and presentation partial failures. The agent can receive those outcomes on a
follow-up. Reading/replaying the stored record never runs extraction or scoring.

Prior user/assistant messages are passed to the agent when routing/extraction
defers. Wholly local direct requests do not initialize Groq; the fixed sentiment
workflow uses Groq without prior history, then passes history on agent handoff. History is data,
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
Total elapsed time returned to the caller includes waiting for the session lock,
history restoration, initial persistence, and execution. The stored execution
record uses the same duration; final save transaction and HTTP transport are excluded.

Memory uses the already-pinned LangChain Core 1.6.6 message types and an
`InMemoryChatMessageHistory` snapshot. SQLite supplies authoritative context on
each call; `RunnableWithMessageHistory` was removed to control commit ordering
and prevent premature in-memory appends. The snapshot class is deprecated for
removal in 2.0. No dependencies changed. External tracing is disabled around
session restoration, execution, and saving.
Records contain private source/results and must not be logged wholesale. No raw
orchestration responses, reasoning tokens or intermediate model/tool-message
transcripts are retained across turns.

History survives backend restart in a separate local SQLite database. One backend
owns it exclusively; workers/hosts cannot share live execution. Startup recovery
on first store use marks unfinished turns interrupted with unknown completion and
never retries them. Initial/final save failures stop execution/continuation as
appropriate, without silent memory/disk divergence. There is no automatic eviction,
truncation, or context budgeting. Large histories can exhaust process memory or
provider context, reported through the existing agent contract.
See [chat-persistence.md](chat-persistence.md) for storage/lock configuration,
duplicate protection for Python turn IDs, durable clearing, and failure contracts.
Reminder/email execution, catalogue APIs, browser navigation, and production-scale
memory remain separate work.

Offline verification covers direct-to-agent context, draft revision and demo/action
preservation, clarification answers, ambiguous-reference responses, session
isolation, clearing, same-session serialization, independent sessions, private
tracing isolation, failure records and rejection before history creation. Provider
doubles verify message/result flow; they do not establish model reliability.

Historical verification on 2026-10-06: all 631 tests (17 new), `pip check` and whitespace
checks pass. Two expected history-API deprecation warnings remain visible.
No live provider, SMTP/inbox, HTTP/UI or deployment tests were performed.
