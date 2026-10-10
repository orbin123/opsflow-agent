# OpsFlow product and functionality audit

## 1. Product purpose and current scope

OpsFlow is a local English-language operations copilot. Users discuss text, analyze
sentiment, extract keywords, look up fictional employee policies, summarize notes,
compose email drafts, and schedule one-time reminders. Saved chats provide context
for follow-ups; Activity explains observable execution and outcomes.

**Assessment:** Core features are connected and the existing automated suite passes.
This is a trusted local workspace, not a production multi-user service. Email drafting
does not send email. Reminder delivery requires a separately running worker.

Audit date: **9 October 2026**. Code baseline: `main`, commit `9c2fcb6`.
“Verified” below means checked within the evidence in section 7; it does not promise
correct results for every possible natural-language request.

## 2. How a request works

`streamlit_app.py` sends a message through `app/ui/ui_client.py` and `app/ui/ui_stream.py`
to FastAPI's `POST /api/v1/chat/stream`. `app/chat/sessions.py` saves a running turn and
restores its chat context. `app/core/runtime.py` classifies the request once, then routes it:

- **LLM-assisted:** High-confidence sentiment, keyword, or FAQ requests use a fixed
  model extraction → local tool → model explanation workflow. Missing input clarifies;
  compound/context-dependent input can hand off to the agent.
- **Agent:** Other requests use one Groq-backed agent to choose tools sequentially.
  Summaries, drafts, reminders, and conversational follow-ups use this route.
- **Direct:** The separate FAQ API can retrieve locally without invoking the agent.
  The current chat path uses the assisted workflows rather than the older direct
  sentiment/keyword routing helpers.

Backend events feed live Activity. SQLite finalization precedes the terminal saved
outcome. Streamlit subsequently reads saved history to display the answer and details.
The stream reports execution stages, not token-by-token answer generation.

## 3. Feature-by-feature behavior

All rows have code connections and automated coverage; fresh live checks are narrower.

| Feature | How it works and what the user receives | Important boundary |
|---|---|---|
| Sentiment | Extracts supplied text; VADER returns positive/neutral/negative and scores. Assisted chat shows explanation and label; Activity keeps exact scores. | English; analyzes source text, not the instruction wrapper. |
| Keywords | YAKE returns up to five phrases of one to three words. Assisted chat shows a Phrase/Score table. | Lower score means greater relevance, not confidence; no candidates is valid. |
| Policy FAQ | TF-IDF/cosine retrieval selects from 25 fictional policies with 75 phrasings; chat explains matched answers. | Ambiguous/no-match or missing policy facts require clarification. These are demo policies. |
| Summaries | Groq produces a bounded paragraph and up to five key points from supplied facts. A single-summary turn has dedicated readable rendering. | Schema validation cannot prove factual fidelity. |
| Email drafts | Groq generates subject/body; code preserves recipient and appends separate review/send instructions. | No sending from chat; missing recipient/source should clarify. |
| Reminders | Agent supplies literal task/date/time phrases; Python resolves the zone and stores one future, one-time reminder per turn. | Today/tomorrow/full dates and clear times; default Asia/Kolkata. No recurrence/edit/cancel UI; chat never starts delivery. |
| Compound requests | One agent executes requested operations in dependency order and retains successful tool results if later work fails. | Five-tool/six-orchestration-call limits; completeness and tool choice still depend on the model. |
| Follow-ups | Saved user messages and structured outcomes become agent context for clarifications and revisions. | Restoring context does not reexecute work; ambiguous references should clarify. |
| Workspace | New chat, literal titles, URL selection, persistent rename and named delete confirmation. | Active/unsaved work blocks management; deletion removes chat history, not reminders. |
| Composer | Multiline field and fixed Send footer; per-chat unfinished drafts survive navigation within the browser session. | Composer drafts are not durable SQLite chat records. |
| Activity/recovery | Live stages, saved tool inputs/results/timings, and explicit errors/partial outcomes; “Check saved chat” reads records. | Disconnect does not cancel backend work or automatically resubmit it. |
| Settings/Docs | Loads the local user guide and returns to the selected chat without executing examples. | Settings currently provides page navigation, not a general configuration editor. |
| Emails page | Projects successful draft observations across saved chats, including partially failed compound turns; Refresh/Open chat read records. | Read-only; deleting the source chat removes its retained draft observations. |
| Reminders page | Reads stored tasks, due times in their recorded zone, and actual delivery states. | Read-only; existing reminders have no source-chat association. |

