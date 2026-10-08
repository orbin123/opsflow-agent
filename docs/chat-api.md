# Session chat API

`POST /api/v1/chat` executes one turn through the existing session runtime.
Run `.venv/bin/python -m uvicorn app.main:app` for local single-process use.
The generated request/response schema is available at `/docs`.

```sh
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"local-chat","message":"Just check the sentiment of this I am happy"}'
```

`session_id`, `message`, and optional `turn_id` are accepted. Both must be nonblank strings;
their limits are 128 and 10,000 characters respectively. Input is preserved
exactly, including surrounding whitespace. Clients cannot set intent, confidence,
route or history. Reuse the exact same session ID for follow-ups; a different ID
starts a separate conversation. The handler calls the session entry point once
in FastAPI's worker thread pool because the runtime blocks during tool/provider
calls. Existing per-session locks serialize turns.

The response includes the echoed `session_id`, accepted `turn_id` (generated when omitted),
and the existing execution fields:

- `status`: `completed`, `needs_clarification`, `partial_failure`, `error`, or the
  runtime's `agent_required` status (retained in the schema; normal chat handoff
  executes the agent instead of returning this intermediate status).
- `predicted_intent`, `confidence`, `route`, `reason`: classification and routing.
  Route is `llm_assisted` for fixed sentiment/keyword/FAQ workflows, or `agent` for
  dynamic orchestration. The shared schema retains `direct`; the separate FAQ-only
  endpoint still uses it for wholly local execution.
- `reply`: the sentiment/keyword/FAQ workflow's explanation/fallback/clarification or the
  agent's application-rendered reply; null for wholly local direct tools.
- `result`: structured direct or LLM-assisted tool output; null for the agent route.
- `agent_reason`: the separate agent outcome reason, when present.
- `trace`: actual tool names, arguments, results, completion/failure states,
  timings, and agent-step reasons when applicable. Nested draft content and fixed
  user actions are retained. No private model reasoning is returned.
- `workflow_trace`: ordered attempted sentiment, keyword, or FAQ stages, each with `stage`, `status`,
  sanitized `reason`, and `elapsed_ms`. Empty when no workflow ran. Includes
  extraction on an eventual agent handoff. Local-tool duration also appears in
  the VADER/YAKE/FAQ tool trace: both records describe the same single tool call.
- `elapsed_ms`: session execution time, including lock waiting and history
  restoration/initial persistence; excludes the final save transaction,
  HTTP transport, thread-pool scheduling and serialization.

HTTP 200 covers successful execution and clarification. Inspect `status` and
structured results: 200 does not mean a policy was matched or any email was sent.
HTTP 422 rejects invalid bodies before execution/history creation. HTTP 503 returns
the execution payload for `error` or `partial_failure`, retaining successful
observations and failed steps; classifier/routing unavailability instead returns
sanitized `{"detail":"..."}`. Failures remain in history through the existing
session wrapper. There are no automatic endpoint retries. A supplied nonblank `turn_id` (up to
128 characters) replays an identical saved chat/message submission without execution,
including after restart. Conflicting content/chat or running/interrupted IDs return
HTTP 409 with `detail.code="chat_turn_conflict"`, nullable `state`, and sanitized
`message`. Finished failures replay with their original 503 semantics. Without an ID,
each POST generates a new one and executes a new turn; explicit null also omits identity.
Duplicate protection applies only while saved records are retained.

The classifier runs once before any LLM invocation. A sentiment, keyword, or FAQ
prediction at or above the saved threshold enters its fixed extraction → local tool →
presentation workflow, including quoted requests. FAQ presentation runs only for a
matched policy; ambiguity/no-match clarifies without presentation. A presenter may
also clarify when a matched policy lacks a material requested detail. Missing/ambiguous input returns
clarification without running the local tool. Contextual/compound/unsupported
extraction abstention invokes the agent once with the unchanged request and prior
history. Lower-confidence sentiment/keywords/FAQ go straight to the agent through the existing confidence gate.

Extraction/local-tool failure stops without agent fallback. Explanation failure returns
HTTP 503 with `status=partial_failure`, `reason=presentation_failed`, the successful
VADER/YAKE/FAQ `result`/tool trace, a fixed factual `reply`, and the failed explanation stage.
No endpoint/provider retry or repeated tool execution occurs. Older clients that restrict routes
to `direct`/`agent` must accept `llm_assisted`; the bundled client validates the
updated schema. `workflow_trace` defaults to empty when absent in an older response.

Session IDs are caller-owned keys, not authentication or authorization. This
endpoint is intended for the existing trusted local use; callers sharing an ID
share conversation context. History and traces contain private supplied text and
results. History is stored in a separate local SQLite database and restored on backend
restart. One backend holds exclusive store ownership; multiple Uvicorn workers/hosts
cannot share execution. There is no automatic eviction/truncation or HTTP
clearing API; application callers can use `clear_session_history`.
See [session-memory.md](session-memory.md) for memory and model limitations.

