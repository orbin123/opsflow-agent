# Local Streamlit console

From the repository root, install `requirements.txt`, then start two terminals:

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```sh
.venv/bin/python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

Open `http://127.0.0.1:8501`. If the backend uses a different port, set
`OPSFLOW_API_URL` in the Streamlit process environment, for example:

```sh
OPSFLOW_API_URL=http://127.0.0.1:8011 .venv/bin/python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

The default API URL is `http://127.0.0.1:8000`. This is a trusted local console;
neither service supplies authentication. Use a single backend process so history
remains coherent. Streamlit's environment setting is separate from backend `.env`
loading. The console uses the create/list/load catalogue APIs and `POST /api/v1/chat`;
it does not run tools itself.

The project sets `client.toolbarMode = "viewer"` using supported Streamlit
configuration. Deploy, rerun, and clear-cache developer actions are absent from
the toolbar/menu; viewer options and runtime Running/Stop feedback remain.
Workspace hides technical session/history details and retains a concise notice
about draft review/sending and unavailable reminder/email execution. Session IDs
remain internal. Configuration can be overridden by environment or CLI settings.

## Conversation and results

Workspace lists saved chats by recent update time. New chat creates a durable empty
chat; the first Send from an empty workspace creates one before submitting. Merely
opening/refreshing the app creates nothing. Titles are literal first-message text,
with native truncation/full-label accessibility, a selected check/tint and update
time in IST. There are no rename/delete/search controls.

The opaque `chat` URL locator selects the saved chat. Refresh, reopening that URL,
and backend/Streamlit restart restore its ordered messages, exact outcomes and
inspector records through GET without resubmission. Without a locator, the latest
chat opens; an empty catalogue shows the welcome view. Unknown, invalid or repeated
locators show recovery and block Send rather than silently select another chat.
An unavailable history load hides previous messages/inspector data and offers
Check saved chat. An unavailable catalogue offers Retry chat list. These controls
only read. Selection uses explicit query-parameter handling because button widgets
cannot bind URLs and automatic selection-widget binding discards invalid locators.

The approved native multiline Message OpsFlow composer and Send preserve unsent
text separately per chat during the current browser session. Text-area edits commit
on blur; navigation saves that committed value before changing chats. Drafts are
not durable across refresh/disconnection/restart. New chats begin with an empty
composer. Native input bounds cap text at 10,000 characters; the application also
checks nonblank/length before queuing and the API validates independently.

Send queues one frozen chat/message/client-generated turn ID. The app renders
Running feedback and disables New chat, chat switching, composer and Send before
making one HTTP submission (210-second socket timeout). It consumes the queue
before HTTP; rerenders, selection, inspector use and reads never repeat it. Outcomes
are restored from saved records, retaining failure/clarification and timing details.
Catalogue/history reads remain uncached so other tabs' saved updates are visible.

Transport/invalid-response failures do not retry. Check saved chat retrieves the
outcome; a saved matching record replaces the local uncertain message. An absent
record leaves completion unknown and Send blocked in that chat; ordinary navigation
to another chat remains possible. A saved running marker locks navigation and
submission and explicitly reports unconfirmed running/unsaved work. Refresh cannot
cancel or reassign it. A known initial persistence failure preserves the draft and
reports no new execution. A final unsaved failure retains its explicit warning and
running marker; backend restart conservatively marks it interrupted. A read then
shows that unknown outcome and permits a new explicit turn with a fresh ID, without
repeating old work. See [chat-persistence.md](chat-persistence.md).

LLM-assisted keywords show the backend introduction followed by a native Phrase/Score
table in YAKE order. Scores display to five decimal places; API/history and the
inspector retain full precision. Raw keyword JSON appears only in the inspector.
A caption explains lower-score relevance; empty results show their reply without
an empty table. Presentation failure still displays the retained keyword table.
Direct responses display structured JSON. LLM-assisted sentiment shows the backend
explanation or factual fallback as plain text and retains the raw VADER result.
Agent responses display the backend's
application-rendered reply as plain text, retaining separate email draft/actions;
supplied text cannot inject HTML or load Markdown images. Demo FAQ results are
explicitly qualified. Clarification questions appear as ordinary assistant replies without an execution
warning banner; their status remains visible in the inspector. Other execution
statuses stay visible: a completed draft is not a
sent email, and chat does not yet create reminders or submit email.

## Inspector

Choose a turn to see its predicted intent, classifier confidence, execution route,
routing reason, agent outcome reason, status, and backend elapsed milliseconds.
Each actual tool step shows its name, arguments, observation, completion/failure,
reason when present and elapsed milliseconds. Values come from validated backend
responses without rounding or recomputation. Total backend time includes session
waiting/history restoration and initial persistence, excluding the final save
transaction and HTTP transport; it need not equal the sum of steps.
No classification/provider substep timings or private reasoning are invented.

