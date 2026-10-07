# Session chat API

`POST /api/v1/chat` executes one turn through the existing session runtime.
Run `.venv/bin/python -m uvicorn app.main:app` for local single-process use.
The generated request/response schema is available at `/docs`.

```sh
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"local-chat","message":"Just check the sentiment of this I am happy"}'
```

Only `session_id` and `message` are accepted. Both must be nonblank strings;
their limits are 128 and 10,000 characters respectively. Input is preserved
exactly, including surrounding whitespace. Clients cannot set intent, confidence,
route or history. Reuse the exact same session ID for follow-ups; a different ID
starts a separate conversation. The handler calls the session entry point once
in FastAPI's worker thread pool because the runtime blocks during tool/provider
calls. Existing per-session locks serialize turns.

The response includes the echoed `session_id` and the existing execution fields:

- `status`: `completed`, `needs_clarification`, `partial_failure`, `error`, or the
  runtime's `agent_required` status (retained in the schema; normal chat handoff
  executes the agent instead of returning this intermediate status).
- `predicted_intent`, `confidence`, `route`, `reason`: classification and routing.
  Route is `direct` for local FAQ execution, `llm_assisted` for the fixed
  sentiment/keyword workflows, or `agent` for dynamic orchestration.
- `reply`: the sentiment/keyword workflow's explanation/fallback/clarification or the
  agent's application-rendered reply; null for wholly local direct tools.
- `result`: structured direct or LLM-assisted tool output; null for the agent route.
- `agent_reason`: the separate agent outcome reason, when present.
- `trace`: actual tool names, arguments, results, completion/failure states,
  timings, and agent-step reasons when applicable. Nested draft content and fixed
  user actions are retained. No private model reasoning is returned.
- `workflow_trace`: ordered attempted sentiment or keyword stages, each with `stage`, `status`,
  sanitized `reason`, and `elapsed_ms`. Empty when no workflow ran. Includes
  extraction on an eventual agent handoff. Local-tool duration also appears in
  the VADER/YAKE tool trace: both records describe the same single tool call.
- `elapsed_ms`: session execution time, including lock waiting and history
  processing; excludes HTTP transport, thread-pool scheduling and serialization.

HTTP 200 covers successful execution and clarification. Inspect `status` and
structured results: 200 does not mean a policy was matched or any email was sent.
HTTP 422 rejects invalid bodies before execution/history creation. HTTP 503 returns
the execution payload for `error` or `partial_failure`, retaining successful
observations and failed steps; classifier/routing unavailability instead returns
sanitized `{"detail":"..."}`. Failures remain in history through the existing
session wrapper. There are no automatic endpoint retries or request deduplication;
resubmitting a turn runs it again and appends another turn.

The classifier runs once before any LLM invocation. A sentiment or keyword
prediction at or above the saved threshold enters its fixed source-extraction → local VADER/YAKE →
presentation workflow, including quoted requests. Missing/ambiguous source returns
clarification without running the local tool. Contextual/compound/unsupported
extraction abstention invokes the agent once with the unchanged request and prior
history. Lower-confidence sentiment/keywords go straight to the agent through the existing confidence gate.

Extraction/local-tool failure stops without agent fallback. Explanation failure returns
HTTP 503 with `status=partial_failure`, `reason=presentation_failed`, the successful
VADER/YAKE `result`/tool trace, a fixed factual `reply`, and the failed explanation stage.
No endpoint/provider retry or repeated tool execution occurs. Older clients that restrict routes
to `direct`/`agent` must accept `llm_assisted`; the bundled client validates the
updated schema. `workflow_trace` defaults to empty when absent in an older response.

Session IDs are caller-owned keys, not authentication or authorization. This
endpoint is intended for the existing trusted local use; callers sharing an ID
share conversation context. History and traces contain private supplied text and
results. Memory lives in one process, resets on restart and is not shared across
multiple Uvicorn workers/hosts. There is no automatic eviction/truncation or HTTP
clearing/history API; application callers can use `clear_session_history`.
See [session-memory.md](session-memory.md) for memory and model limitations.

The existing five-tool agent can compose drafts but does not create reminders or
submit email. The FAQ endpoint remains stateless and FAQ-only. Structured logging,
metrics, authentication, other endpoints and UI are separate slices. This slice
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
