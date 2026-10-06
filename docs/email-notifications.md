# Gmail Draft Notifications

`app/tools/email_notifications.py` provides `send_draft_notification(draft: EmailDraftResult) -> NotificationResult`. It submits one plain-text notification containing an existing draft and its review/send instructions to the configured user's mailbox. It does not draft text, call Groq, send to the draft's intended recipient, or implement agent/API/UI wiring or reminders.

## Local configuration

Keep these settings in the Git-ignored repository-root `.env`, or supply them through environment variables. Environment values take precedence; loading happens only on a valid call.

```dotenv
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
OPSFLOW_USER_EMAIL=your-address@gmail.com
OPSFLOW_TIMEZONE=Asia/Kolkata
```

`SMTP_USERNAME` is the authenticated sender and envelope/header `From`. `OPSFLOW_USER_EMAIL` is the single allowed envelope/header `To`. Both must be bare ASCII mailboxes (no display names, address lists, or whitespace), at most 254 characters. Syntax validation does not verify account existence or ownership. `SMTP_PASSWORD` is a 16-character alphanumeric Google App Password; grouped display spaces are removed before authentication. Do not use a regular Google password or put credentials in Git/chat. [Google describes App Passwords and account eligibility](https://support.google.com/accounts/answer/185833).

The transport is fixed to `smtp.gmail.com:465` using `smtplib.SMTP_SSL` with default certificate/hostname verification and a 30-second blocking-operation timeout. This is a socket-operation bound, not a total-call deadline. Gmail supports encrypted SMTP; [Google documents its SMTP service](https://developers.google.com/workspace/gmail/imap/imap-smtp), and [Python 3.12 documents SMTP_SSL](https://docs.python.org/3.12/library/smtplib.html). No new dependencies, protocol debug output, external tracing, or content/credential logging.

Asia/Kolkata is the agreed future reminder default. Draft notifications have no due time and perform no timezone conversion. Reminder scheduling and aware UTC storage remain a separate slice.

## Input and message contract

Require an `EmailDraftResult`; wrong types raise `TypeError`. Revalidate its subject/body and require a nonblank intended recipient of at most 320 characters without CR/LF, plus the drafting tool's two fixed action instructions. Invalid input raises a sanitized `ValueError` before configuration or network access, including mutated model instances. The utility consumes an existing draft; it does not regenerate it.

The notification subject is fixed: `OpsFlow: email draft ready for review`. The plain-text body contains:

- **Email draft:** intended recipient, draft subject, and draft body.
- **What you should do:** review/replace placeholders, then send or forward using your email client.

The intended recipient is body text only. Explicit `from_addr` and `to_addrs` bind the SMTP envelope to configuration. No CC/BCC or reply-to. Header-like or HTML-like source text remains plain body content and cannot introduce delivery recipients. A local UUID-based Message-ID and UTC Date header identify the submission.

## Submission outcomes

`NotificationResult` contains `status`, `reason`, `message_id`, and `retryable` (default false):

| Status | Meaning |
| --- | --- |
| `accepted` | SMTP submission returned without recipient refusals; `reason` is null. Does not prove inbox arrival. |
| `failed` | No submission acceptance: invalid configuration, authentication failure, pre-submission transport failure, or explicit sender/recipient/message rejection. |
| `unknown` | An error occurred after submission began without a conclusive acceptance/rejection. The server may have accepted the message. |

Stable reasons are `configuration`, `authentication`, `rejected`, `timeout`, and `provider_unavailable`. Raw SMTP replies, addresses, content, and credentials are excluded from results. The submission phase begins immediately before `send_message`; transport errors within it are conservatively uncertain because exact server acceptance cannot be inferred. Definite SMTP rejection remains failed. Socket cleanup is best effort and cannot overwrite an observed outcome; closing avoids relying on QUIT acknowledgement.

`retryable` is true only for definite pre-submission transient timeouts/connection failures/disconnects. It is false for uncertain outcomes, configuration/authentication/rejection failures, TLS errors, and unexpected integration errors. This is metadata for the caller; the transport never retries itself.

Each call makes at most one submission attempt. There are no automatic retries in this utility. Repeating a draft-notification call creates a new Message-ID and may duplicate delivery; Message-ID does not provide deduplication. The [reminder worker](reminders.md) now owns durable attempt tracking, bounded safe retries, and conservative crash recovery for reminders. `send_reminder_notification` uses that worker's persisted attempt UUID as Message-ID, validates that the reminder is due, and sends a fixed plain-text reminder to the configured user through the same transport. Draft-notification body/envelope behavior is unchanged. Manual reconciliation and provider idempotency remain outside the current slice.

## Verification

Automated tests replace SMTP with controlled doubles and forbid socket connections. They verify configured-user-only delivery, body sections, header-like source isolation, TLS verification/settings, input/configuration non-execution, explicit refusals, authentication/transport failures, uncertain submission outcomes, sanitized results, one attempt, and cleanup preserving outcomes. Existing deterministic routing remains unchanged.

No live SMTP connection, authentication, or email submission was performed. The local environment's configuration format was checked without displaying values; this does not establish credential validity or delivery. A manual test message requires separate authorization.
