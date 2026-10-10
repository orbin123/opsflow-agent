# OpsFlow-Agent

An operations copilot using TF-IDF + a calibrated linear SVM for intent routing, LangChain/Groq for conversational tool orchestration, FastAPI, Streamlit, and SQLite reminders.

The local Streamlit chat with per-turn Activity runs with `streamlit run streamlit_app.py` and
uses `/api/v1/chat/stream`; see `docs/streamlit-console.md` for configuration and verification.

The backend stores chat history in separate local SQLite storage and
restores context without reexecution. See `docs/chat-persistence.md` for the
single-backend Unix-lock boundary, interrupted recovery, and explicit unsaved
failures. Python and HTTP turn IDs prevent duplicates while records are retained.
The backend exposes create/list/load catalogue APIs and client helpers; reads
never execute work. See `docs/chat-api.md`. Workspace supports New chat,
literal titled selection, `chat` URL restoration and a per-chat browser-session
multiline draft composer. Running/unsaved work locks navigation and submission;
recovery controls only read. See `docs/streamlit-console.md`. Completed execution
details appear between each right-aligned prompt and left-aligned answer in a
vertically sequential, left-aligned Activity panel. The running panel shows actual
live stage events before the saved answer. The sidebar provides bottom-left
Settings with a read-only Docs guide and saved-work page options.
Docs/return preserves chat selection and browser-session drafts without executing
work; pending/running/unsaved work blocks page entry. See `docs/user-guide.md`.
The app provides a read-only Emails page across retained chat drafts,
including successful drafts from compound/partially failed turns. Existing GET APIs
provide records; Refresh/Open chat never execute drafting. Saved actions and demo
qualifications remain separate. The app provides a read-only Reminders page
and GET catalogue over existing
local storage, showing literal tasks, recorded-zone due times and actual delivery
states. SMTP acceptance does not imply inbox arrival. Reads never start the worker
or schedule/send/retry work; existing records have no source-chat association.
Approved chat reminder creation uses the agent with literal date/time extraction,
local resolution, turn-owned creation keys and the existing scheduler. Only one
one-time reminder per turn is supported. Clarification does not insert; saved
replay/recovery never repeats creation. The delivery worker remains separate and
chat never starts it. Reminder records survive chat deletion; see docs/reminders.md.

The approved Workspace addition provides persistent Rename/Delete through a
themed right-click/More actions menu. Custom titles survive the first message;
deletion requires a named confirmation and removes saved chat records/context.
Running/unsaved work blocks management in both the UI and backend. Catalogue
mutations never execute a chat turn; see `docs/chat-api.md` and `docs/design-system.md`.

The backend provides `POST /api/v1/chat/stream` SSE for actual backend
classification/routing, workflow stages and agent model/tool activity. Progress is
transient; saved terminal outcomes follow SQLite finalization. Disconnect does not
cancel execution; graceful shutdown drains stream workers before releasing storage.
Recovery/replay never repeats work. See `docs/chat-api.md` for event fields and
transport/status boundaries. Streamlit uses the SSE endpoint for one-shot
submission and GET for restoration.
The UI uses collapsed per-turn Activity and nested workflow/tool sections with
exact saved records. Correlated live events show observable stages in a native
running panel before the saved outcome.
Disconnect/rerun recovery only reads; it never automatically reconnects or resubmits.
Live progress is transient; final/restored details use saved records.

The natural-language sentiment workflow is documented in `docs/sentiment-workflow.md`.
It runs behind the classifier using the `llm_assisted`
route, with existing chat HTTP status rules and retained workflow/tool records.
The UI shows direct/fixed-workflow sentiment labels beneath the
existing reply, keeps exact scores/JSON in Activity, and offers natural-English
welcome examples. Remaining answer presentation stays a separately agreed slice.

The natural-language keyword workflow is documented in `docs/keyword-workflow.md`.
It runs behind the classifier using `llm_assisted`,
with the same HTTP status and retained-record contracts as sentiment. Keyword
assistant turns show a brief introduction and a native phrase/score table;
full-precision raw results remain in Activity.