REWORK step 7 storage failures return HTTP 503 with a sanitized object in `detail`:
`code="chat_persistence"`, `outcome="not_started"` or `"unsaved"`, and `message`.
The former means no new execution occurred; the latter means execution started but
the outcome was not saved. An unfinished/unsaved turn blocks subsequent execution
in that chat with HTTP 409. A fresh backend conservatively marks unfinished work
interrupted; it never repeats it. Python turn-ID deduplication is implemented,
and step 8 exposes the same replay contract over HTTP. See [chat-persistence.md](chat-persistence.md).

The existing five-tool agent can compose drafts but does not create reminders or
submit email. The FAQ endpoint remains stateless and FAQ-only. Structured logging,
metrics, authentication, other endpoints and Workspace navigation are separate slices. This slice
adds no dependency or provider changes. Verification uses offline provider doubles;
it does not establish general model quality or reference-resolution reliability.

Verified on 2026-10-06: all 652 tests (21 new), `pip check` and whitespace checks
pass. A local Uvicorn request exercised the real classifier and direct sentiment
tool over HTTP with a 200 response before sentiment workflow integration. Existing two LangChain history-API deprecation
warnings remain. No live Groq, SMTP/inbox, UI or deployment checks were performed.

REWORK step 2b verification on 2026-10-07: all 721 tests, dependency and whitespace
checks pass. TestClient and AppTest checks cover the classifier-first workflow,
clarification/handoff, retained HTTP 503 outcomes, client schema, saved history,
and non-executing rerenders with provider doubles. No live Groq quality checks.

REWORK step 3b verification on 2026-10-07: the 784-test suite passes, including
keyword workflow gating, retained failures/empty results, original-history handoff,
API/client/history round-trips, and non-executing UI rerenders with provider doubles.
No live Groq quality checks or classifier training/threshold changes.

REWORK step 3d verification on 2026-10-07: all 855 tests (22 new), dependency and
whitespace checks pass. FAQ workflow/API/client/history and rerender contracts are
covered offline. A limited synthetic live HTTP review confirmed the fixed FAQ path
and final fresh/post-draft contractor clarifications after an initial agent eligibility
error and prompt correction. These samples do not establish general model grounding.

## Chat catalogue — REWORK step 8

- `POST /api/v1/chats` with `{}` returns HTTP 201 and metadata: `session_id`,
  `title="New chat"`, UTC `created_at` and `updated_at`. Extra fields are rejected.
- `GET /api/v1/chats` returns a metadata list, ordered by descending `updated_at`
  then ascending ID. Empty storage returns `[]`. No pagination in this local slice.
- `GET /api/v1/chats/{session_id}` returns metadata and `turns` in increasing
  sequence order. URL-encode caller-owned IDs. Unknown chats return HTTP 404;
  invalid IDs return 422. Unknown reads never create records.

Turns retain `turn_id`, `session_id`, `sequence`, exact `message`, `started_at`,
nullable `finished_at`, lifecycle `state`, nullable `execution`, nullable
`failure_reply`/`failure_reason`, and trusted `demo_policy`. Execution contains
all original outcomes/results/tool and workflow activity and timings. Running or
interrupted records do not invent completed results. Runtime failure records can
be finished with a sanitized failure and no execution payload.

Metadata and turns are read from one SQLite snapshot. Reads do not wait for a
chat's execution lock, alter update times, classify, invoke providers/tools, or
submit messages. Initial store ownership still performs step 7's conservative
interrupted recovery. Read/write storage errors return the existing sanitized
503 persistence envelope; corrupt execution records fail rather than appear empty.
The catalogue is shared across local browser tabs, under the existing one-user,
one-backend boundary; IDs remain identifiers, not authorization.

The HTTP client exposes `create_chat`, `list_chats`, `get_chat`, and optional
`submit_chat(..., turn_id=...)`. It validates records/identity and reports safe
errors without retries. Step 9 connects Workspace controls and refresh restoration;
see [streamlit-console.md](streamlit-console.md).

## Chat management — requested Workspace addition

`PATCH /api/v1/chats/{session_id}` accepts only `{"title": "Release review"}`.
Titles must be nonblank strings of at most 120 characters; whitespace is collapsed
and display remains literal. HTTP 200 returns updated chat metadata. Custom titles
survive the first submission in an empty chat and backend restart. Rename changes
no saved turn, context, execution result or Activity record.

`DELETE /api/v1/chats/{session_id}` permanently removes that chat and its saved
turns, returning HTTP 200 with `{"session_id": "..."}`. Cached context is cleared
only after the transaction succeeds. Deletion releases retained submission IDs;
their replay guarantee exists only while records are retained.

Both operations URL-encode IDs, never invoke classification/providers/tools, and
return 404 for unknown chats, 409 for active execution or running/unsaved markers,
422 for invalid input, or sanitized 503 storage errors. Transactions roll back
failed writes; session-lock acquisition is nonblocking. Other chats remain intact.
The client exposes `rename_chat` and `delete_chat`, validates response identity,
and never retries mutations. A lost/invalid response may follow a committed change;
the client tells users to check the catalogue before trying again.

