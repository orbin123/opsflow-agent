# Persistent demo employee workspace

The user approved this bounded addition independently of the rework agenda on
2026-10-09. The local application has one employee workspace, automatically used
by every browser connected to the same backend. It is a fictional demonstration
persona named Sachin Tendulkar, not a claim about the real person's employment.

## Profile and ownership

`GET /api/v1/profile` returns the saved profile: `profile_id: EMP-001`, name
Sachin Tendulkar, role Operations Associate, company OpsFlow Demo Company,
timezone Asia/Kolkata, and `is_demo: true`. There is no profile mutation API.

The profile lives in `OPSFLOW_CHATS_DB` (default `var/chats.sqlite3`), using the
existing single-backend Unix-lock boundary. Schema version 3 transactionally adds
one profile to version 1/2 storage without changing chats, titles, saved turns,
results or drafts. Initial database setup seeds the profile once. Subsequent
reads use the saved row; a missing/invalid profile or storage failure returns a
sanitized HTTP 503, rather than inventing a replacement identity.

All retained and future records in this single workspace belong to EMP-001.
Chat catalogue/create/load/rename responses expose `profile_id`; saved email
projections expose the same identity and inherit their source chat's lifetime.
Reminder catalogue records also expose `profile_id`. This is explicit singleton
workspace ownership, not per-record owner columns, user filtering or access control.
The unchanged reminder database belongs to this workspace as a whole; existing
records acquire this association without modifying their task, due time, timezone,
delivery state, attempts or creation keys. Reminder reads remain strictly read-only
and do not depend on opening the chat database. Deleting a chat leaves the profile
and reminders intact, but still removes its retained email drafts.

Profile GET can initialize/migrate chat storage on first access, like existing
catalogue reads. Subsequent profile reads do not update it. Existing startup
recovery may mark old running turns interrupted; it never repeats their work.
No profile/catalogue read executes an agent/tool, schedules a reminder, starts the
worker or sends email. Existing SMTP configuration remains authoritative; the
profile contains no invented mailbox or credentials.

## Boundaries and next slices

This remains a trusted local application without authentication. One profile does
not provide multiple users, admin roles, cloud synchronization or backups. Durable
records survive refresh/restart only while the same persistent databases remain
available; changing paths or replacing files selects different storage.

This slice does not change browser-state restoration, the UI, policy answers,
agent context, reminder defaults or email delivery. The employee timezone is saved
profile metadata; existing runtime timezone configuration still applies. Subsequent
separately agreed slices can persist last-chat selection/composer text, then display
the profile and supply employee context to the agent. Policy facts and personal
employee data such as leave balances must not be invented from this profile.

## Verification

Automated checks cover stable repeated/fresh-process profile reads, legacy migration
with exact saved turn/title preservation, shared catalogue identity, unchanged
reminder bytes/delivery state, sanitized failures without reseeding, transactional
migration rollback and the read-only API boundary. Existing chat, email, reminder
and UI regression checks remain applicable. Browser verification is recorded in
the change record; no live provider or email execution is needed for this slice.
