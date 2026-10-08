# Persistent chat and navigation contract

REWORK step 6, recorded 2026-10-08. The user selected **one local user** and
**disabled navigation while a turn runs**. This document defines the target for
steps 7–9 and the restoration constraints for steps 10–14. Step 7 now implements
the storage/session portion; see [chat-persistence.md](chat-persistence.md).
Steps 8–9 implement catalogue endpoints, HTTP submission IDs and Workspace
navigation/restoration. Each implementation slice needs its
own discussion and proportional verification.

## Ownership and storage

- One trusted local user, one backend process, and a local filesystem. Every
  browser tab using that backend sees the same chat catalogue. There are no
  separate browser owners, accounts, folders, or projects. IDs identify records;
  they do not authorize access. Keep the service local; hosted/multi-user access
  requires a separate authentication and ownership contract before exposure.
- Reuse Python/SQLite and the repository's storage conventions, with a **separate
  chat database**: proposed `OPSFLOW_CHATS_DB`, default `var/chats.sqlite3`, rooted
  at the repository for relative paths. Do not alter reminder tables, database
  settings, delivery state, or worker locks. No reminder/email integration.
- Chat records contain private source text and results. Keep the database and
  sidecars ignored by Git; do not log record contents, credentials, filesystem
  paths, private reasoning, or raw provider responses. Local filesystem access
  is the access boundary; encryption/backups and network storage are separate scope.
- Initialize a versioned chat schema transactionally. Unsupported versions or
  storage failures fail with sanitized messages, without wiping records or
  silently substituting a fresh in-memory conversation.

## Saved records and ordering

The initial schema needs two logical tables, with foreign keys enabled and one
transaction per record transition. Exact SQL is reviewed in step 7.

| Record | Required fields and meaning |
| --- | --- |
| Chat | Stable opaque `session_id`, `title`, UTC `created_at`, UTC `updated_at`. The identifier continues to be the existing chat request's `session_id`. |
| Turn | Stable opaque `turn_id`, chat ID, per-chat monotonic `sequence`, exact original `message`, UTC `started_at`, nullable UTC `finished_at`, lifecycle `state`, nullable execution JSON, nullable sanitized failure reason/reply, and the application-owned demo-policy marker. Unique chat/sequence and turn ID constraints prevent duplicate records. |

Use UUID identifiers within the existing 128-character session-ID bound. A turn
is one user message plus its assistant outcome, rather than two independently
appended records. Sequence, not timestamp or list position, determines history
order. Catalogue order is descending `updated_at`, with ID as a stable tie-breaker.
Creation, accepting a turn, and finalizing it update chat metadata; reading,
selecting, expanding activity, and opening Docs do not.

Save every current execution field: status, predicted intent, confidence, route,
reason, result, reply, agent reason, tool `trace`, `workflow_trace`, and elapsed
time. Preserve exact tool inputs/results, numeric precision, failures, successful
observations preceding a failure, fictional-policy qualification, and draft/action
separation. Clarification and partial failure are valid saved outcomes. Runtime
unavailability uses an explicit sanitized failure record when no execution payload
exists; do not invent classification, route, results, or duration.

Persist the timing returned by the session entry point, including lock/history
handling, as the public turn elapsed value. Preserve individual backend stage/tool
timings unchanged; transport/render time is not execution time. At step 6, history
stored inner runtime timing, so step 7 needed to explicitly resolve this
difference rather than silently presenting two conflicting totals.

Step 7 resolution: freeze one elapsed value before the final save and return/save
that exact value. It includes restoration and the initial commit, and excludes
the final save transaction. No restoration timing is substituted for saved execution.

No expiry, automatic deletion, history truncation, or LLM summarization is added.
Restore all finalized user/assistant pairs in order using the existing assistant
JSON representation and trusted `opsflow_demo_policy` metadata. The new message is
supplied once. Failed and partial turns remain context with their actual status.
An interrupted turn contributes its user message and a factual interrupted outcome,
without invented tool results. This preserves follow-up semantics; it cannot
guarantee model reference resolution. Full history can exceed memory/provider
context limits; report the existing sanitized failure instead of silently dropping
history. Context budgeting remains a separate decision.

## Execution, persistence failures, and interruption

Lifecycle state is separate from the existing execution `status`:

| State | Meaning and recovery |
| --- | --- |
| `running` | The accepted user message and execution marker committed before classification/provider/tool calls. There may be no observed result yet. |
| `finished` | The final execution payload or sanitized runtime failure committed. Execution status still distinguishes completion, clarification, partial failure, and error. |
| `interrupted` | Startup found an unfinished turn left by the previous backend process. Completion is unknown; no automatic retry. |

Serialize execution and persistence per chat; different chats retain independent
context. A failed initial commit prevents execution. Commit the final outcome
before reporting it as saved or using it as authoritative context. A failed final
commit must disclose that the outcome was not saved, retain the running marker,
and block further submissions in that chat until the persistence uncertainty is
resolved. Do not carry on with divergent memory/disk histories or rerun the tool
to repair persistence. If results can be returned to the current caller, label
them explicitly as unsaved; they cannot be promised after refresh.

Single-process startup recovery marks prior running records interrupted before
accepting new turns. Browser disconnect/timeout alone does **not** mark a still
active backend turn interrupted or cancel it. Retrieve its state: it may still
be running or have a committed final result. Unknown completion stays explicit.
HTTP GET, restoration, reconnecting, and Streamlit rerenders never classify,
invoke a provider/tool, or resubmit a stored message. Exactly-once execution across
a crash is not promised; unfinished work is never automatically repeated.

Give persistent submissions a client-generated `turn_id`, retained for the one
submission attempt. Under a per-chat lock, an identical ID/message is a lookup of
the existing turn, not another execution; conflicting reuse returns HTTP 409.
Neither a transport failure nor an HTTP 503 triggers an automatic retry. An
intentional new submission uses a new ID even when its text matches an old turn.
Step 7 implements this storage boundary; step 8 reviews its API compatibility.

## API and client contract for step 8

Catalogue endpoints (implemented in step 8):

| Request | Response and boundary |
| --- | --- |
| `POST /api/v1/chats`, empty JSON object | HTTP 201 with an empty saved chat, generated ID, title `New chat`, and creation/update timestamps. No execution or history clearing. |
| `GET /api/v1/chats` | HTTP 200 with ordered chat metadata; empty catalogue is an empty list. No message/result contents in the list. Initial local scope returns the whole catalogue. |
| `GET /api/v1/chats/{session_id}` | HTTP 200 with metadata and ordered turn records, including lifecycle, finalized execution/failure, and retained observable activity. Never executes work. Unknown ID is HTTP 404. |

Keep `POST /api/v1/chat` and its `session_id`/`message` names. Add an optional
`turn_id` for persistent clients and echo the accepted ID. Requests without it
remain one new execution per POST, preserving existing callers; they lack the new
deduplication protection. Existing caller-owned session IDs may create their chat
on the first valid submission, preserving the current entry-point contract.
Retrieval of an unknown ID never creates it. Reject invalid bodies before record
creation/execution. Restore state remains available through GET after a lost reply.

Preserve HTTP 200 for completion/clarification, HTTP 503 for execution error or
partial failure, and HTTP 422 validation. Sanitized storage failures use HTTP 503
with an explicit unsaved/unknown indication distinct from an execution payload.
Repeated submission of a running/interrupted ID returns HTTP 409 with its lifecycle
and no execution; a finished ID returns its saved outcome with the original status
semantics. Exact response models and failure envelopes are reviewed in step 8.
The FAQ-only endpoint retains its wholly local, stateless contract.

## Browser identity and navigation — implemented in step 9

- Use an opaque `chat` URL query parameter for the selected saved chat. This
  survives refresh/reopening that URL and backend/Streamlit restart; it is an
  internal locator, not a credential. Do not display IDs in Workspace labels or
  normal conversation content. Keep source text/results out of URLs.
- Without a selection, load the most recently updated chat; with no chats, show
  the empty welcome view. Do not create a chat merely by loading or refreshing.
  New chat creates a durable empty chat and selects its returned ID. A first
  submission from the empty welcome view creates one chat before executing.
- An explicitly unknown/invalid locator shows a recovery message and the chat
  list; do not silently execute in another chat. A read failure shows a safe error
  with a read-only retry control. Never show another chat's cached turns under
  the requested selection or treat retrieval failure as empty history.
- Initial title is `New chat`. On first accepted message, collapse whitespace and
  take its first 60 Unicode characters, adding an ellipsis only if truncated.
  Render as literal text; do not call a model to generate titles. Duplicate titles
  are allowed; use update time for orientation. Renaming/deleting/search are later
  optional work.