## Execution event stream — REWORK step 10

`POST /api/v1/chat/stream` accepts the same validated `ChatRequest` as the
nonstreaming endpoint and executes the same session entry point once. Invalid
bodies return HTTP 422 before execution. Valid requests return HTTP 200 with
`Content-Type: text/event-stream`, `Cache-Control: no-cache`, and
`X-Accel-Buffering: no`. After headers are sent, terminal events carry the outcome
in `http_status` (200/409/503); the transport's 200 is not execution success.

```sh
curl -N -X POST http://127.0.0.1:8000/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"local-chat","turn_id":"one-operation","message":"Just check the sentiment of this I am happy"}'
```

Use a streaming POST client (`fetch` plus its response reader, or a streaming
HTTP client), rather than browser `EventSource`, which submits GET requests.
The response consists of SSE frames with numeric `id`, named `event`, and one
JSON `data` line. Newlines in user text are JSON-escaped, so caller-owned strings
cannot create additional SSE fields. A comment heartbeat every 15 idle seconds
keeps the connection active; it does not assert progress or add an event sequence.
A client must handle arbitrary byte-chunk boundaries and stop at `final`/`failure`.

Every JSON event has `version=1`, exact `session_id` and `turn_id`, increasing
one-based `sequence`, and `event`. The sequence is local to this subscription;
it is neither a durable record ID nor a resume cursor. Step finish events identify
their corresponding start with `step_id` equal to the start event's sequence.

| Event | Application data and meaning |
| --- | --- |
| `turn` | Echoes identity before storage/execution; does not acknowledge durable acceptance. Omitted turn IDs receive a generated UUID. |
| `classification` | Actual `predicted_intent` and `confidence`, after the classifier returns. |
| `routing` | Selected `route` and factual `reason`, before entering that route. High-confidence fixed workflows use `high_confidence_workflow`; an extraction abstention emits a second agent routing event with its actual reason. |
| `step_started` | `name`, `kind` (`workflow`, `model`, `tool`), nullable validated `arguments`. Only attempted stages are emitted. |
| `step_finished` | Correlated `step_id`, actual `status`, sanitized `reason`, `elapsed_ms`; workflow `stage` or agent `tool`, with validated arguments/results for tools. Tool/workflow fields come from the same trace records retained in the outcome. |
| `final` | `outcome="saved"`, `http_status`, and `execution` containing all existing execution fields. Sent only after the session wrapper commits the outcome. Includes completed, clarification, error and partial-failure results. |
| `failure` | Sanitized `code`, `message`, `http_status`, and applicable `outcome` or `state`. Terminal; never invents a final execution payload. |

Fixed workflows emit extraction, local-tool and (only when attempted)
presentation stages. Agent model events cover actual orchestration calls: completed
means the provider call returned, not that its output passed validation. Raw
model responses, instructions, history, provider metadata/logs and private reasoning
are not emitted. Agent tools start only after local argument validation and budget
checks. Inputs/results can contain private supplied text, as in the existing trace;
the trusted local access boundary is unchanged. These are progress events rather
than token streaming. Final timings retain the existing session timing boundary.

Failure codes are `chat_persistence` (503, `outcome=not_started` or `unsaved`),
`chat_turn_conflict` (409, nullable `state`), `runtime_unavailable` (503,
`outcome=saved`, a sanitized failure committed by sessions), or
`execution_unknown` (503, `outcome=unknown`, unexpected transport/worker failure).
A failed final save emits `failure` with `unsaved`, even if previous events showed
successful tools. Those progress events are not durable completion proof.

A subscriber disconnect does not cancel the worker, retry providers/tools, or
release database ownership. Graceful backend shutdown waits for disconnected work
before closing the store. A forced process exit can still interrupt execution;
exclusive ownership recovery marks running turns interrupted under step 7's
existing contract. No new persistence schema or intermediate event journal is added.

Progress is transient and discarded after disconnect. Use `GET /api/v1/chats/{id}`
to recover the authoritative running/finished/interrupted state and exact saved
outcome. Reads never execute a turn. There is no GET subscription/replay endpoint
and `Last-Event-ID` does not resume progress. Do not automatically resubmit unknown
work. An explicit POST using the same retained ID/chat/message returns only `turn`
and the saved terminal outcome, without classifier/provider/tool events or calls.
An in-flight duplicate waits on the existing per-chat lock and then returns the
saved outcome; an unsaved/interrupted marker conflicts. Conflicting content/chat
also conflicts. Identity protection applies while turn records are retained.

Streamlit step 13 submits once through this stream, displays actual transient
activity, and restores authoritative outcomes through GET. Step 11 places saved
details between the right prompt and left answer in a vertical sequence. The
nonstreaming endpoint remains available to other callers.
No new external service, dependency, email/reminder execution or UI redesign.
