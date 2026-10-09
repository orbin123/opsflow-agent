# Reminder Scheduling

`app/tools/reminders.py` provides a standalone deterministic `schedule_reminder` tool. It stores a one-time reminder in SQLite and returns `scheduled`. Run the separate `app.reminder_worker` process to submit due reminders to the configured user's Gmail mailbox. Scheduling does not itself send email. Saved chat turns now connect natural-language one-time creation through the agent; see the chat contract below.

## Input and output

```python
from datetime import datetime
from app.tools.reminders import schedule_reminder

record = schedule_reminder(
    task="Review the SLA",
    local_due=datetime(2026, 10, 7, 9, 0),
    creation_key="caller-operation-123",
    timezone="Asia/Kolkata",
)
```

The date in this example must still be in the future when executed.

| Argument | Contract |
| --- | --- |
| `task` | Nonblank string, at most 1,000 characters before normalization; surrounding whitespace is removed. |
| `local_due` | A resolved `datetime` without `tzinfo`, representing the local calendar time. No natural-language strings. |
| `creation_key` | Caller-generated nonblank opaque string, at most 128 characters, preserved exactly; reuse for retries of the same operation. |
| `timezone` | IANA zone name, at most 128 characters; omitted uses `OPSFLOW_TIMEZONE`, then `Asia/Kolkata` if unset. Invalid/unavailable zones fail. |
| `utc_offset_minutes` | Optional integer strictly between -1,440 and 1,440, which must match the zone at the local time. Required to select an ambiguous DST occurrence. |
| `db_path` | Optional persistent file path; omitted uses `OPSFLOW_REMINDERS_DB`, then `var/reminders.sqlite3`. Relative paths are rooted at the repository. |
| `now` | Optional aware current instant for controlled testing; production callers omit it. |

The immutable `ReminderRecord` contains `reminder_id` (UUID), `creation_key`, normalized `task`, aware UTC `due_at` and `created_at`, original `timezone`, and `status="scheduled"`. This is a scheduling acknowledgement, not a delivery report. Newly created database records start as `pending`; the worker owns subsequent delivery states. Creation retries preserve existing delivery state and attempt history. The configured recipient and SMTP credentials are not part of the scheduling contract or database.

