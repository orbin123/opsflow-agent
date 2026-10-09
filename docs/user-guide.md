# Docs

OpsFlow helps you analyze English text, find fictional employee policies,
summarize information, prepare email drafts and schedule one-time reminders. Write an ordinary-English request
in **Message OpsFlow**, then press **Send**. Quotes, command prefixes and colons
are optional. Include the text or facts you want the tool to use.

## Sentiment

Use sentiment analysis to describe the tone of supplied English text. Include
the whole statement so negation and punctuation retain their meaning.

**Demo prompt:**

> Just check the sentiment of this I am happy

Expect a positive, neutral or negative label and a brief explanation. Expand
Activity for the selected source and exact VADER scores. A label describes the
text; it does not establish what its author feels. Short, sarcastic or mixed
statements can be difficult to interpret.

## Keywords

Supply a passage to find up to five ranked phrases.

**Demo prompt:**

> Find keywords in this The server failed after the deployment

Expect phrases with relevance scores. Lower YAKE scores indicate greater
relevance, rather than greater confidence. Activity retains the full-precision
results. Very short or punctuation-only text may contain no useful candidates.

## Fictional policy lookup

Ask a complete employee-policy question. These policies are fictional demo data,
not your employer's rules.

**Demo prompt:**

> What is the remote work policy?

Expect an explanation of a matching demo policy, or a request to clarify when
the question is ambiguous or unsupported. Activity retains the exact policy
result. A match may not answer every detail: OpsFlow should acknowledge missing
facts. A policy answer does not require an email recipient.

## Summaries

Include the source text and ask for a summary.

**Demo prompt:**

> Summarize this update: The deployment failed on Tuesday. The team rolled back the release. Service was restored at 10 am.

Expect a concise summary and any key points returned by the tool. Check the
summary against the original facts before relying on it; model-generated wording
can omit or misinterpret details. Exact tool output remains in Activity.

## Email drafts

Provide the intended recipient, factual content and writing instructions such
as tone. The recipient may be a name; confirm their address yourself before sending.

**Demo prompt:**

> Draft a short professional email to Alex saying that the deployment failed on Tuesday, the team rolled back the release, and service was restored at 10 am.

Expect an intended recipient, subject and body, followed by separate review and
sending actions. This creates a draft. OpsFlow chat does not send email. Review
facts, recipient and wording, then copy the draft to your email application.
Drafts using policy information retain the fictional-demo qualification.

## Reminder requests

Ask for one task, a date and a clear time. Use today, tomorrow, or a full calendar
date with its year (for example 2026-10-10 or 10 October 2026). Include am/pm or a
24-hour time such as 10:00. An explicit IANA timezone overrides the configured
zone; otherwise OpsFlow uses the configured zone, defaulting to Asia/Kolkata.

**Demo prompt:**

> Remind me tomorrow at 10 am in Asia/Kolkata to review the deployment report.

Expect a scheduling acknowledgement containing the saved task and the exact due
date, time, UTC offset and timezone. Tomorrow means the next calendar day in the
selected zone, resolved at the start of the submitted turn. Missing or ambiguous
details require clarification; reply in the same chat. A clarification follow-up
resolves relative dates at the start of that follow-up, so use a full date when
continuing on another day. Past times, ambiguous numeric dates, timezone
abbreviations and unsupported date phrases require a clearer future time. A DST
clock overlap requires a confirmed UTC offset; a skipped local time needs a new time.

Scheduling stores a reminder; it does not send an email or start the delivery
worker. The separate local worker must be running to submit due reminders to the
configured user's mailbox. Check **Settings → Reminders** for current delivery
state. SMTP acceptance does not establish inbox arrival.

Refresh, restoration and replay of the same submission never schedule it again.
Repeated model calls cannot create a second reminder in that turn. Separate
submissions have separate identities and can create separate reminders; this is
not global duplicate-content detection. If scheduling succeeded before a later
model failure, the reminder remains stored. If the chat outcome could not be
saved, check Reminders before creating another; recovery never automatically retries.
Only one-time creation is supported here; ask for one reminder per turn.
Recurring reminders, cancellation, editing, deletion and manual retry are unavailable.

## Requests with multiple tasks

You can ask for related operations in one request.

**Demo prompt:**

> Analyze the sentiment, extract keywords, summarize this complaint, and draft a professional email to Alex about it: The service failed twice today and I am frustrated.

One agent chooses tools in sequence and can use earlier results for later steps.
Expand Activity to see which operations actually ran. If a later operation fails,
earlier successful results remain saved. The agent has a bounded budget of six
orchestration calls, five tool calls and a soft 120-second limit; a long request
may stop before every operation finishes.