## 4. Frontend–backend connectivity

| Backend entry point | Frontend/client connection | Assessment |
|---|---|---|
| `POST /api/v1/chat/stream` | Send → `submit_chat(..., on_event=...)` → SSE client | Connected; live Activity and saved outcomes covered. |
| `POST /api/v1/chat` | Nonstreaming `submit_chat` client path | Implemented/tested; normal Streamlit Send uses SSE. |
| `POST/GET /api/v1/chats` | New chat and Workspace catalogue | Connected. |
| `GET /api/v1/chats/{id}` | Selection, restoration, recovery and Emails projection | Connected; reads never execute tools. |
| `PATCH/DELETE /api/v1/chats/{id}` | More actions/right-click → rename/delete dialogs | Connected with backend active-work checks. |
| `GET /api/v1/reminders` | Settings → Reminders → `list_reminders` | Connected and read-only. |
| `POST /api/v1/faq` | Standalone API consumer | Intentionally separate; chat calls retrieval through its runtime. |
| `GET /health` | Operational HTTP check | No dedicated UI; reports liveness, not Groq/SMTP/storage readiness. |
| `send_draft_notification` | Python utility only | No chat/API/UI send action; a built capability, not a user-facing integration. |
| Reminder worker | Separate `app.reminders.reminder_worker` process → Gmail transport | Connected to reminder storage; intentionally independent of chat. |

There is no separate Emails HTTP endpoint: the frontend reads existing chat APIs and
uses `app/ui/email_catalogue.py`. Sentiment, keywords, summaries and drafts similarly
run behind chat rather than dedicated public endpoints.

## 5. Packages and Python responsibilities

Exact direct pins live in [requirements.txt](../requirements.txt).

| Package/component | Actual project use |
|---|---|
| `streamlit` | UI widgets, session state, page rendering, AppTest and the v2 chat-action menu. |
| `fastapi`, `uvicorn[standard]` | Validated HTTP routes, SSE responses, server lifecycle and local serving. |
| `scikit-learn`, `joblib` | TF-IDF/calibrated linear SVM classifier; TF-IDF FAQ retrieval; trusted saved-model loading. |
| `vaderSentiment`, `yake` | Local sentiment scoring and keyword extraction; neither tool needs Groq. |
| `langchain-groq`, `langchain-core`, `groq` | ChatGroq model calls, message/tool schemas, conversation records and provider error handling. The sequential agent loop is application code. |
| `pydantic`, `python-dotenv` | Validate API/tool/model outputs; load local configuration without overriding existing environment values. |
| `langsmith` | Explicitly disables tracing around execution/model paths; not an enabled product analytics feature. |
| `pytest`, `httpx2` | Tests, FastAPI client support and HTTP integration checks. The UI client uses Python `urllib`; Groq also brings an `httpx` dependency used in error doubles. |
| `pandas`, `matplotlib`, `nbclient`, `ipykernel` | Dataset/model evaluation and notebook execution, rather than core chat orchestration. |
| Python standard library | `sqlite3` stores chats/reminders; `zoneinfo`/`datetime` resolve due times; `fcntl` and threading locks control ownership/concurrency; `asyncio` supports streams; `smtplib`/`ssl`/`email` submit notifications. |

Model-using paths default to `openai/gpt-oss-20b`, permit the configured 120b variant,
and require `GROQ_API_KEY`. Source text/context can reach Groq; the complete chat
experience is therefore not wholly offline even when its underlying analysis tool is local.

## 6. Data, reliability and side effects

