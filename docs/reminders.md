# Reminder Scheduling

`app/tools/reminders.py` provides a standalone deterministic `schedule_reminder` tool. It stores a one-time reminder in SQLite and returns `scheduled`. It does not parse natural language, send email, run a worker, or integrate the agent/API/UI. Until the worker slice is implemented, scheduled reminders will not produce notifications.

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

The immutable `ReminderRecord` contains `reminder_id` (UUID), `creation_key`, normalized `task`, aware UTC `due_at` and `created_at`, original `timezone`, and `status="scheduled"`. The database state is `pending`. The configured recipient and SMTP credentials are not part of the scheduling contract or database.

The future agent owns resolving relative dates against the current instant and clarifying ambiguous/missing details. An explicit request timezone overrides the configured default. Local times are checked through UTC round trips using [Python zoneinfo](https://docs.python.org/3.12/library/zoneinfo.html). A nonexistent DST time fails; an ambiguous time requires a confirmed offset. A `fold` flag alone is not accepted as confirmation. The machine timezone is never a fallback. New reminders due at or before the current instant fail.

## Persistence and retries of creation

SQLite stores UTC timestamps in fixed microsecond ISO format and retains the original zone for display. The configured/default database is separate from tracked source; `.gitignore` excludes `var/` and SQLite database/sidecar files. Credentials remain in the existing ignored `.env`. Repository-root `.env` loading preserves existing environment values.

A unique creation key and an explicit `BEGIN IMMEDIATE` transaction serialize lookup and insertion, including concurrent callers. A successful return occurs only after commit. See [SQLite transactions](https://www.sqlite.org/lang_transaction.html). A repeated key with identical normalized task, UTC due time, and zone returns the original ID and creation timestamp, even after the reminder becomes overdue. Changing those fields under the same key raises `ValueError`; use a new key for an intentional new reminder. Two distinct keys can create identical reminders. This prevents duplicate creation only when the caller reuses the key; it does not detect repeated user intent or prevent duplicate email delivery.

Invalid arguments raise `TypeError` or sanitized `ValueError` without inserting a record. Database/filesystem failures raise sanitized `ReminderPersistenceError`; raw database errors and paths are not returned. No success is returned after a failed commit. Parent directories are created on a valid storage attempt. Each call closes its database connection; records survive process restarts. There is no schema for delivery attempts yet, worker recovery, automatic retry, or manual reconciliation.

## Verification

46 offline cases use temporary database files and controlled current instants. They cover Kolkata conversion, an explicit timezone override, timezone-data failure, DST gaps and both fold occurrences, past/exact/future boundaries, validation limits, unchanged/conflicting creation retries, distinct keys, concurrent identical-key scheduling, recovery in a fresh process after the due time, configured/relative paths, and sanitized database/commit/filesystem failures. No SMTP or Groq call is made. Full-suite results are recorded in the plan and change record.

Delivery, worker ownership, retry timing, and unknown SMTP outcomes remain the next separately agreed slice. Persistence alone does not establish email delivery or exactly-once submission.