## How execution works

The classifier first estimates the request's intent. The route depends on
confidence, available information and whether the request needs context or
multiple operations. Example prompts do not guarantee a particular route.

- **Direct:** A safely extracted, single-purpose request runs a local deterministic tool.
- **Fixed workflow (`llm_assisted`):** High-confidence sentiment, keyword and FAQ
  requests use language-model extraction, a local tool and a presentation stage.
  Missing information clarifies; contextual or compound requests can pass to the agent.
- **Agent:** A language model chooses tools for contextual, uncertain or multiple-task
  requests. Summaries and drafts use language-model tools. Reminder creation always
  uses the agent, with local validation and storage.

“Single task” describes how many operations you asked for. “Deterministic” and
“agentic” describe how work executes. Local scoring or retrieval can be part of
a workflow that also depends on a language model.

## Activity and saved chats

Your prompt appears above its Activity and answer. During execution, Activity
shows actual classification, routing and model/tool stages. After completion it
collapses; expand it to inspect saved arguments, results, failures and timings.
Activity contains observable work, not private model reasoning.

Use **New chat** for an independent conversation. Select a saved title to return
to its messages and context. **More actions** or right-click lets you rename or
delete a chat; deletion removes its saved messages and Activity after confirmation.
Chats survive refreshes and application restarts. Unsent composer drafts belong
to the current browser session and each chat; they are not permanently saved.

Open **Settings → Docs** to read this guide, then **Return to chat** to continue
with your selected chat and multiline draft. **Settings → Emails** lists retained successful email drafts across saved chats,
newest turns first. Each draft shows its recipient, subject, body, review actions,
save time and originating chat. Expand **Chat context** for its prompting message,
or choose **Open chat** to read the full conversation. Successful drafts remain
available when a later step failed; the source turn's outcome is shown separately.

**Refresh** reads current records without drafting again. Renaming a chat updates
its displayed title, and deleting a chat removes its drafts from this list after
refresh. If records cannot be read, a loading error appears instead of an incomplete
list. An invalid saved draft has an unavailable-record notice. Emails does not send,
edit or export drafts.

**Settings → Reminders** lists stored reminders by due time, earliest first.
Each card shows the saved task, due time in its recorded timezone (including UTC
offset), and current delivery state. Refresh only reads records; it never schedules
or delivers a reminder. Return to chat preserves your selected chat and draft.

Scheduled means awaiting delivery; Submitting means the outcome is pending;
Retry scheduled means the worker recorded a definite pre-submission failure.
SMTP accepted does not confirm inbox arrival. Failed requires intervention;
Unknown has no automatic retry. A due time in the past does not prove delivery.
Loading failures appear explicitly rather than as an empty list.

Reminders have no originating chat link. Deleting a chat does not cancel or delete
its reminders. Creation uses chat; delivery uses the separate worker. This page does not start the worker
or add retry, cancellation, editing or deletion controls.

## Clarification, failures and recovery

If you request a draft without a recipient or facts, OpsFlow asks for the missing
information. Reply in the same chat to supply it. If a policy question is unclear,
make it more specific. Avoid assuming an unsupported fact was found.

Errors and partial failures describe unsuccessful work while retaining available
results. A failed presentation stage can show a factual fallback from a successful
local tool result. Reading Activity or restoring a chat never executes the turn again.

If the model provider temporarily limits an agent request, Activity can show
**Model busy — waiting … seconds**. Leave the turn running: it waits up to 60 seconds
and retries that rejected model request once, without repeating completed tools.
Waits share the turn's existing 120-second budget. Longer limits or unsuccessful
retries still report unfinished work accurately; completion is not guaranteed.

Chat navigation pauses during running work. Settings navigation and submission
also pause while the selected chat has unconfirmed work. If the
connection is interrupted, execution may continue on the backend. Use **Check
saved chat** to read the saved outcome. Recovery does not automatically reconnect,
retry or resubmit. An interrupted or unknown outcome must not be treated as success.

## Current limitations

Chat schedules one-time reminders through the agent. Chat does not send draft
notification emails or start the reminder delivery worker.
A scheduled record is not a sent email, and SMTP acceptance does not prove inbox arrival.

English examples demonstrate the current chat tools. Output quality and
model interpretation can vary. Fictional policies, generated summaries and drafts
need appropriate review. This guide does not promise support for external
recipients, unlimited workflows or automatic delivery.