The saved classifier uses 1,000 synthetic examples across eight labels. Its recorded
200-example test split achieved **88% accuracy**, **0.8813 macro F1**. The selected
0.71 routing threshold yielded 100% precision at 23.5% coverage for the original
direct-route evaluation. Those historical metrics do not evaluate today's complete
LLM-assisted workflows or establish real-world accuracy.

Chats and reminders use separate local SQLite files. Chat turn IDs prevent duplicate
execution while records remain retained; reminder creation keys prevent repeated
creation within the supported turn contract. Restarts recover unfinished chat work
as interrupted without replay. An executed-but-unsaved outcome remains explicit.
There is no cross-database transaction making chat finalization and scheduling atomic.

Agent execution has a soft 120-second budget, five tools and six orchestration calls.
Each explicitly rate-limited model request may retry once after a valid wait of at
most 60 seconds within that budget; tools and HTTP turns are not retried. Fixed
workflows/standalone writing do not receive that agent-specific waiting policy.

The separate worker claims due reminders and records attempts. Only definite transient
pre-submission failures receive the persisted three-attempt retry budget. Interrupted
or uncertain submissions become unknown and are not automatically resent. SMTP
acceptance does not establish inbox arrival; exactly-once delivery is not guaranteed.

Storage supports one trusted local backend and cooperating local workers with Unix
locks. No user authentication/ownership layer, automatic history eviction, backup,
or encryption is implemented. This limits public hosting and multi-host deployment.

## 7. Verification and evidence

Fresh checks on the audit baseline:

- `.venv/bin/python -m pytest -q`: **1,153 passed**, one LangChain history deprecation
  warning, 80.63 seconds. Coverage spans routing, extraction, tools, API/SSE, storage,
  recovery, reminder attempts, catalogue operations and Streamlit AppTest flows.
- `.venv/bin/python -m pip check`: **No broken requirements found.**
- Code review traced registered APIs, UI clients/rendering, workflows, tools, storage,
  agent bounds and notification connections. Documentation was treated as supporting
  evidence rather than proof that code works.
- Inline-browser review of the existing app on 8512 confirmed restored clarification
  and scheduled-reminder answers, saved Activity, the Reminders page's two pending
  records with Asia/Kolkata times, and the Emails empty state.

Automated model/SMTP doubles verify application contracts, not live provider quality
or actual email arrival. Earlier live demos/browser checks are recorded in
[agents_doc.md](agents_doc.md) and [REWORK.md](../REWORK.md); they are historical
evidence, not freshly repeated tests. This audit did not create a new reminder, start
the worker, send email, retrain the model, or freshly exercise every feature in a
browser. Live Groq fidelity, SMTP/inbox delivery, full mobile/accessibility review
and production deployment remain unverified by this audit.

## 8. Findings and next steps

**No failing automated functionality was found.** Core advertised chat features have
frontend/backend connections. This supports the current local implementation, not
an unconditional claim that everything works for all inputs.

| Priority | Finding | Recommended bounded follow-up |
|---|---|---|
| High | Actual reminder email delivery and inbox arrival are unverified; draft sending is backend-only. | Separately agree on controlled live delivery verification and any draft-send integration. |
| High | Model extraction, factual grounding and complete compound execution remain quality risks; historical demos exposed unsupported wording and reminder normalization clarification. | Evaluate representative live requests and source fidelity, beyond scripted schema tests. |
| Medium | Dedicated summary/draft rendering only covers successful single-tool turns; broader capability/multi-tool presentation remains deferred in rework. | Finish the agreed remaining step 12b presentation before handover. |
| Medium | Historical status notes conflict with later completion entries: old baseline says reminders are disconnected; some “pending merge” notes survive later merge records. | Reconcile the current status summary at handover while preserving dated history. |
| Medium | Local unauthenticated storage and unbounded retained context limit production use and may exhaust model capacity. | Discuss ownership, retention and deployment requirements before expanding beyond local use. |
| Low | `InMemoryChatMessageHistory` emits a deprecation warning; older direct-routing helpers remain alongside assisted chat. | Plan a proportional compatibility/usage review; no runtime break was observed. |

This audit does not close rework step 15, resume the paused original plan, or authorize
feature changes. Detailed contracts remain in the linked feature documentation.
