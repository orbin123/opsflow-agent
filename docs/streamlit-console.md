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
loading. The console only calls `POST /api/v1/chat`; it does not run tools itself.

The project sets `client.toolbarMode = "viewer"` using supported Streamlit
configuration. Deploy, rerun, and clear-cache developer actions are absent from
the toolbar/menu; viewer options and runtime Running/Stop feedback remain.
Workspace hides technical session/history details and retains a concise notice
about draft review/sending and unavailable reminder/email execution. Session IDs
remain internal. Configuration can be overridden by environment or CLI settings.

## Conversation and results

A random session ID is created once per Streamlit browser session and reused for
follow-ups. UI turns survive script reruns; refreshing/disconnecting can start a
new session, while backend history resets on process restart. No durable UI history,
clear/history endpoint or automatic eviction is added. See [chat-api.md](chat-api.md).

Messages are preserved exactly and checked for nonblank text and the API's 10,000
character bound. The input disables during submission (`submit_mode="disable"`).
Each turn makes one HTTP request with a 210-second socket timeout, allowing the
bounded agent's provider calls time to finish. There are no automatic retries;
transport errors may leave an unknown backend outcome. Submitted turns remain
visible with that warning. Resubmitting manually executes another turn.

Direct responses display structured JSON. Agent responses display the backend's
application-rendered reply as plain text, retaining separate email draft/actions;
supplied text cannot inject HTML or load Markdown images. Demo FAQ results are
explicitly qualified. Execution status stays visible: a completed draft is not a
sent email, and chat does not yet create reminders or submit email.

## Inspector

Choose a turn to see its predicted intent, classifier confidence, execution route,
routing reason, agent outcome reason, status, and backend elapsed milliseconds.
Each actual tool step shows its name, arguments, observation, completion/failure,
reason when present and elapsed milliseconds. Values come from validated backend
responses without rounding or recomputation. Total backend time includes session
waiting/history and excludes HTTP transport; it need not equal the sum of steps.
No classification/provider substep timings or private reasoning are invented.

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