The natural-language FAQ workflow is documented in `docs/faq-workflow.md`.
It extracts a complete question, calls unchanged local retrieval,
and explains only matched fictional policies while retaining exact answers. Ambiguous/
no-match results clarify without presentation; missing policy details may also clarify.
High-confidence FAQ chat requests use `llm_assisted`,
with the same HTTP status/history/trace rules. Replies stay readable; exact policy JSON
remains in Activity. Lower-confidence requests use the agent and its pure FAQ tool.
Policy answers do not need recipients; ask for those only for requested email drafts.
The FAQ-only endpoint keeps its existing wholly local contract.

The user-approved persistent demo employee workspace is implemented.
Schema version 3 stores one fictional Sachin Tendulkar profile (EMP-001)
in the chat database. All retained/future chats, saved drafts and reminders belong
to this singleton workspace; catalogue records expose its profile ID. GET
`/api/v1/profile` reads saved identity without executing work. No login, multiple
users, agent personalization or durable composer/last-selection restoration is
included in this first slice. See `docs/employee-profile.md`.

The approved local monitoring slice provides generated HTTP request IDs, sanitized
JSON request/task/tool/persistence logs, Prometheus `/metrics`, and a provisioned
local Grafana dashboard. HTTP/SSE transport status, actual task execution and
persistence outcomes remain separate; saved replay/recovery never counts as new
work. Metrics are process-scoped and reset on restart. The monitoring Compose
stack does not start the app or reminder worker. See `docs/monitoring.md`.

The user approved a protected temporary Render Free demo. Its Docker launcher
runs one loopback-only API, Streamlit and a password-protected public nginx proxy;
it never starts the reminder worker. Cloud SQLite records are disposable and local
records/SMTP credentials are excluded. A native demo notice makes storage loss
and disabled delivery explicit. Free hosting cannot extend Render's default
shutdown window. See `docs/render-demo.md` for packaging and verification limits.

Dockerization and hosted deployment are complete: `Dockerfile` uses pinned Python
3.12, runtime dependencies and the unprivileged `opsflow` user;
`deploy/run_demo.py` supervises API/Streamlit/nginx, and `.dockerignore` excludes
credentials and local storage. Render builds directly from the connected
GitHub repository. The live demo is https://opsflow-temporary-demo.onrender.com
(`srv-db4gtd3tqb8s73f7mrrg`, Free, Singapore, one instance). Hosted Docker build,
HTTP/WebSocket authentication, chat/Activity and refresh restoration were verified.
The repository is now public. The last recorded live commit is `ed56040`.
GitHub Actions CI runs on PRs/pushes to `main`, with offline tests,
dependency checks, Linux AMD64 Docker build and container authentication smoke
checks. Main protection requires genuine CI/DCO checks, including admins. Both
`render.yaml` and the live service target `main` with `checksPass`; failed CI was
verified to block PR merge. Hosted CI verifies all 1,190 tests, the AMD64 image
and authentication smoke checks. The first automatic deployment awaits approved
merge and verification. See `docs/cicd.md`.

## Read Before Working

- `docs/package-structure.md`: application package responsibilities and launch commands.

- `docs/PLAN.md`: active implementation agenda for remaining project work.
- `docs/agents_doc.md`: brief record of completed changes and the next step.
- `skills/karpathy-guidelines/SKILL.md`: follow the supplied Karpathy development guidelines. If missing, ask before development.

## Active Agenda

- Use `docs/PLAN.md` to choose and order remaining project work. The user resumed this agenda on 2026-10-09.
- Discuss the next bounded step, its contract and proportional verification with the user, then implement the agreed slice. The plan does not authorize implementing every item at once.
- Use current code and feature documentation to understand existing behavior and avoid repeating completed work. Existing collaboration, design, routing and side-effect rules still apply.
- Track decisions, scope, status and verification in `docs/PLAN.md` and `docs/agents_doc.md`. Do not use `agenda.txt` as an alternative agenda.

## Frontend Design