The chat adapter resolves supported literal date/time phrases against the submitted turn instant and clarifies ambiguous/missing details. An explicit request timezone overrides the configured default. Local times are checked through UTC round trips using [Python zoneinfo](https://docs.python.org/3.12/library/zoneinfo.html). A nonexistent DST time fails; an ambiguous time requires a confirmed offset. A `fold` flag alone is not accepted as confirmation. The machine timezone is never a fallback. New reminders due at or before the current instant fail.

## Persistence and retries of creation

SQLite stores UTC timestamps in fixed microsecond ISO format and retains the original zone for display. The configured/default database is separate from tracked source; `.gitignore` excludes `var/` and SQLite database/sidecar files. Credentials remain in the existing ignored `.env`. Repository-root `.env` loading preserves existing environment values.

A unique creation key and an explicit `BEGIN IMMEDIATE` transaction serialize lookup and insertion, including concurrent callers. A successful return occurs only after commit. See [SQLite transactions](https://www.sqlite.org/lang_transaction.html). A repeated key with identical normalized task, UTC due time, and zone returns the original ID and creation timestamp, even after the reminder becomes overdue. Changing those fields under the same key raises `ValueError`; use a new key for an intentional new reminder. Two distinct keys can create identical reminders. This prevents duplicate creation only when the caller reuses the key; it does not detect repeated user intent or prevent duplicate email delivery.

Invalid arguments raise `TypeError` or sanitized `ValueError` without inserting a record. Database/filesystem failures raise sanitized `ReminderPersistenceError`; raw database errors and paths are not returned. No success is returned after a failed commit. Parent directories are created on a valid storage attempt. Each call closes its database connection; records survive process restarts.

## Due-time email worker

Use the existing [Gmail configuration](email-notifications.md). Start the worker separately from FastAPI:

```bash
.venv/bin/python -m app.reminder_worker
```

`--db-path /absolute/path/reminders.sqlite3` overrides the configured database. `--once` processes eligible records and exits without waiting for future due times. The normal loop polls every five seconds after processing its current batch. Pending overdue records are eligible immediately after downtime. This is local polling, not an exact-time inbox-delivery promise. SMTP keeps the existing verified TLS settings, configured-user-only envelope, and 30-second socket-operation timeout; it has no total-call deadline.

The worker holds an exclusive, nonblocking [Unix advisory file lock](https://docs.python.org/3.12/library/fcntl.html) at `<canonical-database-path>.lock` throughout ownership. A second cooperating worker fails before recovery or SMTP. Use one local filesystem and the same canonical database path for all workers; do not use hard-link aliases, delete/replace the lock file while workers may run, or use network/multi-host storage. Current macOS behavior is verified; planned Linux/Docker deployment remains unverified. Windows support is outside this slice. No lock timeout reclaims a running worker's attempts.

Worker initialization adds `reminder_attempts` without altering existing reminder rows. Each attempt stores its UUID, reminder ID, attempt number, unique Message-ID, UTC start/end timestamps, outcome/reason, and any next retry time. The worker commits a conditional transition to `submitting` and an attempt marker before calling SMTP outside the transaction. A failed claim/commit prevents submission. Outcomes update the attempt and reminder in one transaction. IDs and sanitized outcome/state/reason are printed as JSON after a completed processing batch; timestamps remain available in SQLite. No task content, recipient address, credentials, raw SMTP reply, or model reasoning is logged.

| Reminder state | Meaning and next action |
| --- | --- |
| `pending` | Stored and awaiting due time. |
| `submitting` | Durable attempt marker; the active worker owns the outcome. |
| `retry` | A definite transient pre-submission failure; await persisted retry time. |
| `accepted` | SMTP acknowledged acceptance. Terminal; does not prove inbox arrival. |
| `failed` | Definite failure needing intervention, or retry budget exhausted. Terminal. |
| `unknown` | Acceptance cannot be established or ruled out. Terminal; no automatic retry. |

Only definite pre-submission timeouts, connection errors, and disconnects are retryable. Allow at most three total attempts: the second becomes eligible one minute after the first failed attempt ends, and the third five minutes after the second ends. Attempt counts and eligibility persist across restarts. Configuration/authentication failures, explicit SMTP rejection (including temporary rejection codes), TLS errors, and unexpected pre-submission integration errors do not automatically retry. A timeout/disconnect once submission begins is `unknown`, regardless of remaining budget. Message-ID identifies an attempt and provides no Gmail deduplication.

After acquiring exclusive ownership, startup turns unfinished attempts/reminders into `unknown` with attempt reason `interrupted`. The interrupted attempt's `ended_at` is the recovery instant, not an observed SMTP completion time. This includes a crash after the claim but before SMTP and a crash after acceptance before the outcome commit. Avoiding resubmission can cost delivery; exactly-once delivery is not guaranteed. Already recorded `accepted`/`failed`/`unknown` records are not submitted on restart. If an outcome cannot be persisted, the worker stops processing and cannot resume within that same context; its durable unfinished marker remains for conservative recovery. `SIGINT`/`SIGTERM` request shutdown after the current attempt's outcome is persisted, before claiming another. An abrupt process exit releases ownership but leaves its marker for startup recovery.

There is no automatic reconciliation or manual reset command in this slice. Review unknown/failed outcomes before deciding on any later explicit new attempt. Do not report a terminal failure or unknown as sent, and do not blindly create a new reminder to retry an unknown submission.

## Verification

46 offline cases use temporary database files and controlled current instants. They cover Kolkata conversion, an explicit timezone override, timezone-data failure, DST gaps and both fold occurrences, past/exact/future boundaries, validation limits, unchanged/conflicting creation retries, distinct keys, concurrent identical-key scheduling, recovery in a fresh process after the due time, configured/relative paths, and sanitized database/commit/filesystem failures. No SMTP or Groq call is made. Full-suite results are recorded in the plan and change record.

Worker verification uses 34 additional offline cases: due/overdue processing, committed attempt visibility before SMTP, retry timing/budget across restarts, terminal outcomes, SMTP-stage classification, configured-recipient and original-zone message content, second-process exclusion, actual process exit, post-acceptance interruption, claim/outcome/recovery database failures, unchanged state on creation retry, and graceful SIGTERM. Existing scheduling and draft-notification tests remain regression checks. No real SMTP connection/authentication/submission or inbox arrival has been verified.

## Read-only catalogue and page

GET `/api/v1/reminders` returns one JSON object per stored reminder with
`reminder_id`, literal `task`, aware `due_at` and `created_at`, original `timezone`,
and actual persisted `state`. Ordering is due instant ascending, then ID.
Creation keys, SMTP credentials and attempt Message-IDs are not exposed.
Reads open the configured database in SQLite `mode=ro` and do not create storage,
migrate schema, acquire worker ownership, recover attempts or submit email.
A missing database returns `[]`; existing invalid/inaccessible storage or invalid
records returns HTTP 503 with a sanitized detail, never a partial list.
The scheduling-only schema is supported before worker initialization.

Settings → Reminders displays these records with due times in their recorded
timezone and UTC offset. Refresh/Return are read-only and preserve selected chat
and composer drafts. SMTP accepted does not mean inbox delivery; pending,
submitting, retry, failed and unknown remain distinct. No chat links are shown
because stored reminders have no chat association. Chat schedules one-time reminders through the agent. Worker
startup, cancellation, deletion and manual retry remain outside this page slice.

## Chat creation contract

`app.chat_reminders` supplies the agent's `schedule_reminder` schema and adapter.
The agent extracts literal task, date, time, optional IANA timezone and optional
confirmed UTC offset from the current user message, or the immediately preceding
clarification chain. Application code checks those phrases against user messages,
resolves today/tomorrow in the chosen zone or an explicit ISO/full month-name date
with year, and validates wall time through the existing scheduler. Times accept
am/pm, HH:MM, noon and midnight. Unsupported/ambiguous dates, missing details,
invalid zones, DST gaps/overlaps and past instants clarify without inserting.
This validation checks literal provenance, not complete semantic interpretation;
language-model selection and authorization interpretation still have limitations.

`execute_session_request` supplies an application-owned creation key derived from
its durable turn ID, scoped through a ContextVar. The model cannot supply keys,
database paths, test clocks or delivery recipients. One successful reminder per
turn is enforced; a second proposed scheduling call stops with the first result
retained. Existing SQLite key conflicts and concurrent insert protection remain.
Standalone `run_agent`/`execute_request` calls without a durable turn context
cannot schedule; use the saved-chat entry point or existing structured scheduler.
HTTP, SSE and history carry JSON-safe task/due/zone/ID observations, with the
creation key omitted. Application-generated acknowledgements and later failure
replies retain the actual scheduling result, regardless of final model wording.
Scheduling acknowledgement is historical, not a current delivery-state report.
Use GET `/api/v1/reminders` for actual persisted states.

Chat and reminder commits are separate. If reminder insertion succeeds but chat
finalization fails or the process stops, the reminder may exist while the chat
outcome is unsaved/interrupted. Existing recovery blocks replay and never retries
that turn. Inspect the read-only Reminders page before any intentional new request.
Turn-key protection is per operation, not global duplicate-content detection;
new submissions can create equal reminders. Reminder records and keys survive
chat deletion, which does not cancel delivery or delete reminder storage.
The worker, attempt policy, SMTP transport and catalogue schema are unchanged.