- Selecting a chat loads its messages, outcomes, and activity as one consistent
  snapshot; subsequent submissions use that chat's restored context only.
  Unsaved composer text belongs to its chat during the browser session. It is
  not promised after refresh; clear the composer for a new chat.
- While the backend turn is known to be running, disable New chat, chat switching,
  and repeat submission; show a textual Running state. After a timeout, recover
  through reads. Refresh or a manually changed URL cannot cancel/reassign the
  running turn. Backend per-chat serialization remains necessary for other tabs.
  Interrupted work allows an explicit new turn with a new ID, with the unknown
  outcome visible. Storage uncertainty blocks continuation as described above.

## Sidebar and activity interaction specification

The proposed interaction patterns below adapt the existing
[design tokens](design-system.md); they are not new implemented Figma components.
Figma metadata inspection on 2026-10-08 was blocked by the Starter tool-call limit.
Visual approval and alignment with any available Figma components remain part of
steps 9 and 11; do not mark visual verification complete from this contract.

- Workspace contains New chat followed by the selectable titled chat list.
  No session IDs, paths, backend settings, or storage descriptions. Docs remains
  a lower-sidebar entry for step 14; its return preserves the selection and chat.
- Reuse square geometry, 48 px controls (at least 44 px targets), IBM Plex Mono
  labels, VT323 short action labels, existing surfaces, and a 2 px visible focus
  outline. Selected chat uses action tint plus a visible selection indicator;
  selection, running, disabled, and failure states have text/accessibility labels.
  Long titles truncate visually while their full literal text remains accessible.
- Desktop uses the existing rail proportions; mobile uses the native collapsible
  sidebar, stacked panels, and full-width New chat. Selection is keyboard operable.
  Native widgets are preferred; concrete widget/API choices await implementation.
- Keep the inspector through steps 7–10. Step 11 moves saved details into a
  collapsed Activity expander in their assistant turn, with expandable tool
  inputs/results and truthful status/timing labels. The final reply remains
  outside Activity. No private reasoning or fabricated progress.
- Step 13 updates the same activity from actual backend events. Expansion and
  rerendering only change presentation. Restored turns display saved observations;
  unfinished stages show unknown/interrupted rather than fabricated completion.

## Contract review and later verification

Step 6 review compared this specification with `app/sessions.py`, `app/api/chat.py`,
`app/ui_client.py`, `streamlit_app.py`, and the memory/API/reminder/design documents:

| Scenario | Required result; implementation verification belongs to the indicated slice |
| --- | --- |
| Two chats and direct/workflow-to-agent follow-up | Isolated ordered histories, exact results and demo markers; steps 7–9. |
| Refresh/backend restart | Same saved chat and outcomes; read-only restoration; interrupted unfinished turns; steps 7–9. |
| Clarification/runtime failure/presentation partial failure | Actual statuses, safe replies and retained successful observations; steps 7–8. |
| Initial/final storage failure | No execution before initial commit; disclosed unsaved outcome and blocked divergent continuation; step 7. |
| Timeout/repeated ID/rerender | Read recovery or lookup, no repeat execution; steps 7–10. |
| Unknown chat/empty list/create/load | Explicit recovery and stable catalogue behavior; steps 8–9. |
| Switching during execution/other browser tab | Disabled ordinary navigation, backend serialization and correct turn association; steps 7–9. |
| Long title/keyboard/mobile/activity expansion | Accessible existing tokens and read-only display; steps 9, 11, 13. |

Step 6's evidence is documentation review, not runtime or browser evidence. No dependency,
provider, SMTP, reminder, deployment, framework, routing, or context-limit changes
were made. Step 10 events is the next bounded discussion; this document does not authorize
implementing every later slice.


Step 9 implementation uses native title buttons and a multiline composer/Send,
approved by the user. Explicit URL handling retains unknown/invalid-link recovery
because Streamlit bound selection widgets discard unknown values. Unsaved drafts
are per-chat browser-session state, committed on text-area blur; refresh may lose
them. Recovery reads never retry submissions. Unknown outcomes absent from storage
remain blocked in that chat; another chat may be selected. Existing inspector stays
through step 10. See [streamlit-console.md](streamlit-console.md) for implemented
states and verification limits.
