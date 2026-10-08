# OpsFlow-Agent

An operations copilot using TF-IDF + a calibrated linear SVM for intent routing, LangChain/Groq for conversational tool orchestration, FastAPI, Streamlit, and SQLite reminders.

The local Streamlit chat/inspector runs with `streamlit run streamlit_app.py` and
uses `/api/v1/chat`; see `docs/streamlit-console.md` for configuration and verification.

Approved REWORK step 7 stores chat history in separate local SQLite storage and
restores context without reexecution. See `docs/chat-persistence.md` for the
single-backend Unix-lock boundary, interrupted recovery, and explicit unsaved
failures. Python and HTTP turn IDs prevent duplicates while records are retained.
Approved step 8 exposes create/list/load catalogue APIs and client helpers; reads
never execute work. See `docs/chat-api.md`. Approved step 9 adds Workspace New chat,
literal titled selection, `chat` URL restoration and a per-chat browser-session
multiline draft composer. Running/unsaved work locks navigation and submission;
recovery controls only read. See `docs/streamlit-console.md`. The separate inspector
remains through step 10; live events/inline Activity and Docs are later slices.

The natural-language sentiment workflow is documented in `docs/sentiment-workflow.md`.
Approved REWORK step 2b connects it behind the classifier using the `llm_assisted`
route, with existing chat HTTP status rules and retained workflow/tool records.

The natural-language keyword workflow is documented in `docs/keyword-workflow.md`.
Approved REWORK step 3b connects it behind the classifier using `llm_assisted`,
with the same HTTP status and retained-record contracts as sentiment. Keyword
assistant turns show a brief introduction and a native phrase/score table;
full-precision raw results remain in the inspector.

The natural-language FAQ workflow is documented in `docs/faq-workflow.md`.
Approved REWORK step 3c extracts a complete question, calls unchanged local retrieval,
and explains only matched fictional policies while retaining exact answers. Ambiguous/
no-match results clarify without presentation; missing policy details may also clarify.
Approved REWORK step 3d connects high-confidence FAQ chat requests using `llm_assisted`,
with the same HTTP status/history/trace rules. Replies stay readable; exact policy JSON
remains in the inspector. Lower-confidence requests use the agent and its pure FAQ tool.
Policy answers do not need recipients; ask for those only for requested email drafts.
The FAQ-only endpoint keeps its existing wholly local contract.

## Read Before Working

- `REWORK.md`: active implementation agenda until its rework steps and completion criteria are verified.
- `docs/agents_doc.md`: brief record of completed changes and the next step.
- `skills/karpathy-guidelines/SKILL.md`: follow the supplied Karpathy development guidelines. If missing, ask before development.

## Active Agenda — Rework First

- As agreed on 2026-10-07, pause the original `docs/PLAN.md` agenda until `REWORK.md` is complete. Do not consult the original plan or an `agenda.txt` file to decide, order, or add work during the rework.
- Choose the next bounded step from `REWORK.md`, discuss its contract and proportional verification with the user, then implement the agreed slice. Creating the rework plan does not authorize implementing all its steps at once.
- Use current code and feature documentation to understand existing behavior; the paused plan is historical context only and cannot expand rework scope. Existing collaboration, design, routing, and side-effect rules still apply.
- Track rework decisions, status, and verification in `REWORK.md` and `docs/agents_doc.md`. Keep the pause notice in `docs/PLAN.md`; its original checklist remains paused.
- Only after all rework completion criteria are verified, record the handover in these files, reconcile the original plan with the resulting implementation, and resume `docs/PLAN.md` for remaining project work.

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
- Immediately update the active plan when decisions, scope, architecture, or status change: `REWORK.md` during rework, then `docs/PLAN.md` after the recorded handover. Add a brief completed-change entry to `docs/agents_doc.md`. Update this file too if project facts or working rules change. Include those updates in the same logical change.
- Keep the plan and record concise and adaptable. Use ✅ only for verified completed work and ⏳ for the active discussion or step.

## Project Boundaries

- Direct execution requires a high-confidence, single-purpose deterministic request with safely extracted arguments. Sentiment analyzes the supplied text, not the instruction wrapper.
- Reminder requests always go through the agent, regardless of classifier confidence. Compound, uncertain, LLM-dependent, or context-dependent requests also use the agent, except the approved fixed sentiment/keyword/FAQ workflows: high-confidence predictions enter `llm_assisted` extraction/local tool/presentation, with missing/ambiguous input clarifying and contextual/compound extraction abstention handing off to the agent. FAQ similarity does not prove every question detail is covered; retain the exact policy and acknowledge missing facts.
- Version one includes emails to the configured user with separate draft content and action instructions, plus scheduled reminder emails. External-recipient email sending is a separate scope decision.
- A stored reminder requires a due-time delivery worker; a draft or scheduled record must not be reported as a sent email. Track side effects and failures accurately and prevent duplicate delivery.
- The local reminder worker uses a Unix file lock beside the canonical SQLite path. Use cooperating workers on one local filesystem; network storage, multiple hosts, hard-link aliases, and deleting/replacing an active lock file are unsupported. SMTP acceptance does not prove inbox arrival. Unfinished/unknown attempts never retry automatically; only definite transient pre-submission failures use the persisted three-attempt budget.
- Preserve session history for both routes. Display observable tool execution traces and timings without exposing private model reasoning.
- Verify dependency/API/model compatibility before implementation. Keep credentials out of Git and logs; use controlled email test doubles for automated checks.