When present, the sentiment, keyword, or FAQ workflow stages expander shows backend-reported
extraction, local-tool, and presentation statuses/reasons/timings, including extraction
before agent handoff. The VADER/YAKE/FAQ duration also appears in the tool trace;
these are two records of the same call. The client accepts `llm_assisted` and
retains stage records for both HTTP 200 and HTTP 503 outcomes. The expander labels
source/question extraction and presentation as LLM stages and VADER/YAKE/FAQ as local tool stages.
FAQ workflow assistant turns show the readable reply without a separate demo-policy
warning caption. Exact policy/candidate JSON and demo metadata stay in the inspector,
including retained presentation failures.

REWORK step 3d AppTest checks cover matched FAQ replies, no-match clarification,
retained presentation failures, exact stage labels/timings, HTTP/client/history
preservation, inspector-only policy JSON, and non-executing rerenders. Existing
Streamlit design/layout is retained; no new browser-layout verification in this slice.

HTTP 503 execution payloads retain observations and failed steps. Runtime-detail,
HTTP rejection, connection, invalid-response and wrong-session failures display
safe messages without raw server/transport details. Inspector selection and reruns
do not re-execute requests.

## Styling and verification

Streamlit 1.65.0 is pinned and its native chat/AppTest APIs were checked against
[chat input documentation](https://docs.streamlit.io/develop/api-reference/chat/st.chat_input)
and [AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
Python 3.12.13 and the installed backend dependencies remain compatible.
The documented light terminal palette, type scale, square controls and 2:1 desktop
layout are adapted to Streamlit; panels stack below 768 px. Native Streamlit JSON
syntax coloring/icons remain framework defaults. CSS uses Streamlit test IDs and
must be rechecked when upgrading the pinned version.

The linked Figma file currently exposes only Foundations. The user approved a
console adaptation from that page and [design-system.md](design-system.md), rather
than adding missing Figma pages. VT323 and IBM Plex Mono Regular are bundled from
the Google Fonts repository under their adjacent SIL Open Font License files in
`ui/fonts/`. Fonts are embedded locally; no external font requests are needed.
Streamlit usage statistics are disabled in `.streamlit/config.toml`.

Verification: 18 added checks cover the one-shot client, safe failures, response
preservation, real API/direct-tool UI integration, scripted agent clarification
and follow-up isolation, partial failures, exact display timing, non-executing
reruns, bounds and plain-text rendering. All 670 tests, `pip check` and whitespace
checks pass. Browser verification uses a real local backend/direct sentiment tool.
Desktop (1440 px) and mobile (390 px) checks confirm panel placement, visible focus,
font rendering, caption contrast and no mobile horizontal overflow.
Agent verification uses offline doubles. No live Groq, SMTP/inbox or deployment
verification is claimed.

REWORK step 1 verification (2026-10-07): all 18 existing UI checks, `pip check`,
and whitespace checks pass. A real local direct sentiment request completed.
Browser inspection at 1440 px and 390 px confirmed removed developer/session
copy, no Deploy in toolbar/menu, keyboard sidebar open/close, visible input focus,
mobile panel stacking, and no horizontal overflow. An isolated delayed local HTTP
fixture confirmed Running/Stop feedback, the spinner, disabled submission, and
input recovery after a controlled HTTP 503, with exactly one request logged.
Temporary fixture services were stopped. No new tests, live provider/email calls,
or deployment checks were added; existing LangChain deprecation warnings remain.

REWORK step 2b verification (2026-10-07): all 721 tests, `pip check`, and whitespace
checks pass. AppTest verifies a real saved-classifier/API/client path with scripted
sentiment language stages and local VADER scoring, including plain-text reply,
exact workflow timings, retained HTTP 503 results/history, and rerender non-execution.
Figma inspection was rate-limited; the existing native expander adaptation was
retained. No CSS/layout change, live Groq, or new browser-layout checks.

REWORK step 9 verification (2026-10-08): all 939 tests (17 new navigation checks),
dependency and whitespace checks pass. Final recovery-copy changes passed 88
targeted navigation/UI/storage/catalogue checks. Scripted-provider inline review
on 8505/backend 8016 covered isolated chats/follow-ups, an unsent draft, refresh
during delayed execution, read failure/recovery, unknown links and unchanged
saved turns after backend restart. Desktop 1440 px/mobile 390 px checks confirmed
literal/truncated accessible titles, native keyboard/sidebar behavior, 48 px
targets, visible 2 px focus, stacked panels and no horizontal overflow. Figma
inspection remains rate-limited; the documented-token/native adaptation was
approved. No live model quality, email/reminders, streaming, inline Activity,
Docs or deployment verification; the existing LangChain deprecation remains.