- Whenever a request involves frontend design or UI implementation, read and follow `docs/design-system.md`. Use its linked OpsFlow Figma file as the visual source of truth; keep implementation decisions consistent with its tokens, typography, layout, and component states. If the requested UI needs a design-system rule that is not documented, identify that gap and discuss it before expanding the system.

## Collaboration and Coding Rules

- Suggest and discuss each implementation step before coding. Explain the problem, proposed change, inputs/outputs, and how we will verify it. Once the user agrees, complete that bounded step without repeatedly requesting permission.
- Take the slow approach throughout this project so the user understands the code. Prefer one small, explainable step at a time. If asked to implement too much at once, remind the user of this agreement and propose a smaller first slice.
- Make each development change a logically scoped commit and PR with a clear purpose and relevant verification. Keep unrelated work separate; preserve existing user changes. Use logical job-based branch and PR names such as `fix/...` or `feature/...`, not `codex/...`. Agree on the slice before implementation and prepare its reviewable diff before publication.
- Do not add `Co-authored-by`, ChatGPT, Codex, or any other non-user author attribution to commits, merge commits, PR descriptions, or PR details. Authorship should remain only the user's GitHub account.
- Before opening or updating a PR, confirm the DCO check will pass for every commit. Use only the user's GitHub account details for any required `Signed-off-by` line.
- State assumptions and ask about material uncertainties before implementing. Do not silently change scope or choose external services.
- Write the simplest code that solves the agreed problem. Avoid speculative features, unnecessary abstractions, unrelated refactoring, and cosmetic changes outside the task.
- Verify behavior appropriate to the change. Report what was checked and what remains unverified; never claim delivery, execution, or testing that did not happen.
- For changes affecting chat or Streamlit behavior, after automated tests pass, start the local app and exercise the changed flow in the inline browser. Then leave the app open there so the user can independently verify it before merge or direct push to `main`; wait for the user's confirmation before either. Record any unavailable checks and observed limits clearly.
- Keep tests proportional to the agreed slice and discuss the proposed test scope before coding. Cover core successful behavior, meaningful boundaries, realistic failures, and regressions; prioritize routing mistakes, incorrect payload extraction, side effects, and accurate failure reporting. Use representative cases for equivalent inputs and justify exhaustive cases when they protect a real contract. Avoid tests that merely mirror the implementation or repeat coverage without catching a distinct failure.
- Immediately update `docs/PLAN.md` when decisions, scope, architecture, or status change. Add a brief completed-change entry to `docs/agents_doc.md`. Update this file too if project facts or working rules change. Include those updates in the same logical change.
- Keep the plan and record concise and adaptable. Use ✅ only for verified completed work and ⏳ for the active discussion or step.

## Project Boundaries

- Direct execution requires a high-confidence, single-purpose deterministic request with safely extracted arguments. Sentiment analyzes the supplied text, not the instruction wrapper.
- Reminder requests always go through the agent, regardless of classifier confidence. Compound, uncertain, LLM-dependent, or context-dependent requests also use the agent, except the approved fixed sentiment/keyword/FAQ workflows: high-confidence predictions enter `llm_assisted` extraction/local tool/presentation, with missing/ambiguous input clarifying and contextual/compound extraction abstention handing off to the agent. FAQ similarity does not prove every question detail is covered; retain the exact policy and acknowledge missing facts.
- Version one includes emails to the configured user with separate draft content and action instructions, plus scheduled reminder emails. External-recipient email sending is a separate scope decision.
- A stored reminder requires a due-time delivery worker; a draft or scheduled record must not be reported as a sent email. Track side effects and failures accurately and prevent duplicate delivery.
- The local reminder worker uses a Unix file lock beside the canonical SQLite path. Use cooperating workers on one local filesystem; network storage, multiple hosts, hard-link aliases, and deleting/replacing an active lock file are unsupported. SMTP acceptance does not prove inbox arrival. Unfinished/unknown attempts never retry automatically; only definite transient pre-submission failures use the persisted three-attempt budget.
- Preserve session history for both routes. Display observable tool execution traces and timings without exposing private model reasoning.
- Verify dependency/API/model compatibility before implementation. Keep credentials out of Git and logs; use controlled email test doubles for automated checks.
