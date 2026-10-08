# Durable local chat history

REWORK step 7 adds `app/chat_store.py` and connects it to `app/sessions.py`.
SQLite is authoritative: every request restores prior user/assistant context from
saved records. The process-local history object is a snapshot, not a fallback.
Reminder storage, worker locking, tools, routing thresholds, and providers are
unchanged. Step 8 exposes catalogue HTTP APIs and submission IDs; step 9 connects
browser navigation/restoration. See [chat-api.md](chat-api.md) and
[streamlit-console.md](streamlit-console.md).

## Configuration and ownership

`OPSFLOW_CHATS_DB` selects a persistent local file; the default is
`var/chats.sqlite3`. Relative paths are rooted at the repository. Backend `.env`
loading preserves existing environment variables. Parent directories are created
on first use. Database/sidecar/lock files are already ignored by Git.

The store initializes lazily on the first session operation. It takes an exclusive
nonblocking Unix file lock at `<resolved-database-path>.lock` and retains it until
backend shutdown. A second cooperating backend fails before recovery or execution.
This supports one trusted local backend process on one filesystem. Network storage,
multiple hosts, Windows, hard-link aliases, and removing/replacing an active lock
file are unsupported. Paths resolve symlinks; never share the chat database with
the reminder worker. Changing the configured chat path requires backend restart.
Use `close_chat_store()` only after active operations finish; FastAPI shutdown does
this after requests drain.

IDs are identifiers, not credentials. Browsers using the local backend share its
chat records; do not expose this unauthenticated service publicly. Records contain
private text/results and are not logged wholesale. Filesystem access is the access
boundary. There is no hosted ownership layer, encryption, or automatic backup.

## Records and execution lifecycle

Schema version 1 uses `chats` and `chat_turns`, foreign keys, and transactional
writes. Unsupported versions/foreign schemas are rejected without replacement.
Chat metadata contains the exact session key, literal first-message title, UTC
creation/update timestamps, and the next sequence number. A turn contains its ID,
chat/sequence, original message, timestamps, lifecycle, execution JSON or sanitized
failure, and the trusted demo-policy marker. Sequences stay increasing even after
an explicit clear. Titles collapse whitespace, take 60 Unicode characters, and
append an ellipsis when truncated. No title-generation model call is made.

1. Validate the message, session key, and optional turn ID before storage.
2. Under the per-chat lock, restore ordered completed/interrupted context and
   commit the new message with state `running`. A failed commit prevents execution.
3. Execute once outside the SQLite transaction, using only that chat's context.
4. Commit state `finished` and the real outcome before acknowledging saved success.
   A finished outcome can be completed, clarification, partial failure, or error.
   Runtime unavailability saves a sanitized error and is still raised to the caller.

The saved payload retains all current classification/routing fields, replies,
structured results, tool and workflow traces, reasons, timings, demo qualification,
and draft actions. The response and saved payload use the same `elapsed_ms`, measured
through lock waiting, restoration, the initial commit, and execution. The final
save transaction, HTTP transport, and rendering are excluded. Stage/tool timings
remain unchanged. Runtime-unavailable/interrupted records do not invent these fields.

An unsuccessful final commit leaves the original running marker and returns an
explicit **unsaved** failure. Further submissions in that chat are blocked; it
cannot continue using uncommitted in-memory results. Unexpected execution exceptions
also leave an unknown marker and return a sanitized failure. After exclusive
ownership is acquired by a fresh process, prior running markers become `interrupted`
with a factual unknown-completion reply. No completion timestamp or result is
fabricated. Recovery never repeats work; a new explicit turn may continue after
the interrupted outcome. Browser disconnects do not cancel backend work.

Step 10's `/api/v1/chat/stream` publishes transient execution progress alongside
this same lifecycle. Progress is not a persistence acknowledgment; terminal saved
outcomes follow the final commit, and failed finalization reports unsaved. Subscriber
disconnect does not cancel the worker. Graceful shutdown drains disconnected stream
workers before releasing ownership. Recovery uses these existing records; there is
no intermediate event journal or progress resume cursor. See [chat-api.md](chat-api.md).

## Restoration and submission identity

```python
from app.sessions import execute_session_request

result = execute_session_request(
    "local-chat", "Just check the sentiment of this I am happy", turn_id="one-operation"
)
```

Python callers may supply a nonblank turn ID of at most 128 characters. Reusing
the same ID/chat/exact message returns the saved outcome without provider/tool calls,
including after process restart. Reusing it with different content/chat conflicts.
Running/interrupted IDs conflict without execution. Without an ID, each call creates
a new UUID and executes a new turn, preserving existing callers. HTTP now accepts optional `turn_id` and echoes the accepted ID, using this same
replay contract; submissions without IDs retain their previous behavior. No automatic retries.

Reads and context restoration never execute requests. Finalized assistant JSON,
successful observations, failed/partial/clarification statuses, and application-owned
demo markers become ordered `HumanMessage`/`AIMessage` pairs. Interrupted turns get
a factual error pair. Corrupt saved outcomes block execution instead of being silently
dropped. Different chats remain isolated, same-chat execution is serialized, and
full history is retained without truncation or context summarization. Model reference
resolution is not guaranteed, and large histories can exhaust provider context.

The existing Python `clear_session_history` function transactionally deletes a
chat's turns, resets its title, and clears its snapshot only after commit. It retains
metadata and sequence allocation. A failed clear keeps saved context; an unsaved
running marker cannot be cleared. Clearing removes prior submission-ID records too,
so duplicate protection applies while records are retained. No HTTP delete/clear
endpoint or navigation control is added. Process-local history from versions before
this change is not migrated automatically.

## HTTP storage failures and verification

Execution's existing HTTP 200/503 rules remain. Storage failures return HTTP 503
with `detail.code="chat_persistence"`, a sanitized message, and
`detail.outcome="not_started"` or `"unsaved"`. An unfinished chat returns HTTP 409.
The client displays fixed storage-specific wording without raw server details or
retrying. Existing HTTP request bodies remain compatible; responses add the accepted turn ID.

Offline checks use temporary databases and scripted providers: fresh-process
context restoration, abrupt exit/unknown recovery, second-process exclusion,
duplicate/conflicting IDs, concurrency, retained workflow and agent traces/demo
markers, write-commit rollback, corrupt reads, durable/failed clearing, unsupported
schemas, input rejection, and sanitized HTTP/client failures. Existing integration
tests cover real local tools and follow-ups. Counts and browser evidence are recorded
in `REWORK.md`; scripted checks do not establish live model quality or delivery.
