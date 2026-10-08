# OpsFlow Rework Plan

Agreed direction: 2026-10-07. `REWORK.md` is the active agenda until the completion
criteria below are verified. The original `docs/PLAN.md` agenda is paused; do not
use it or `agenda.txt` to decide or order work. Resume the original plan only
after the recorded rework handover.

**Status:** Steps 1 and 2 (2a/2b) implemented and verified within their recorded limits.
Keyword steps 3a/3b and FAQ steps 3c/3d are implemented and verified within the
recorded offline and limited live-review bounds. Step 4 is implemented and verified
with offline/scripted-browser checks and merged in PR #27 after user approval.
Step 5 is verified within the offline/scripted-browser limits below; user approved
merging PR #28 on 2026-10-08. Step 6's persistence/navigation contract is
recorded and reviewed. Step 7 storage/restoration is merged in PR #30 after user
approval, with its step 6 dependency PR #29 also merged. Step 8 catalogue APIs and
HTTP submission IDs and step 9 Workspace navigation/restoration are implemented
and verified within the offline/scripted-browser limits below. User approved merging
both on 2026-10-08; PRs #31/#32 are merged. Step 10 backend events are implemented
and verified within the recorded offline/scripted-browser limits; step 11 completed
inline details and step 13 live formation are implemented and verified within the
recorded offline/scripted-browser limits. Step 12a sentiment/onboarding is implemented
and verified within the recorded limits; step 12b and steps 14 onward remain pending.
Workflow modules now live under `app/workflows/` for package organization.
**Next:** ⏳ Step 12b remaining answer presentation discussion; steps 12a and 13
await user review before merge. Step 11 is merged in PR #34.
FAQ PRs #25/#26 and the workflow package organization are merged into `main`. Keyword workflow/integration/presentation are
merged in PR #24.

## Intended User Experience

OpsFlow should feel like a conversational workspace. Users write ordinary
English, receive readable answers, and can inspect actual execution activity
without leaving the conversation.

- Keep the OpsFlow name/logo. Remove the redundant `OPSFLOW / OPERATIONS CONSOLE`
  caption and user-facing Deploy entry and its deployment flow.
- Workspace contains New chat and a list of chat sessions, like ChatGPT. Each
  chat has independent history and context that can be restored and continued.
  "Sections" means sessions: no folders, project spaces, or additional grouping.
- Hide session IDs, filesystem locations, backend configuration, and storage
  mechanics from ordinary Workspace navigation. Keep identifiers internally.
- Chats survive refreshes and application restarts. Preserve messages, results,
  clarification/failure states, and observable execution details.
- Replace the separate execution inspector with compact, collapsible activity
  inside the corresponding assistant turn. Classification, routing, tool inputs,
  results, failures, and timings become visible as execution happens.
- Show readable final answers outside the activity panel. Technical details are
  available on expansion; they should not dominate the conversation.
- Accept natural-English requests without mandatory quotes, colons, prefixes,
  or code syntax. Extract the intended source text without losing its meaning.
- A request containing three, four, or more operations uses one agent and a
  multi-step workflow. It does not require multiple separate agents.
- Provide a Docs entry near the bottom of the sidebar with thorough usage,
  examples, expected outputs, limitations, and explanations of execution types.

## Current Baseline

These findings come from code/document inspection, not new runtime verification:

- `streamlit_app.py` uses one temporary browser-session ID and an adjacent
  inspector. The welcome example encourages `Sentiment: "I am happy"` syntax;
  structured results are displayed as JSON.
- `app/ui_client.py` and `app/api/chat.py` exchange one final response after
  execution. There is no live execution-event stream.
- `app/sessions.py` retains direct and agent outcomes in process-local history.
  It has no durable chat catalogue or history retrieval API; backend restart
  loses chat history. SQLite reminder persistence is separate.
- Direct sentiment and keyword extraction require recognized instructions with
  double-quoted source text. FAQ routing accepts some ordinary policy questions.
  Uncertain extraction falls back to the agent rather than rejecting all chat.
- The agent accepts ordinary English and uses five registered tools, with
  sequential tool observations and bounded execution. Current limits are six
  orchestration calls, five tool calls, and a soft 120-second budget.
- Sentiment, keywords, and FAQ are the three direct deterministic capabilities.
  Summarization and email drafting use the agent/LLM tools. Reminder storage and
  delivery utilities exist, but reminder/email execution is not connected to chat.
- The existing design reference specifies the light terminal palette, typography,
  geometry, and states. The connected Figma file currently exposes Foundations;
  chat-list navigation and inline activity patterns need explicit design discussion.

## Working Rules and Boundaries

Before implementing each numbered step, discuss its problem, input/output
contract, proposed changes, material uncertainties, and proportional tests.
Then complete only that agreed slice as one logical commit/PR, with user-only
authorship and DCO sign-off. Split a step further if its contract becomes too large.
Update this file and `docs/agents_doc.md` with the actual outcome and verification.
Use checked boxes or ✅ only after verification; use ⏳ for the active discussion.

Follow `AGENTS.md`, `skills/karpathy-guidelines/SKILL.md`, the Streamlit skill,
and `docs/design-system.md` for their applicable work. Discuss missing design
patterns before extending the design system. Verify installed framework/provider
compatibility during each implementation slice.

For changes affecting chat or Streamlit behavior, automated tests are followed by
agent-run verification of the changed flow in the inline browser. Leave the app
open for the user's independent review and wait for their confirmation before
merging or pushing directly to `main`. Record any unavailable checks and observed
limits.

Preserve these contracts throughout the rework:

- Direct execution needs a high-confidence, single-purpose request and reliable
  argument extraction. Ambiguous, contextual, compound, and LLM-dependent requests
  use the agent, except the approved fixed high-confidence sentiment/keyword/FAQ workflows,
  reported as `llm_assisted`. Missing material information requires clarification.
- Sentiment analyzes the complete source statement, including negation and
  punctuation, rather than an isolated emotional word or instruction wrapper.
- Activity shows observable events and short factual explanations of routing.
  Never expose private model reasoning, credentials, or raw provider/server logs.
- Demo policies remain identified as fictional. Drafts retain separate user
  action instructions and never imply an email was sent.
- Streaming, refresh, restoration, and rerendering must not execute a turn again.
  Preserve successful outcomes and represent interrupted/unknown work accurately.
- Reminders always require agent orchestration when connected. Connecting reminder
  or notification side effects to chat, deployment, other endpoints, metrics,
  new external services, and multiple-agent architecture are outside this rework.
  Describe unavailable capabilities honestly; resume remaining integration work
  under the original plan after handover.

## Ordered Implementation Steps

Tool/routing and one-agent behavior are verified first, followed by durable
history, chat APIs/navigation, and backend events. The existing inspector stays
available for those checks. Completed inline details (step 11), readable answers
(step 12), and live activity (step 13) then use the verified backend contracts.

### 1. Remove developer chrome and redundant metadata

- [x] Discuss, implement, and verify this slice.
- **Problem/change:** Remove Deploy and its user-facing flow using supported
  Streamlit configuration where possible; remove the console caption and Workspace
  session ID/local-storage/backend explanations. Keep useful capability limitations
  accessible through appropriate answers and, later, Docs.
- **Input → output:** Current preview → cleaner header and sidebar, retaining the
  product identity and working chat controls.
- **Verify:** Inspect desktop/mobile and the deployment menu entry; check chat input,
  sidebar accessibility, and useful loading controls still work. No new behavior
  tests for simple text removal unless an existing check needs updating.

#### Step 1 agreed contract and outcome — 2026-10-07

- **Agreement:** User approved header/Workspace cleanup and proportional existing
  UI/browser checks. Keep the OpsFlow identity, capability subtitle, internal
  session continuity, native header controls, and concise draft/reminder limitations.
- **Implemented:** `[client] toolbarMode = "viewer"` hides Deploy, rerun, and
  clear-cache developer actions using installed Streamlit 1.65.0 configuration.
  Removed the redundant console caption and visible session/history explanation;
  Workspace now states that drafts need review/sending and chat cannot schedule
  reminders or send email. Updated `docs/streamlit-console.md`.
- **Verified:** All 18 existing `tests/test_streamlit_ui.py` checks, `pip check`,
  and `git diff --check` pass. A real local sentiment request completed via the
  direct route. Browser checks at 1440 px and 390 px confirmed cleaned header and
  sidebar, Deploy absent from toolbar/menu, mobile panel stacking, no horizontal
  overflow, keyboard sidebar open/close, and the input's visible 2 px focus outline.
  An isolated delayed local HTTP fixture confirmed Running/Stop feedback, the
  spinner, disabled submission during work, and input recovery after HTTP 503;
  its logs recorded one request. Temporary fixture services were stopped.
- **Limits/design:** No new tests, CSS, dependencies, backend behavior, live
  provider, SMTP, or deployment changes/checks. Existing LangChain deprecation
  warnings remain. Figma lists Foundations only; further inspection was rate-limited.
  Used the documented approved adaptation without adding a new design pattern.
- **Delivery:** One scoped commit/PR on `fix/rework-interface-cleanup`, with
  user-only authorship and DCO sign-off. Later rework steps need separate agreement.

### 2. Accept natural-English sentiment requests

- [x] Discuss, implement, and verify this slice with offline language-stage doubles.
- **Problem/change:** Replace mandatory quoted syntax with structured LLM source
  extraction, deterministic VADER scoring, and an LLM-written explanation. The user
  proposed one dedicated workflow per deterministic capability; start with sentiment
  only, then separately review keywords and FAQ in step 3.
- **Input → output:** `Just check the sentiment of this I am happy` → source
  `I am happy` → VADER result → a conversational explanation grounded in that result.
  The same intent with quotes/colon stays valid. Only scoring is deterministic;
  structured JSON does not guarantee correct extraction or faithful prose.

#### Step 2 contract — 2026-10-07

User approved completing standalone step 2a after confirming the classifier remains
first in the proposed chat flow. Step 2a is verified as recorded below. Step 2b and
its routing revision are now approved as recorded below.

**2a — Standalone sentiment workflow (approved implementation slice)**

- [x] Implement and verify the standalone contract with offline provider doubles.
- Add a dedicated `run_sentiment_workflow(request)` function. Keep
  `analyze_sentiment(text)` as the existing pure VADER tool; do not replace it with
  an LLM or make the agent's existing scorer recursively invoke this workflow.
- Accept one nonblank English request within the existing 10,000-character limit.
  Retain the original request in application code rather than asking the model to
  reproduce it. No conversation history is supplied to this standalone function.
- First LLM call: a sentiment-specific system prompt asks for strict structured
  output with `status` (`ready`, `needs_clarification`, or `agent_required`), nullable
  `source_text`, and a bounded reason code. Treat source commands as data. Return
  `ready` only for one explicit, self-contained sentiment task; missing/ambiguous
  source requires clarification, while contextual or compound requests need the agent.
- Validate the schema and status/field combinations locally. For `ready`, require
  a nonblank verbatim contiguous excerpt of the original request, preserving
  negation, capitalization, punctuation, and line breaks. Do not translate,
  paraphrase, or stitch together excerpts. This check rejects invented text but
  cannot prove the model selected the complete intended source; test that separately.
- Invoke VADER exactly once only after successful extraction validation. Preserve
  the exact selected source and the authoritative label and numerical scores.
  Neither clarification nor agent-handoff outcomes execute VADER in this function.
- Second LLM call, only after scoring succeeds: supply the retained request,
  validated source, and actual VADER result to a separate presentation prompt.
  Request a short natural-English explanation, without changing the label/scores,
  claiming certainty about the author's feelings, or following source instructions.
  Validate a bounded structured `reply`; keep raw results separate from prose.
- Return the original request, selected source, outcome, structured result, reply,
  and actual stage statuses/timings. A successful answer has two fixed LLM calls
  and one local scoring call; this is not an open-ended tool-selection loop.
- Extraction/provider/validation failure: return a sanitized failure without
  scoring or a presentation call. VADER failure: retain the attempted input and
  do not generate a success explanation. Presentation failure: retain the successful
  VADER result and provide a fixed factual fallback reply with an explicit
  presentation-failure indication; never rerun extraction or scoring to repair prose.
- Reuse the existing Groq/LangChain provider approach, with bounded calls and no
  automatic retries. Verify installed strict-schema/model compatibility before
  coding; do not add a provider or dependency without discussion. Two LLM calls add
  latency, cost, and provider dependence even though VADER itself remains local.
- **Proportional verification:** Provider doubles cover a representative unquoted
  success, quoted regression, negation/multiline fidelity, missing/uncertain source,
  context/compound abstention, embedded source commands, malformed/non-verbatim
  extraction, provider failure, scorer failure, and presentation failure with retained
  results. Assert the exact scorer input and execution counts. Reuse existing VADER
  tests instead of duplicating its scoring coverage. Separately agree on a small
  synthetic live extraction/prose review; doubles do not establish language quality.
- **Boundary:** No runtime/API/UI wiring, classifier changes, generalized workflow
  framework, keywords/FAQ migration, or reminder/email side effects in 2a.

**Step 2a outcome — 2026-10-07**

- Implemented `app/sentiment_workflow.py` with strict structured extraction,
  verbatim-source/status validation, one unchanged VADER call, and bounded structured
  explanation. Preserves the original request, actual results, and attempted-stage
  timings. Abstention never scores; presentation failure retains scoring with an
  explicit `partial_failure` status and fixed factual fallback. No retries or agent
  invocation. See `docs/sentiment-workflow.md` for configuration and output contracts.
- Verified all 709 tests (39 new), `pip check`, and documentation/code whitespace.
  The installed LangChain adapter was exercised with a fake SDK completion transport;
  checked Groq strict-schema documentation and existing dependency versions. Fixed a
  pytest reserved parameter name caught in initial collection. No dependency changes.
- Limits: no live Groq calls or language-quality/injection-resistance evaluation;
  substring/schema checks cannot establish source completeness or prose fidelity.
  Existing LangChain history deprecation warnings remain. No runtime, classifier,
  API, UI, history, agent registry, SMTP, or deployment changes/checks.
- Delivery: user-authored DCO-signed PR #22 merged into `main` on 2026-10-07.
  At 2a delivery, chat integration was still pending.

**2b — Chat integration (approved implementation slice)**

- **Agreement:** User requested step 2b and selected `llm_assisted` with the existing
  status rules: completed/clarification HTTP 200; extraction/scoring failure and
  retained-result presentation partial failure HTTP 503. Classifier stays first.
- **Implementation contract:** Add `workflow_trace` for actual attempted-stage
  statuses/reasons/timings, preserve VADER tool inputs/results in `trace`, and retain
  both records in process-local history. Agent handoff retains the extraction stage
  and supplies the unchanged request/history once. The existing inspector displays
  workflow stages using its current native expander pattern. No interface redesign.
- **Verification:** Offline provider doubles for successful unquoted/quoted requests,
  classifier gating, clarification, contextual/compound handoff, failures, retained
  partial results, API/client/history preservation, and UI rerender non-execution.
  Inspect saved-classifier predictions separately. Existing FAQ/keyword/agent checks
  cover regression behavior; no live provider quality checks in this slice.

- Dispatch: classify once; high-confidence sentiment candidates enter the
  fixed workflow. Low-confidence/other intents retain current dispatch. Contextual
  and compound abstentions pass the original request/history to the existing agent;
  missing source yields clarification. Never pass the instruction wrapper to VADER.
- Approved exception to the previous all-LLM-dependent-requests-use-agent rule:
  high-confidence sentiment uses fixed `llm_assisted` execution; `direct` retains
  wholly local execution and `agent` denotes dynamic orchestration. Update the chat
  API/client together; the FAQ-only endpoint retains its existing route contract.
- Carry the grounded reply, raw result, clarification/failure state, and observable
  stage timings through runtime/API/session history. Presentation failure maps to
  `partial_failure`; preserve successful scoring and prevent duplicate execution.
- Verify classifier predictions separately from extraction, chat response/history
  round-trips, handoff with original context, and unchanged FAQ/keyword behavior.
  Do not retrain or change confidence thresholds without separate evaluation/agreement.
- Step 12 remains the general UI presentation/onboarding work. Producing a sentiment
  reply here does not authorize moving the inspector or redesigning the interface.

**Step 2b outcome — 2026-10-07**

- Connected the fixed sentiment workflow behind unchanged intent/confidence gating
  in `app/runtime.py`. The chat API/client accepts `llm_assisted` and preserves
  the reply/result/tool trace plus actual `workflow_trace` stages. Existing session
  serialization saves these fields automatically. Contextual/compound abstention
  retains extraction details and hands the original request/history to the agent
  once. Missing/ambiguous source clarifies; failures never rerun successful scoring.
- Kept the agreed HTTP 200/503 semantics, including retained-result presentation
  partial failure. Added an inspector expander using the existing native pattern;
  stage timings are backend values. The agent registry still invokes pure VADER.
  FAQ-only scope and keyword/agent contracts remain covered by existing checks.
- Verified all 721 tests (15 new, with existing sentiment checks migrated to the
  new route), `pip check`, and whitespace checks. Fixed a new test's mutable mock
  message capture by snapshotting each invocation. Provider doubles cover
  classifier-first order, threshold/invalid-confidence gates, exact source/one
  scoring call, clarification/follow-up, original-context handoff, extraction and
  scorer failure, retained partial outcomes, OpenAPI/client/history, and UI rerenders.
- Separately inspected saved-classifier predictions: the unquoted happy example
  predicts sentiment at 0.904 against 0.71, missing-source/contextual examples also
  predict sentiment, and a combined sentiment/summary example predicts compound.
  This is example inspection, not a new classifier evaluation or live quality test.
- Limits: no live Groq, SMTP, deployment, or new browser-layout verification. Figma
  inspection was rate-limited; reused the documented approved adaptation with no
  CSS/token/layout change. Existing LangChain history warnings remain. No new
  dependencies, threshold/model training, persistence, or subsequent-step work.
- Delivery: user-authored DCO-signed PR #23 on `feature/sentiment-chat-workflow`
  now targets `main` after dependency PR #22 merged. The user authorized merging
  both slices; existing 721-test evidence applies to the unchanged application diff.

### 3. Review natural-English keyword and FAQ requests

- [x] Discuss, implement, and verify bounded keyword/FAQ slices as recorded below.
- **Problem/change:** Apply the source-boundary approach to keyword extraction and
  audit ordinary FAQ questions. Expand only demonstrated gaps while preserving
  ambiguity/no-match handling and exact stored policy answers.
- **Input → output:** `Find keywords in this The server failed after the deployment`
  → source text/keywords; `What is the remote work policy?` → grounded demo-policy
  result or clarification, without mandatory `keywords:` or `faq:` syntax.
- **Verify:** Representative natural phrasing, missing source, unrelated/ambiguous
  policies, compound/contextual fallbacks, and existing quoted-form regressions.
  Do not imply lexical similarity or keyword relevance is a confidence probability.

#### Step 3a contract — 2026-10-07

- [x] Implement and verify the standalone keyword workflow with offline doubles.

- **Agreement:** User approved the first keyword-only PR after discussion of the
  sentiment pattern. Implement the standalone workflow first; discuss FAQ later.
  Keyword chat integration needs a separate agreement.
- **Input → output:** One nonblank English request, at most 10,000 characters,
  enters `run_keyword_workflow(request)`: strict LLM source extraction → unchanged
  `extract_keywords(text)` YAKE tool exactly once → grounded LLM reply. Retain the
  original request, verbatim contiguous source, ranked phrases/raw scores, outcome,
  and actual attempted-stage statuses/timings. Quotes and colons are optional.
- **Boundaries/failures:** Missing/ambiguous source clarifies; contextual, compound,
  or unsupported requests return an agent-handoff decision without invoking it.
  Validate extraction locally before running YAKE. Embedded source commands are
  data. Extraction/tool failure stops later stages; presentation failure retains
  the successful result, including an empty list, with a factual fallback. No
  retries, generated keywords, reranking, or confidence-percentage claims.
- **Provider:** Reuse the installed Groq/LangChain approach with strict schemas,
  bounded calls, lazy configuration, and external tracing disabled. No new service,
  dependencies, classifier/threshold changes, runtime/API/UI/history wiring,
  generalized workflow framework, FAQ changes, or email/reminder side effects.
- **Proportional verification:** Offline provider doubles cover unquoted/quoted
  success, full multiline/negation source preservation, missing/ambiguous source,
  contextual/compound abstention, embedded commands, invalid/non-verbatim output,
  provider/tool failures, and retained-result presentation failures. Assert exact
  tool input/count and actual result transport; cover empty keyword results.
  Exercise the installed adapter with fake SDK transport and reuse existing YAKE
  tests. No live provider quality check is authorized in this slice; schema and
  substring checks cannot prove source completeness or prose fidelity.

#### Step 3a outcome — 2026-10-07

- Implemented `app/keyword_workflow.py` with strict structured source extraction,
  verbatim/status validation, one unchanged YAKE call, and bounded structured reply.
  Preserves the original request, exact source, ranked phrases/raw scores, outcomes,
  and actual attempted-stage timings. Clarification/handoff never run YAKE.
  Presentation failure retains results, including an empty list, with a factual
  fallback and explicit `partial_failure`; no automatic retries or agent invocation.
- Verified all 763 tests (42 new), `pip check`, and documentation/code whitespace.
  Fake SDK transport exercises the installed LangChain strict-schema adapter;
  checked Groq's strict-schema support for the existing allowed models. No new
  dependencies. Existing LangChain history deprecation warnings remain.
- Limits: no live Groq or language-quality/injection-resistance evaluation; schema
  and substring checks cannot prove complete extraction or faithful presentation.
  No classifier/threshold, runtime/API/UI/history, pure tool/agent registry, FAQ,
  SMTP, or deployment changes. See `docs/keyword-workflow.md` for the contract.
- Delivery: one user-authored DCO-signed change on
  `feature/keyword-language-workflow`, published as keyword-only PR #24.
  At standalone delivery, keyword chat integration still needed agreement;
  approved step 3b below is now included in the same PR. FAQ remains deferred.

#### Step 3b contract — 2026-10-07

- [x] Implement and verify keyword chat integration with offline provider doubles.

- **Agreement:** User approved connecting keywords to chat with the sentiment
  contract and explicitly requested committing this slice in existing PR #24.
  PR #24 now includes both the standalone workflow and chat integration.
- **Dispatch/output:** Classify once; high-confidence keyword requests enter the
  fixed `llm_assisted` extraction → YAKE → presentation workflow, including quoted
  requests. Preserve the reply, raw ordered phrases/scores, exact tool input,
  tool trace, and actual `workflow_trace` through API/client/session history.
  Reuse the inspector's native expander for keyword stages without UI redesign.
- **Status/failure:** Completed/clarification HTTP 200; extraction/tool failure or
  retained-result presentation partial failure HTTP 503. No repair/retries.
  Missing/ambiguous source clarifies without YAKE; contextual/compound/unsupported
  abstention hands original request/history to the agent once and retains extraction
  details. Low-confidence/other intents retain agent behavior; FAQ stays unchanged.
- **Proportional verification:** Offline doubles cover classifier-first gating,
  unquoted/quoted success, missing source, contextual/compound handoff, extraction
  and tool failures, retained presentation failures/empty results, API/client/history,
  and UI reply/stage rendering without resubmission. Check saved-model predictions
  separately, including the supplied Langchain example. Reuse standalone/tool tests.
  No live LLM, classifier training/threshold changes, provider/dependency changes,
  generalized framework, agent presentation changes, streaming, or FAQ work.

#### Step 3b outcome — 2026-10-07

- Connected keywords behind unchanged classifier/confidence gating using the same
  fixed workflow dispatch as sentiment. API/client/session history preserve the
  reply, ordered raw result, exact tool trace, and keyword `workflow_trace` stages.
  The inspector reuses its native expander and identifies LLM versus local stages.
  Assistant turns show readable replies alongside the existing raw JSON display.
- Preserved HTTP 200/503 rules, missing-source clarification, original-request/history
  agent handoff, retained extraction details, and successful/empty results on reply
  failure. No retries or duplicate tool calls. Agent registry still uses pure YAKE;
  low-confidence/other-intent behavior and FAQ-only scope remain unchanged.
- Verified the 784-test suite (21 new integration/UI checks, 42 standalone checks
  from 3a); all 21 UI checks also pass after the final stage-label adjustment.
  `pip check` and whitespace checks pass. Offline checks cover gating, exact
  source/counts, abstention/follow-up, API/OpenAPI/client/history, failures/empty
  results, and UI replies/stages/non-executing rerenders. Existing warnings remain.
- Separately inspected saved-classifier examples: quoted Langchain request predicts
  keywords at 0.7853 and the unquoted server example at 0.8271 against 0.71; the
  original paragraph plus 'above text' predicts sentiment at 0.3336 and stays with
  the agent. These are example checks, not a classifier quality evaluation.
- Limits: no live Groq/language quality, SMTP, deployment, or browser-layout checks;
  no dependencies, model training/threshold changes, generalized framework, agent
  presentation changes, or FAQ work. Figma inspection was rate-limited; reused the
  documented approved adaptation with no CSS/token/layout changes.
- Delivery: additional user-authored DCO-signed integration commit in existing
  PR #24, whose title/description now cover standalone workflow plus chat wiring.
  FAQ remains the next discussion; later implementation is not authorized.

#### Step 3b presentation correction — 2026-10-07

- **User correction/contract:** The LLM phrase list followed by raw JSON repeats
  the result. User requested a human introduction and an intuitive phrase/score
  table. Correct keyword presentation in the same PR: the LLM supplies a brief
  introduction; the application renders actual YAKE phrases/scores once in a native
  table, preserving rank. Display scores to five decimal places while retaining
  full precision in API/history/inspector. Explain that lower scores mean greater
  relevance, not confidence. Keep raw JSON in the inspector, not the main answer.
- **Failure/boundary:** Retained results still render on presentation failure, with
  a short factual fallback introduction; empty results state that no candidates
  were found and do not render an empty table. Keyword-only presentation correction;
  no routing, YAKE, agent, FAQ, dependencies, or general step-12 UI redesign.
- **Verification:** Update the existing workflow fallback/UI checks and add targeted
  empty-result and literal-cell checks. Verify ordered actual phrases/raw scores,
  readable intro, table formatting, inspector precision, partial failures, and
  non-executing rerenders. Provider doubles verify transport/contract, not live prose.
  Use supported native Streamlit table APIs and the existing design adaptation.
- **Outcome:** Updated the LLM prompt to request an introduction instead of a
  repeated phrase list. The keyword assistant turn now renders ordered raw YAKE
  results in a literal-text Phrase/Score dataframe with five-decimal display; raw
  JSON remains in the inspector. Retained-result fallback reports count/empty state
  without duplicating phrases. No result precision, route, or execution changes.
- **Verified:** All 786 tests (two new UI boundaries, existing success/failure
  checks updated), `pip check`, and whitespace checks pass. Tests cover table
  order/raw precision/format, inspector-only JSON, introduction transport, retained
  partial results, empty results, literal cells, and non-executing rerenders.
  Installed Streamlit dataframe/NumberColumn APIs checked locally. No live LLM or
  browser-layout verification; existing LangChain history warnings remain. The
  documented native design adaptation is retained without new CSS/Figma changes.
- **Delivery:** One additional user-authored DCO-signed presentation correction
  commit in PR #24. FAQ remains deferred; general step-12 presentation is separate.

#### Step 3 FAQ architecture discussion — 2026-10-07

- **Direction:** The user's classifier → FAQ TF-IDF ranking → stored answer by
  ID → Groq GPT-OSS presentation diagram is feasible for the current 25 fictional
  policies/75 phrasings. Reuse the local tool/data; rank distinct policy IDs rather
  than treating alternate phrasings as competing answers.
- **Separate decisions:** Intent-classifier TF-IDF and FAQ TF-IDF are different
  fitted spaces. Transform the question with the FAQ vectorizer. Classifier
  probability and cosine similarity are different quantities; similarity is not
  an answer-confidence probability. Preserve existing retrieval heuristics until
  separately agreed evaluation supports tuning.
- **Answer coverage:** A matched policy may not answer every question qualifier.
  Preserve the complete question and exact policy; the presenter should acknowledge
  missing facts and retain conditions/limits. The approved step 3c choice below is
  grounded explanation with retained exact answer. Schema/substring checks cannot
  guarantee complete extraction or faithful prose.
- **Inspection evidence:** Seven read-only local probes exposed coverage/routing
  limits. Retrieval alone matched `Can contractors work from home?` at 1.0 despite
  absent eligibility information; classifier probability was 0.377 against 0.71,
  so this was not a direct chat execution. `Could you explain how I can work from
  home?` matched retrieval at 1.0 but classified `out_of_scope` at 0.578. These are
  examples, not an independent benchmark or authorization to retrain.
- **Alternatives/sequencing:** Start with existing lexical retrieval; discuss added
  phrasings, embeddings/hybrid retrieval, or reranking only if held-out review shows
  a meaningful gap. Better matching still needs answer-coverage review. Standalone
  step 3c precedes separately agreed step 3d classifier-first chat integration;
  preserve the FAQ-only endpoint unless explicitly revised.
- **Primary references checked:** [scikit-learn TF-IDF](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html),
  [cosine similarity](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html),
  and [Groq structured outputs](https://console.groq.com/docs/structured-outputs).
  Groq documents strict-schema support for existing GPT-OSS model choices.

#### Step 3c contract — 2026-10-07

- [x] Implement and verify the standalone FAQ contract with offline provider doubles.
- **Agreement:** User approved proceeding with the proposed first standalone
  slice. Use a grounded LLM explanation, retaining the exact stored policy answer.
  The architecture discussion above records the proposal; this contract is the
  approved implementation boundary. Step 3d chat integration requires separate
  agreement.
- **Input/output:** `run_faq_workflow(request)` accepts one nonblank English
  request up to 10,000 characters. Strict LLM extraction selects a complete
  verbatim contiguous question or returns clarification/agent-required. Preserve
  all qualifiers; never normalize the question into a different question.
- **Execution:** For a valid question call unchanged `retrieve_faq` once.
  Ambiguous/no-match returns fixed clarification without presentation. A match
  enters one bounded structured LLM presentation call with original request,
  question, and actual result. The presenter may return clarification when the
  policy does not cover a material detail; the raw matched result remains intact.
- **Outcomes/records:** Preserve request/question, exact FAQ result, reply, bounded
  reasons, attempted-stage statuses/timings, and total duration. Extraction/retrieval
  failure stops. Presentation failure retains retrieval and returns `partial_failure`
  with an explicitly qualified exact-policy fallback. No retries or agent invocation.
- **Verification:** Offline provider doubles cover natural/quoted fidelity and
  qualifiers, missing/ambiguous/contextual/compound abstention, matched/ambiguous/
  no-match counts, embedded commands, malformed/non-verbatim output, sanitized
  provider/tool failure, retained coverage-clarification and fallback, plus installed
  strict-schema serialization. Reuse local retrieval tests. No live language-quality
  check is authorized in this slice; schema checks/doubles cannot prove grounding.
- **Boundaries:** Reuse current dependencies/Groq models and the pure FAQ tool.
  No classifier/threshold/index tuning, runtime/API/UI/history/agent-registry
  wiring, side effects, generalized workflow framework, or later rework work.

#### Step 3c outcome — 2026-10-07

- Implemented `app/faq_workflow.py`: strict verbatim question extraction →
  unchanged `retrieve_faq` once → bounded grounded presentation for matched
  results only. Preserves full questions, exact answers/IDs/candidates, separate
  prose, actual stages/timings, and sanitized outcomes. Missing/contextual/compound
  extraction abstains; ambiguous/no-match retrieval clarifies without presentation.
  Presenter-reported missing details clarify while retaining a raw matched result.
  Presentation failure retains retrieval with a qualified exact-answer fallback;
  no retries, repeated lookup, or agent invocation. Added `docs/faq-workflow.md`.
- Verified all 833 tests (47 new), including existing retrieval/routing/API/chat/
  agent/UI regressions, plus `pip check` and whitespace checks. Offline doubles
  cover question fidelity/qualifiers, abstention, exact call counts, result transport,
  missing-detail clarification, failures, and fallback. Fake SDK completion
  transport verifies installed strict-schema serialization for both GPT-OSS models.
  Corrected initial new-test assertions for JSON tuple-to-list serialization;
  application payload/retained result behavior was unchanged by that correction.
- Limits: no live Groq extraction/grounding review or general injection-resistance
  guarantee; schema/substring checks cannot prove semantic completeness/fidelity.
  Existing LangChain history deprecation warnings remain. No dependencies,
  classifier/threshold/index, runtime/API/UI/history, pure-tool/agent-registry,
  side effects, or later rework changes. Step 3d requires separate discussion.
- Delivery: one user-authored DCO-signed change on `feature/faq-language-workflow`;
  merged as PR #25 into `main` on 2026-10-08 after the user authorized delivery.

#### Step 3d contract — 2026-10-07

- [x] Implement and verify chat integration and the bounded FAQ clarification correction.
- **Agreement:** User requested connecting the FAQ workflow to app chat after
  reporting an irrelevant recipient clarification. High-confidence FAQ chat
  requests use fixed `llm_assisted` extraction/retrieval/presentation. Retain the
  classifier/0.71 threshold and FAQ-only endpoint contract. The reported contractor
  prompt scores 0.669 and therefore continues through the existing agent.
- **Bounded correction:** Clarify the agent prompt: self-contained policy questions
  require FAQ lookup, not a recipient/department; recipient clarification applies
  to requested email drafting. Current independent questions supersede unrelated
  prior drafting context. Retain the pure agent FAQ tool and require acknowledgement
  of material question details absent from its exact stored answer. Prompt changes
  cannot guarantee model compliance or grounding.
- **Records/status:** API/client/history retain the grounded reply, exact FAQ
  result/question, one tool execution, and actual workflow stages/timings. Clarification
  and completed outcomes remain HTTP 200; errors/retained partial failures use 503.
  Contextual/compound extraction abstention hands original request/history to the
  agent once while retaining extraction stages. Failures do not retry or hand off.
- **UI:** Reuse native assistant text and existing inspector expanders. Show FAQ
  stage names and LLM/local labels; retain exact policy JSON in the inspector rather
  than repeating it below the generated FAQ reply. No CSS/layout/token changes or
  general step-12 redesign. Figma inspection remains limited by server rate limits;
  use the existing documented native adaptation.
- **Verification:** Offline doubles cover gates, exact calls, clarification and
  handoff, failure/status/result retention, API/client/history, prior-context FAQ
  fallback and draft regressions, and UI rerender non-execution. A small synthetic
  live HTTP review will inspect the actual high-confidence and reported low-confidence
  FAQ responses using the existing local app/provider; no email/send/reminder side
  effects. Preserve existing checks for FAQ-only, sentiment/keyword, and agent tools.
- **Delivery/boundary:** One scoped user-authored DCO-signed integration commit/PR
  on `feature/faq-chat-workflow`, stacked on open standalone PR #25. No retraining,
  retrieval tuning, new dependency/provider, generalized framework, persistence,
  streaming, other endpoint changes, or later rework work.

#### Step 3d outcome — 2026-10-07

- Connected high-confidence FAQ chat requests to the existing fixed workflow as
  `llm_assisted`. API/client/history preserve readable reply, raw FAQ result,
  question/tool observation, and actual workflow stages/timings. Clarification
  and handoff, HTTP 200/503, retained partial results, and no-retry behavior match
  the agreed contract. Inspector labels FAQ extraction/presentation as LLM stages
  and retrieval as local; exact policy JSON stays in the inspector. FAQ-only scope,
  classifier threshold, pure tool/index, and agent registry are unchanged.
- Corrected agent instructions to distinguish policy explanations from requested
  email drafts and respect independent questions after drafting context. Added
  an explicit coverage/eligibility example after the first live check incorrectly
  inferred contractor eligibility despite performing the correct FAQ lookup.
  Final inspected fresh-session and post-draft samples both returned appropriate
  `needs_clarification`, preserving conditions and acknowledging unspecified
  contractor eligibility. The post-draft missing-recipient sample clarified with
  no tool execution; the subsequent policy question looked up the FAQ once.
- Verified all 855 tests (22 new), `pip check`, and whitespace checks. Offline
  coverage includes gates, original-context handoff, actual execution counts,
  status/history/API/client preservation, retained failures, low-confidence pure
  agent lookup, and non-executing native UI rerenders. Checked installed Streamlit
  display APIs. The running local backend reloaded changes and exposed FAQ stages;
  a synthetic natural-policy HTTP request completed with `llm_assisted`, two LLM
  stages, one lookup, and inspected faithful conditions. Five synthetic live chat
  turns total covered that match, the initial eligibility failure, missing-recipient
  clarification, and the two final corrected contractor samples.
- Limits: small inspected live samples and doubles do not establish general
  extraction/prose/abstention quality or injection resistance. Existing LangChain
  deprecations remain. Figma inspection was rate-limited; reused the documented
  native adaptation with no CSS/layout/token changes or new browser-layout review.
  No dependency/provider, training/threshold, retrieval tuning, side effects,
  persistence/streaming, other endpoints, or later rework work changed.
- Delivery: one user-authored DCO-signed integration change on
  `feature/faq-chat-workflow` in PR #26. On 2026-10-08 the user authorized merging
  it and its standalone dependency. PR #25 is merged; PR #26 now targets `main`.
  Step 4 remains the next discussion.

#### Step 3d caption correction — 2026-10-08

- **Agreement:** User requested removing the fixed `Fictional demo policy — verify
  your actual company policy.` caption from the chat display. Remove both render
  locations; retain underlying JSON data, demo metadata, model replies, inspector
  records, and all routing/execution behavior.
- **Verification scope:** Update the existing FAQ UI assertion and run the current
  UI checks plus whitespace validation. No new tests or live provider calls are
  needed for this small text removal. Include in the existing FAQ integration PR #26
  as one user-authored DCO-signed presentation correction.
- **Outcome:** Removed both fixed caption render locations. All 26 existing
  Streamlit/UI checks and whitespace checks pass; the updated assertion verifies
  caption absence while retaining reply/inspector data and non-executing rerenders.
  No new tests, dependencies, backend/provider behavior, or live calls changed.

### 4. Verify conversational summarization and drafting

- [x] Discuss, implement fixes, and verify with offline/scripted-browser checks.
- User approved merge on 2026-10-08; live model quality remains unverified.
- **Problem/change:** Audit source extraction, writing instructions, and follow-up
  handling for the remaining available tools; fix demonstrated failures only.
- **Input → output:** `Summarize this The outage lasted 20 minutes and is resolved`
  → summary; `Draft an email to Alex saying the outage is resolved` → draft and
  separate user actions; missing recipient/facts → clarification.
- **Verify:** Standalone and contextual requests, clarification answers, source
  preservation, demo-policy qualification, and unavailable sending/reminder requests.
  Use provider doubles in tests; agree separately on any limited live quality checks.

#### Step 4 agreed contract — 2026-10-08

- User approved auditing the existing agent path and fixing demonstrated failures
  only, with proportional provider-double tests, regression checks, and inline-browser
  review. Summarization/drafting remain agent operations; no new fixed workflow.
- Missing source, draft recipient, or material facts should produce a conversational
  question, not an execution error. A missing/blank required source or recipient in
  an otherwise valid proposed writing-tool call clarifies without executing a tool.
  Malformed types, extra fields, bounds violations and provider failures remain errors.
  The chat shows clarification as an ordinary reply; its status remains in the inspector.
- Verify unquoted/multiline source transport, contextual summaries, clarification
  answers followed by drafting, revisions, session isolation, retained tool results,
  separate fixed user actions, demo-policy qualification and unavailable actions.
  Provider doubles establish protocol behavior, not semantic extraction quality.
  No live model calls are authorized in this slice.

#### Step 4 outcome — 2026-10-08

- Fixed missing/blank required writing-tool arguments that previously produced
  `invalid_tool_arguments`; now returns `needs_clarification` and a fixed question
  without executing a tool. Other validation failures retain the error contract.
  Removed the technical clarification warning from the chat; inspector status remains.
- Added 16 scripted API/agent checks and adjusted two existing assertions. All 870
  tests, `pip check`, and whitespace checks pass. Existing standalone summary/draft
  tests cover provider payload/failure contracts; session tests retain demo-policy
  qualification and fixed draft actions. No dependencies or provider APIs changed;
  installed Streamlit 1.65.0/ChatGroq 1.1.3/Core 1.6.6/Groq 0.37.1/Pydantic 2.13.5 checked.
- Inline browser exercised the real API/session/runtime and Streamlit path with a
  temporary scripted orchestration/summary/draft provider: missing recipient/facts,
  recipient answer, supplied facts completing a draft with separate actions, and
  contextual summary. Questions displayed without error/warning banners; inspector
  retained status, exact inputs/results and actual timings. Review app stays open
  at `http://127.0.0.1:8502` (fixture backend on 8001).
- Limits: no live provider quality, SMTP/inbox, reminder creation or deployment
  checks. Doubles cannot establish semantic extraction, reference resolution or
  factual fidelity. Existing LangChain deprecation warnings remain. Figma inspection
  was rate-limited; retained documented/native UI without CSS/layout expansion.
- Delivery: user-authored DCO-signed PR #27 on
  `fix/conversational-summary-draft-review`, merged after user approval on
  2026-10-08. Later rework steps need separate agreement.

#### Future-build requests recorded — 2026-10-08

User agreed to record these ideas for future builds rather than implement them in
step 4: a settings icon near the bottom-left sidebar opening Reminders, with Docs
added in a later build; reminder cards showing due-time details and a link back to
creation chat, with off/delete controls; and a separate Email page listing drafts
and actual sent records. Discuss navigation/design alongside step 6 and the Docs
entry in its planned slice. Reminder creation from chat, delivery integration, sent
email records and off/delete semantics require separate post-rework contracts under
the existing side-effect boundaries. A draft must never appear as sent. This record
does not authorize those features or change the ordered rework implementation steps.

### 5. Verify one-agent multi-step requests

- [x] Discuss, implement fixes if needed, and verify this slice within recorded limits.
- **Problem/change:** One agent identifies multiple requested operations, passes
  earlier observations to dependent tools, and reports each actual outcome.
  Use "multi-step request" in the product and documentation.
- **Input → output:** `Analyze the sentiment, extract keywords, summarize this
  complaint, and draft an email to Alex about it: The service failed twice today`
  → ordered tool results and a draft based on supplied facts/results.
- **Verify:** Three/four-tool requests, dependency ordering, missing inputs,
  successful steps followed by a failure, and requests beyond current budgets.
  Discuss whether limits need adjustment; do not promise unlimited work or silently
  drop tasks. Explain unfinished work without claiming it completed.

#### Step 5 contract and outcome — 2026-10-08

- **Agreement:** User requested implementation of step 5. Bounded audit of three/
  four-tool requests, dependency observations, missing input after success, later
  failure, and existing budgets. Keep one agent and current limits; no multi-agent
  architecture, side-effect integration, routing thresholds, or new dependencies.
- **Implemented:** Explicit multi-step/dependency/budget guidance in the agent prompt.
  Fixed application draft rendering that previously hid earlier results: completed
  sentiment, keywords, summary, and policy lookup now accompany the exact draft and
  fixed actions. Stopped requests explicitly report unfinished work and retain all
  actual results. No retry or speculative continuation.
- **Verified:** All 877 tests (seven added), `pip check`, and whitespace checks pass.
  Scripted real-loop/API/session tests verify one model initialization, classification
  once, three/four ordered tools, exact source and earlier observations, summary-to-
  draft dependency, retained failure/clarification records, five-tool success, refused
  sixth execution, and soft time-budget overrun with successful results retained.
  Existing tests cover invalid calls/provider failure, FAQ/draft qualification, and
  UI rerender non-execution. Saved classifier predicts the four-tool complaint as
  `compound_request` at 0.7867 against 0.71. Inline browser uses real classifier,
  sentiment, keywords, chat/session/runtime and UI with temporary scripted agent/
  writing providers; verified four outcomes, missing-recipient clarification with
  three retained results, and budget stopping after five tools.
- **Limits/delivery:** Prompt guidance and provider doubles do not establish live
  semantic extraction, dependency choice, exhaustive task coverage, or prose fidelity.
  No live Groq, SMTP/inbox, reminder, or deployment checks. Existing LangChain
  deprecations remain. Review app stays open on port 8503 for independent user review;
  user approved merging PR #28 on 2026-10-08. Step 4 PR #27 is already merged; original plan remains
  paused. Step 6 needs separate discussion.

### 6. Agree on persistent-chat and navigation contracts

- [x] Discuss and record the contract before storage/UI implementation.
- **Problem/change:** Define what a saved chat contains and how users recover it.
  Propose local SQLite reuse for chat storage, without changing reminder tables or
  worker locking. Decide storage/schema, ownership, restoration, titles, and behavior
  when a chat is switched during execution.
- **Input → output:** The agreed chat-list experience → a documented persistence/API
  contract and sidebar/activity interaction specification using existing design tokens.
- **Decisions:** Local single-user versus access-controlled hosted use; browser chat
  identity after refresh/restart; simple initial titles; history/context limits; and
  treatment of pending/interrupted turns. IDs alone are not authorization.
- **Verify:** Review the contract against isolated contexts, refresh/backend restart,
  existing direct/agent history semantics, failure retention, and no repeat execution.
  Renaming/deleting/searching chats are optional future scope, not prerequisites.

#### Step 6 contract and review — 2026-10-08

- **Agreement:** User requested step 6 and selected one trusted local user and
  disabled New chat/chat switching during execution. Recorded the full target in
  [docs/persistent-chat-contract.md](docs/persistent-chat-contract.md). This is a
  documentation slice; storage, API, UI, and event implementations remain separate.
- **Contract:** Separate local chat SQLite database using existing conventions;
  versioned chat/ordered-turn records; full execution/failure/demo-marker retention;
  commit-before-execution/final acknowledgement; read-only context restoration;
  explicit interrupted/unsaved outcomes and no automatic retries. Proposed turn
  IDs prevent duplicate persistent submissions. Keep current full-history behavior,
  HTTP status semantics, caller-owned session-ID compatibility, and FAQ boundaries.
- **Navigation:** Shared local catalogue, deterministic first-message titles,
  URL-selected chat restoration, create/list/load API shapes, disabled navigation
  while running, and later inline Activity using existing tokens. Renaming/deletion/
  search, hosted ownership, context budgeting, and reminder integration are outside
  scope. Exact API models and visual patterns are reviewed in their later slices.
- **Verified:** Contract reviewed against current sessions/runtime history transport,
  chat API/client, Streamlit state, and memory/reminder/design documentation for
  isolated contexts, restart/refresh, retained failures, and non-executing recovery.
  Documentation whitespace checks pass. No runtime tests or browser checks were
  needed for this documentation-only change. Figma metadata inspection was blocked
  by the Starter tool-call limit; visual verification remains pending in UI slices.
- **Next:** Discuss only step 7's durable storage/restoration implementation and
  proportional offline tests before coding. Steps 8–14 are not authorized together.

### 7. Implement durable chat history and runtime restoration

- [x] Discuss, implement, and verify this slice after step 6.
- **Approved slice — 2026-10-08:** User approved durable SQLite chat/turn records,
  context restoration, interrupted recovery, submission-ID duplicate protection,
  explicit write failures, and durable behavior of the existing Python clearing
  function. Catalogue HTTP APIs and sidebar changes stay in steps 8–9. Verify
  fresh-process recovery, isolation/follow-ups, retained failures, duplicate IDs,
  failed writes, and serialization with offline doubles, followed by inline-browser
  chat review. Implemented and verified within the bounds below; user approved
  merging PR #30 and its dependency PR #29 after the browser review.
- **Problem/change:** Store chat metadata, messages, execution records, and finalized
  outcomes durably. Reconstruct the context consumed by the existing agent from saved
  direct/agent outcomes without appending turns twice or changing reminder behavior.
- **Input → output:** Chat turns → durable records → restored conversational context.
  Persist incomplete work with an explicit state rather than fabricating completion.
- **Verify:** Fresh-process restoration, direct-to-agent follow-ups, independent chats,
  failed/partial turns, write failures, ordering, and existing same-session serialization.
  Prevent silent memory/disk divergence and disclose known persistence failure.

#### Step 7 outcome — 2026-10-08

- **Implemented:** Versioned `chats`/`chat_turns` in a separate local SQLite file,
  exact ordered user/outcome records, full trace/stage/result/demo-marker retention,
  and reconstruction of authoritative agent context on each request. Existing
  Python clearing is durable, retains metadata/sequence allocation, and rejects
  unfinished work. See [docs/chat-persistence.md](docs/chat-persistence.md).
- **Execution/recovery:** Commit the initial running marker before execution and
  the final outcome before acknowledgement. Failed initial commit prevents work;
  failed final commit returns an explicit unsaved HTTP 503 and blocks continuation.
  Unexpected execution failures remain unknown without raw error exposure. Exclusive
  Unix chat-store ownership prevents a second backend recovering live work; startup
  on first store use marks abandoned markers interrupted without retries.
- **Compatibility:** Optional Python `turn_id` replays identical saved submissions;
  changed content/chat and unfinished IDs conflict. Existing HTTP input and status
  rules remain; catalogue APIs/HTTP IDs/UI navigation stay in steps 8–9. Removed
  the history runnable's automatic append to control commit order; retained the
  pinned message types and snapshot class. One existing deprecation warning remains.
  Response and stored elapsed time are identical, excluding the final save commit.
- **Verified:** All 902 tests (25 new), `pip check`, and documentation/code whitespace
  checks pass. Temporary-file/scripted-provider checks cover fresh-process context,
  abrupt exit/interruption, second-process exclusion, ID replay/conflict/concurrency,
  retained statuses/traces/demo markers, commit rollback/read corruption, clearing,
  unsupported schemas, and safe HTTP/client failures. Existing tests cover real
  local tools, isolation, serialized follow-ups, draft actions, and non-executing UI.
- **Browser:** Inline app on 8504/backend 8014 uses scripted sentiment/agent providers
  with the real classifier, VADER, runtime, API/client, and storage. A completed
  sentiment survived backend restart and reached the next agent turn; rerender did
  not append turns. A temporary database trigger forced final-save failure, producing
  the explicit unsaved warning and retaining the running marker. The trigger was
  removed before restart/recovery; the marker became interrupted and one explicit
  new turn continued with restored context. Four records remained (three finished,
  one interrupted), with no repeat execution. Review app is left open for review.
- **Limits/delivery:** No live provider quality, SMTP/inbox, hosted/multi-host/network
  storage, Linux/Windows, or deployment verification. No new dependencies, reminder
  changes, automatic migration of old process-local memory, or browser refresh
  restoration. Commit/PR is separate from the step 6 contract dependency PR #29.
  User approved merging both PRs on 2026-10-08. PR #29 is merged; PR #30 now
  targets `main`, with existing verification still applicable.

### 8. Expose chat creation, listing, and retrieval

- [x] Discuss, implement, and verify this slice after step 7.
- **Approved slice — 2026-10-08:** Create with empty JSON/HTTP 201; list metadata
  by descending update time and stable ID; load metadata plus ordered saved turns
  (unknown ID 404), without execution. Add optional submission `turn_id` and echo
  accepted IDs, retaining legacy submissions and 200/503 outcomes; conflicting or
  unfinished IDs return 409. Adapt the HTTP client; navigation stays step 9.
  Verify round-trips, restart recovery, retained records, replay/conflicts, invalid
  input, sanitized storage failures and chat/FAQ regressions, then inline-browser
  review. One trusted local user/backend remains the ownership boundary.
- **Problem/change:** Add only the backend contracts needed for New chat, a chat list,
  and loading saved turns; adapt the HTTP client. Apply the ownership decision from
  step 6. Reading history must not execute tools or submit provider calls.
- **Input → output:** Create/list/load requests → stable internal chat IDs, titles,
  ordered saved messages, outcomes, and activity detail.
- **Verify:** Empty list, create/list/load round-trip, unknown chat, restart recovery,
  invalid input, sanitized storage failures, and access boundaries where applicable.
  Preserve existing chat submission and FAQ contracts unless an agreed change requires
  an explicit compatibility update.

#### Step 8 outcome — 2026-10-08

- **Implemented:** Empty-object creation returns 201 and generated metadata; listing
  returns metadata by descending update time with stable ID ties; loading returns
  one snapshot of metadata and ordered turns. Unknown IDs return 404 without record
  creation. Reads preserve update times and never classify/invoke providers/tools.
  Saved runtime failures, lifecycle, exact execution/activity/timings and demo markers
  remain available. Corrupt execution records fail with sanitized persistence 503.
- **Submission/client:** Optional HTTP `turn_id` replays saved identical submissions;
  conflicting content/chat or unfinished IDs return 409 with safe code/state/message.
  Responses echo accepted IDs; omitted/null IDs generate a new submission each time.
  Existing 200/503 and FAQ contracts remain. Client create/list/load helpers validate
  records and chat association, URL-escape caller-owned IDs, and never retry.
- **Verified:** All 922 tests (20 new) pass, plus `pip check` and whitespace checks.
  The final OpenAPI response-description changes passed 41 targeted API checks.
  New coverage includes create/list/load, ordering/ties, unchanged reads, fresh-process
  interruption recovery without execution, HTTP replay/conflict/status/legacy behavior,
  workflow activity preservation, invalid bodies/IDs, corrupt/safe storage failures,
  client round-trips and safe failures. Existing storage tests cover locking, commit
  rollback, isolation, and full trace/demo retention. Installed FastAPI 0.142.2 and
  Pydantic 2.13.5 checked; no dependency/provider changes.
- **Browser:** Inline Swagger app on `http://127.0.0.1:8015/docs` exercised empty
  listing, creation, real classifier/VADER with scripted language stages, load,
  identical replay, changed-ID-content 409 and unknown-chat 404. Backend restart
  retained one completed turn with identical result/stages/timing and metadata;
  listing/reads did not append or update it. App remains open for user review.
- **Limits/delivery:** One user-authored DCO-signed change on
  `feature/chat-catalogue-api`, merged in PR #31 after user approval. No live
  provider quality, SMTP, reminders, deployment, navigation/UI changes or refresh
  restoration verification. Existing LangChain snapshot deprecation remains.
  Shared trusted-local ownership stays unchanged. Step 9 needs separate discussion.

### 9. Build Workspace chat navigation and restoration

- [x] Discuss, implement, and verify this slice after step 8.
- **Approved slice — 2026-10-08:** User approved native New chat/title-list
  navigation, explicit `chat` URL restoration, latest/empty startup, read-only
  history/inspector loading and recovery, locked navigation during running work,
  and a multiline composer with Send preserving per-chat unsent drafts in the
  browser session. Use documented design tokens/native sidebar adaptation while
  Figma inspection remains rate-limited. Verify two-chat isolation, refresh/backend
  restart, exact retained outcomes, failure recovery, keyboard/long-title/mobile
  behavior with automated and scripted-provider inline-browser checks. Keep the
  inspector and defer activity/events/Docs to later steps. Stack on open PR #31.
- **Problem/change:** Add New chat and a selectable titled chat list. Restore messages
  and activity on selection and refresh; keep technical IDs/configuration invisible.
  Ensure active selection and pending work follow the agreed switching policy.
- **Input → output:** Sidebar selection → the corresponding isolated conversation
  and follow-up context; New chat → a separate empty conversation.
- **Verify:** Create two chats, switch and continue each, refresh, restart the backend,
  and restore saved results without resubmission. Check long titles, empty history,
  retrieval failure, keyboard navigation, and mobile sidebar behavior.

#### Step 9 outcome — 2026-10-08

- **Implemented:** Native New chat and titled sidebar buttons, selected tint/check/
  text, literal truncated titles with full accessible labels, and update times in
  IST. Explicit `chat` URL selection restores ordered saved messages/outcomes and
  the unchanged inspector. Missing selection opens the latest chat; empty storage
  creates nothing until New chat or first Send. Unknown/invalid/repeated locators
  and unavailable reads block submission without displaying another chat's history.
- **Composer/execution:** User approved native multiline composer plus Send.
  Per-chat unsent text is retained in the current browser session after blur;
  New chat starts empty, and refresh may lose drafts. One queued message freezes
  its chat/message/turn ID, consumes the queue before HTTP and renders disabled
  navigation/composer/Send with Running feedback. Reads/rerenders never submit.
- **Recovery:** Lost replies restore committed matching records without duplicate
  local turns; unresolved absent outcomes block Send in that chat without retries.
  Running/unsaved markers lock navigation and submission, including after refresh.
  Known initial-save failures retain the draft and report no new execution; unsaved
  failures remain explicit until backend restart/interrupted recovery, which allows
  a new explicit turn. Check saved chat/Retry chat list only read. Read failures hide
  cached conversation/inspector content and never appear as empty success.
- **Verified:** All 939 tests (17 new navigation checks), `pip check` and whitespace
  checks pass. Final recovery wording/client-message changes passed 88 targeted
  navigation/UI/storage/catalogue regressions. Tests cover isolated context/drafts,
  URL refresh/restart/latest/empty selection, invalid/unknown links, creation/read/
  catalogue failures, running locks, interrupted continuation, initial/final save
  failures, lost/unknown replies, queued identity and literal long labels. Existing
  sentiment/keyword/FAQ/agent UI checks use the new composer and retain exact outcomes.
  Installed Streamlit 1.65.0 text-area/button APIs checked; no dependencies changed.
- **Browser:** Review app on 8505/backend 8016 uses scripted language providers
  with real classifier/VADER/runtime/API/storage. Created positive/negative chats,
  switched/restored an unsent draft, and continued each with its own prior result.
  An 18-second scripted follow-up showed disabled controls; refresh restored its
  running marker, then read-only recovery loaded completion without resubmission.
  Forced retrieval 503 hid history/inspector and recovered by reading. Backend restart
  plus refresh preserved all five saved turns byte-for-byte before a separate
  long-title check added one new explicit turn. Unknown-URL recovery was also checked.
  Desktop 1440 px/mobile 390 px checks verified title truncation/full accessible
  label, native sidebar/keyboard selection, 48 px targets, 2 px focus outline,
  stacked panels and no mobile horizontal overflow. Review app remains open.
- **Limits/delivery:** One user-authored DCO-signed change on
  `feature/workspace-chat-navigation` in PR #32. User approved merging on 2026-10-08;
  dependency PR #31 is merged and #32 now targets `main`. Figma inspection remains rate-limited;
  the user approved documented-token/native adaptation, not new Figma components.
  No live provider quality, SMTP/reminders, deployment, streaming/Activity/Docs,
  ownership/authentication, history budgeting or durable composer storage changes.
  Existing LangChain snapshot deprecation remains. Step 10 needs separate discussion.

### 10. Stream actual backend execution events

- [x] Discuss event contract/transport, implement and verify after steps 7–8.
- **Problem/change:** Emit ordered classification/routing and tool-start/tool-finish
  events during execution, followed by the actual final outcome. Discuss a compatible
  HTTP event-stream approach; do not choose a new external service.
- **Input → output:** One submitted turn → identifiable ordered events → one saved
  final outcome, with existing nonstreaming behavior preserved where needed.
- **Contract:** Correlate events to chat/turn/step, define sanitized event fields,
  completion/failure signals, persistence boundaries, and disconnect/recovery behavior.
  Progress streaming does not require token streaming or private reasoning output.
- **Verify:** Events arrive before completion using controlled delayed tools; ordering
  and failure traces are accurate. Cover disconnect and interrupted finalization.
  Reconnect/restoration must not replay execution; unknown outcomes never automatically
  retry. Keep events consistent with the persisted final results.

#### Step 10 agreed contract — 2026-10-08

- **Agreement:** User approved `POST /api/v1/chat/stream` using SSE alongside the
  unchanged nonstreaming endpoint. Emit actual classification/routing, workflow
  stages and agent model/tool start/finish activity, with versioned chat/turn/event
  sequence and step correlation. Include only validated inputs/results, sanitized
  failures and actual timings; never model content/reasoning or raw provider logs.
- **Persistence/recovery:** Progress events are transient. Send a saved terminal
  outcome only after SQLite finalization; report unsaved failure explicitly.
  Disconnect closes the subscription while backend work continues. Graceful shutdown
  drains disconnected work before releasing store ownership. Recovery reads the
  existing catalogue; duplicate IDs return saved outcomes without execution and
  unknown/interrupted turns never automatically retry. No event replay buffer,
  database migration, token streaming or new service/dependency.
- **Verification scope:** Controlled delayed-tool checks for genuine early delivery,
  ordering, fixed-workflow/agent handoff, retained successful/failed observations,
  final-result consistency, duplicate/conflicting IDs, input rejection, isolation,
  initial/final persistence failures, disconnect/shutdown and interrupted recovery.
  Follow automated checks with a local inline-browser API review and leave the
  existing Streamlit app open. Keep its inspector; live inline Activity is step 13.

#### Step 10 outcome — 2026-10-08

- Implemented context-scoped observable events in actual runtime/workflow/agent
  execution and `POST /api/v1/chat/stream` SSE transport. Events correlate version,
  chat/turn, sequence and start/finish step; validated tool data and existing trace
  timings match saved outcomes. Agent orchestration emits call status/timing without
  provider content. Fixed-workflow abstention retains extraction events before the
  actual agent handoff. Existing nonstreaming calls require no observer/signature change.
- Final outcomes are emitted only after the existing session save. Saved execution
  error/partial failure retains HTTP 503 semantics in terminal event data; validation
  remains HTTP 422, while conflicts/storage/runtime failures use sanitized terminal
  events after stream headers. Disconnect discards transient progress while retained
  workers continue once; graceful shutdown drains those workers before closing SQLite.
  Replays return only identity plus saved outcome, and recovery never repeats work.
- Verified all 955 tests (16 new), `pip check`, OpenAPI event-stream content type,
  and whitespace checks. Controlled real HTTP verifies start before tool release,
  durable running state, disconnect continuation, shutdown drain, and saved replay.
  Tests cover all three fixed workflows, agent handoff/failed tools/partial failure,
  presentation/extraction failures, clarification, invalid tool arguments, literal
  identities/frame safety, concurrent-chat isolation, initial/final persistence
  failures, interrupted recovery and saved/event equality. Two initial test setup
  errors (FAQ JSON normalization and argument-schema name) were corrected.
- Inline browser on backend 8017 verifies real classifier/VADER/SQLite with scripted
  LLM stages and a 10-second controlled tool: actual progress precedes completion,
  read-only running/finished recovery after disconnect, identical non-executing replay,
  and a full stream whose final payload equals saved history. Existing Streamlit
  chat/inspector on 8506 restores this record and completes an ordinary nonstreaming
  turn. Both review pages remain open; screenshot `/tmp/opsflow-step10-review.jpg`.
- Limits: no live Groq/model-quality, SMTP/inbox, forced process kill in this slice's
  browser review, deployed proxy/buffering or external-service checks. Existing
  history deprecation remains. No dependencies, storage migration, routing thresholds,
  reminder/email execution, production UI changes, token streaming, durable event
  replay or later-step implementation. Step 11 needs separate agreement. User
  approved merging PR #33 after review on 2026-10-08.

### 11. Move completed execution details into each chat turn

- [x] Discuss, implement, and verify this slice after steps 2–10.
- **Sequencing:** First verify the tool/routing and one-agent multi-step behavior,
  saved/restored outcomes, and backend execution-event contract. Keep the existing
  inspector available through steps 2–10 so those checks do not depend on this UI
  migration. Build inline details against the resulting contracts, then recheck
  representative outcomes in the new presentation.
- **Problem/change:** Remove the right-hand inspector and turn selector. Put the
  verified completed classification, confidence, route/reason, timings, and tool
  traces in a collapsed activity panel within each assistant response. Make individual
  tool sections expandable and associate them with their original turn.
- **Input → output:** Final and restored chat responses → conversation with optional
  per-turn execution details. Backend events are verified in step 10; live UI
  updates follow in step 13, and readable answer presentation follows in step 12.
- **Verify:** Direct, agent, no-tool, clarification, error, and partial-failure
  displays retain actual backend fields; old turns show their own details.
  Inspect collapsed/expanded layout, keyboard use, and mobile reading width.

#### Step 11 agreed contract — 2026-10-08

- User requested implementation and approved native collapsed Activity under each
  answer, with nested workflow/tool expanders and the existing Foundations styling.
  Remove the inspector/selector; retain final response presentation and nonstreaming
  submission. Stable turn keys associate panels with original saved outcomes.
- Verification scope: existing UI/navigation regression checks plus representative
  direct, agent/tool, no-tool, clarification, error and partial-failure restored
  outcomes; exact per-turn fields and read-only rerenders. Then inline-browser
  collapsed/expanded desktop/mobile, keyboard/focus, refresh and submission checks.
- Figma metadata remains blocked by the Starter tool-call limit. Document the
  approved native pattern without modifying Figma or expanding later-step scope.

#### Step 11 outcome — 2026-10-08

- Implemented native collapsed Activity inside each assistant response, with
  independently collapsed workflow/tool sections and stable saved-turn keys.
  Removed the inspector column/selector; retained exact classification, confidence,
  route/reasons, status, timings, arguments, results and failed-step details.
  Unknown/interrupted turns retain recovery messages without fabricated activity.
- Single conversation uses a 760 px desktop reading width; mobile expander padding
  uses the existing 8 px rhythm. Native summary controls have the 2 px focus outline.
  Updated design/console docs and project facts. Submission, API/storage and answer
  rendering remain unchanged; live activity and onboarding are later slices.
- Verified all 961 tests (six new restored-outcome cases), `pip check` and whitespace.
  Final assertion refinements passed 49 targeted UI/navigation tests. Real inline
  browser on existing review app 8506/backend 8017 verifies restored sentiment
  workflow/tool details, a new scripted-agent no-tool turn, independent turn panels,
  refresh, keyboard expansion/focus, desktop 1440 px and mobile 390 px with no
  horizontal overflow. Saved JSON is byte-identical before/after expansion/refresh.
  Desktop chat width is 760 px. Review app remains open. Screenshots:
  `/tmp/opsflow-step11-review.png`, `/tmp/opsflow-step11-mobile.png`.
- Limits: browser language stages are scripted; other outcome variants are covered
  by automated UI tests. No live provider/email, new dependencies, schema/routing,
  streaming-UI or deployment checks. Existing LangChain history deprecation remains.
  Figma inspection was rate-limited; native adaptation was explicitly approved.
  One user-authored DCO-signed change on `feature/rework-inline-activity`; user
  review/merge confirmation remains pending.

#### Step 11 sequential layout revision — 2026-10-08

- User clarified vertical sequencing with a sketch, then corrected alignment:
  prompt right, Activity below at left, then answer below at left. This supersedes the intermediate
  three-column interpretation and initial under-answer placement.
- Use native aligned containers capped at 560 px, shrinking on narrow viewports;
  the main area uses the existing 1440 px desktop reference. Keep turn association,
  collapsed details, exact records and existing answers/recovery behavior.
- Verify existing restored-outcome checks with separate prompt/details/answer
  containers, then browser vertical order/alignment, keyboard, mobile and refresh.
- Verified the layout correction with 49 UI/navigation checks and inline desktop
  1440 px/mobile 390 px order/alignment/no-overflow checks. Screenshot
  `/tmp/opsflow-sequential-layout.png`. The latest right-prompt/left-activity/left-answer
  alignment passes 49 UI/navigation checks and inline 1440 px positioning checks;
  screenshot `/tmp/opsflow-sequential-final-alignment.png`. Correction belongs
  to PR #34. The user also
  requested live sequential formation: take step 13 next, before step 12, as a
  separate stream-client/UI slice using actual step 10 events and saved terminal
  outcomes. No fabricated reasoning/token streaming or execution retry.

### 12. Present readable answers and onboarding

- [ ] Discuss, implement, and verify this slice after step 11.
- **12a approved — 2026-10-08:** Readable sentiment label beneath the existing
  grounded reply; exact scores/raw JSON remain in Activity. Preserve clarification,
  failure and retained-result presentation-failure behavior. Replace the quoted
  welcome syntax with previously verified natural-English sentiment, keyword and
  fictional FAQ examples. UI-only; keep execution/storage/layout unchanged.
  Verify representative success/clarification/failure/null results, non-executing
  restoration/rerenders and keyword/FAQ regressions, then desktop/mobile inline
  browser review. Remaining answer presentation requires a separate step 12b agreement.
- **Problem/change:** Render sentiment labels, keyword lists, FAQ answers/candidates,
  summaries, and email drafts as readable content. Keep raw structured detail in
  activity panels. Replace the syntax-heavy welcome example with natural-English
  examples based on behavior verified in steps 2–5; do not promise unsupported input.
  This presentation step follows inline activity so raw details have their intended
  location and verified backend output shapes guide the answer rendering.
- **Input → output:** Existing structured results/statuses → useful answers with
  clear clarification, failure, demo-policy, and draft/action distinctions.
- **Verify:** Representative outputs from each existing capability and absent/null
  results; no duplicated draft content or fabricated success. Use controlled data
  for display checks; generated wording should not be an exact test requirement.

#### Step 12a outcome — 2026-10-08

- **User-requested correction:** Right-align Send beneath the composer using a
  native container. All 79 UI/navigation/stream checks pass; inline desktop/mobile
  review confirms right alignment, a 48 px mobile target and no horizontal overflow.
  No new tests or CSS; submission/disabled behavior retains existing coverage.
  Added as a separate signed correction commit in PR #35. App stays open for review.
- **Implemented:** Direct/fixed-workflow sentiment answers show the saved label
  beneath the existing reply when available; exact scores/raw JSON stay in Activity.
  Retained scoring remains visible with the existing presentation-failure notice;
  absent/null results and clarification do not invent a label. Welcome examples use
  the previously verified natural-English sentiment/keyword/fictional FAQ requests.
  No backend, execution, storage, layout or other answer-presentation changes.
- **Verified:** All 991 tests pass, including six new restoration/onboarding cases
  and strengthened existing success/partial-failure assertions. Covers direct negative,
  fixed neutral, clarification, error and null results; exact saved scores remain
  in Activity, with no execution on restoration/rerender. Existing keyword/FAQ/agent
  regressions pass. `pip check` and whitespace checks pass; installed Streamlit 1.65.0
  text/info APIs checked without dependency changes.
- **Browser:** Existing inline review on 8506/backend 8018 confirms restored and
  newly submitted sentiment explanation/label, saved VADER scores in expanded
  Activity, refresh restoration, natural-English welcome, and 1440/390 px layouts.
  Mobile answer/welcome wrap without horizontal overflow. App remains open for
  independent review. Screenshots `/tmp/opsflow-step12a-desktop.jpg`,
  `/tmp/opsflow-step12a-mobile.jpg`, `/tmp/opsflow-step12a-welcome-mobile.jpg`.
- **Limits/delivery:** Scripted language stages with real classifier/VADER/HTTP/
  SQLite; no new live-provider quality or email checks. Figma is still rate-limited;
  existing documented native text styling retained. Existing LangChain history
  deprecation remains. Scoped DCO-signed change on
  `feature/readable-sentiment-onboarding`, stacked on the unmerged step 13 branch;
  merge awaits user review. Step 12b needs separate agreement.

### 13. Connect live events to collapsible chat activity

- [x] Discuss, implement, and verify this slice after steps 9–11; user requested
  it before step 12.
- **Problem/change:** Replace the generic wait with compact in-chat progress. Update
  classification, route, and expandable tool steps as events arrive; leave the
  final answer readable outside the collapsed detail.
- **Input → output:** Live events → running/completed/failed step states and final
  answer → the same meaningful activity when replayed from saved history.
- **Verify:** Observe live direct and controlled multi-step requests; steps appear
  during work, failures retain successful observations, and rerenders do not duplicate
  turns or execution. Check expansion usability, disconnect messaging, restored
  history, keyboard accessibility, and mobile layout.

#### Step 13 sequential live activity contract — 2026-10-08

- User explicitly requested visible formation during execution, like thinking-model
  activity, before the answer. Take this bounded stream hookup before step 12;
  final-answer/onboarding rendering stays unchanged.
- One consumed submission uses the existing POST SSE endpoint and frozen turn ID.
  Prompt appears right immediately; left native Activity starts open with a stable
  running header and adds expandable stage data from actual classification/routing/start/finish
  events. Display the answer below at left only after a saved terminal outcome.
- Validate event version, correlation, contiguous sequence, step pairing and final
  execution/status. No provider text/private reasoning, synthetic delays or token
  typing. Progress is transient; the restored panel uses exact saved records.
- Terminal failures, invalid stream and disconnect keep existing safe read-only
  recovery. Never reconnect/resubmit automatically. Interrupted UI reruns recover
  a consumed turn by GET; navigation/submission remain locked during running or
  uncertain work. No backend/storage/provider/dependency change.
- Verification: real-API AppTest regressions, incremental consumption, malformed/
  mismatched events, retained partial results, terminal save failures, transport
  interruption and consumed-rerun recovery; then delayed inline browser progress
  before answer, multi-step/failure, refresh/recovery, desktop/mobile and keyboard.
- Implemented on `feature/rework-live-activity`, stacked on open step 11 PR #34.

#### Step 13 outcome — 2026-10-08

- Added one-shot validated SSE consumption in `app/ui_stream.py`, selected by the
  UI client's optional progress callback. Nonstreaming callers retain their API.
  UI displays a right prompt, then left running Activity with actual stage events,
  then the left answer after a saved final outcome. Live Activity starts open with
  a stable header; stage sections can expand without label updates resetting them.
  Completed details collapse and use exact saved records, not transient progress.
- Validates event version/identity/sequence, SSE fields, step pairing, terminal
  status/outcome and final execution schema. Invalid/disconnected streams and
  terminal failures use sanitized errors and existing GET recovery, never automatic
  retry/reconnect. Interrupted subscriber reruns recover consumed frozen turns.
- Verified the 983-test full suite, then 73 focused UI/navigation/stream checks
  after final header/recovery refinements (24 new stream/recovery cases overall).
  Dependency and whitespace checks pass. Existing history deprecation remains.
- Inline browser on 8506/backend 8018 uses scripted providers/compound routing,
  delayed real VADER/YAKE/FAQ, HTTP and SQLite. Observed sentiment workflow and
  three sequential agent tools, live successful observations before any answer,
  keyboard expansion, refresh during work with locked read-only recovery, one
  stream POST per submitted turn, and retained-result agent partial failure.
  Recovered JSON remains byte-identical after inspection. Desktop 1440 px/mobile
  390 px checks verify right prompt/left activity/left answer and no overflow;
  summary focus is 2 px. Review app stays open.
- Screenshots `/tmp/opsflow-step13-live-final.png` and
  `/tmp/opsflow-step13-mobile.png`. Browser language stages and compound gate are
  scripted; direct/restored and other failure variants are automated UI checks.
  No live provider quality, SMTP, proxy/deployment, token streaming, backend/schema,
  event journal or dependency changes. Figma remains rate-limited; user-specified
  native adaptation is documented. User review/merge confirmation remains pending.

### 14. Add the in-app Docs guide

- [ ] Discuss content/navigation, then implement and verify this slice.
- **Problem/change:** Add Docs near the lower sidebar, opening a readable guide while
  preserving the active chat. Keep maintained usage content in repository docs.
- **Input → output:** Docs selection → organized tool/capability guides with purpose,
  necessary information, ordinary-English examples, expected output shape, limitations,
  clarification/failure examples, and actual availability.
- **Coverage:** Sentiment, keywords, demo FAQs, summaries, drafting, and the current
  reminder/notification limitations. Explain single requests, direct deterministic
  execution, single agentic requests, and one-agent multi-step workflows. "Single"
  describes task count; "deterministic/agentic" describes execution and can overlap.
- **Verify:** Walk through every published example against supported behavior with
  controlled fixtures and agreed manual checks. Mark unavailable features clearly;
  never document future reminder sending as currently working. Check navigation,
  readability, lower-sidebar placement, and unchanged chat state on return.

### 15. Verify the complete rework and hand back to the original plan

- [ ] Review completion evidence, reconcile documentation, and record handover.
- **Input → output:** Implemented rework slices → verified user journeys and an
  accurate original-plan backlog reflecting the new UI, persistence, and streaming.
- **Verify:** Run relevant regression/dependency checks for the final implementation;
  inspect the desktop/mobile UI and the end-to-end journeys below. Use offline
  provider/email doubles for automated checks. Report live-provider/SMTP/deployment
  limitations explicitly; do not rerun identical checks without a new concern.
- **Handover:** Once all criteria pass, mark this plan complete, update `AGENTS.md`
  and `docs/agents_doc.md`, remove the original plan's pause, and reconcile its
  outdated architecture/status before discussing its next remaining slice.

## Completion Criteria

- [x] Deploy and the redundant console caption are absent from the user interface;
  Workspace contains no visible session ID, storage path, or backend configuration.
- [ ] New chat, a list of independent sessions, selection, continuation, refresh,
  and application-restart restoration work without mixing context or rerunning turns.
- [ ] Normal English works across the available capabilities without required command
  punctuation; ambiguous/missing inputs clarify and safe direct routing is preserved.
- [ ] One agent executes supported multi-step requests in dependency order, retains
  partial results, and honestly explains limits, failures, and unavailable actions.
- [ ] The separate inspector is gone. Actual progress appears during execution inside
  each response, collapsed by default with expandable details and saved-history replay.
- [ ] Answers are readable, demo policies remain qualified, and draft/user actions
  remain separate; no misleading sending/delivery/completion claims are introduced.
- [ ] Docs is reachable near the lower sidebar and covers tools, natural-language
  examples, outputs, execution types, and limitations matching verified behavior.
- [ ] Relevant checks and reviewed desktop/mobile journeys are recorded. Design-system
  gaps and material contract decisions are resolved in the corresponding slices.
- [ ] All numbered steps are verified or explicitly revised with the user; the
  original plan resumes only after the recorded completion and handover.

## Decision and Verification Record

- **2026-10-08:** User authorized merging FAQ PR #26 and its required standalone
  dependency. PR #25 merged into `main` with a user-authored signed merge message;
  PR #26 retargeted to `main`. Implementation and caption checks remain the recorded
  855-test regression run and 26 UI checks; this delivery record changes only docs.
  Confirm current heads, DCO, and mergeability before the integration merge. Step 4
  remains a separate discussion; the original plan stays paused.

- **2026-10-08:** User requested removing the fixed demo-policy verification
  caption. Removed both chat render locations and updated existing FAQ UI coverage
  and documentation. All 26 current UI checks and whitespace checks pass; underlying
  data/model replies/inspector records are unchanged. Scoped signed correction in
  existing integration PR #26; no later rework implementation.

- **2026-10-07:** Completed approved FAQ chat step 3d and bounded agent-policy
  clarification correction. All 855 tests (22 new), dependency and whitespace
  checks pass. Limited live HTTP review confirmed workflow routing and corrected
  fresh/post-draft contractor clarifications after an initial eligibility error.
  Recorded that model-quality limitation; preserved classifier/FAQ-only contracts.
  Step 3 is complete within recorded bounds; step 4 requires separate discussion.

- **2026-10-07:** Completed approved standalone FAQ step 3c with retained exact
  policies, grounded presentation/coverage clarification, and bounded failure
  handling. All 833 tests (47 new), dependency and whitespace checks pass; installed
  adapter exercised offline. No live quality review or chat integration; step 3d
  is the next discussion.

- **2026-10-07:** User approved the proposed first FAQ slice, recorded as step 3c:
  standalone question extraction → existing retrieval → grounded explanation with
  retained exact policy, offline verification, and explicit abstention/failure
  handling. Chat integration and live language-quality review remain separate.

- **2026-10-07:** Reviewed the user's FAQ architecture diagram against the existing
  local retriever, classifier, routing gate, and agent contracts. Recorded the
  unapproved step-3 FAQ proposal above and split standalone/integration delivery.
  Seven local read-only probes exposed lexical coverage and classifier limitations;
  checked primary scikit-learn/Groq documentation. Presentation choice and final
  contract were open at that review and then resolved for step 3c. The review
  changed no application code and made no live provider calls.

- **2026-10-07:** User authorized merging PR #24, including standalone keywords,
  classifier-first chat integration, and the introduction/score-table correction.
  Verified the tested application head, clean mergeability, user-only authorship,
  all commit DCO sign-offs, and passing DCO. This delivery-record update changes
  documentation only; existing 786-test evidence applies to unchanged code/tests.
  FAQ remains the next discussion; no further implementation is authorized.

- **2026-10-07:** User authorized merging both sentiment slices. Merged standalone
  PR #22, retargeted integration PR #23 to `main`, and updated dependency/delivery
  records before its authorized merge. Verified user-only authorship, DCO sign-offs,
  passing DCO checks, and unchanged application/test files against the tested 2b
  commit. Documentation-only delivery update; no new runtime tests or provider calls.

- **2026-10-07:** User requested step 2b and selected the `llm_assisted` API route
  with existing status rules. Completed classifier-first chat wiring, retained
  workflow/tool/history records, and inspector compatibility. All 721 tests,
  dependency checks, and whitespace checks pass within the limits above. Step 3
  is the next discussion; later implementation remains unapproved.

- **2026-10-07:** User approved completing step 2a after confirming classifier-first
  dispatch. Implemented the standalone workflow and documented its contract and
  boundaries. All 709 tests, dependency checks, and whitespace checks pass; see the
  outcome above. Step 2b remains the next discussion; no live provider quality checks.

- **2026-10-07:** Planned the user's LLM extraction → deterministic scoring → LLM
  explanation proposal as step 2a (standalone sentiment workflow), then step 2b
  (separately agreed chat integration). Recorded source validation, abstention,
  retained-result failure handling, proportional tests, and the proposed routing-rule
  exception. Reviewed current sentiment/router/runtime/session/API/provider code and
  documentation whitespace. No application changes, runtime tests, provider calls,
  compatibility verification, or implementation approval in this planning change.

- **2026-10-07:** User deferred the former step 2 (inline completed execution
  details) until tool/agent behavior, persistence, and backend events are verified;
  it is now step 11. Moved its dependent readable-answer step to step 12, before
  live activity in step 13. Renumbered the intervening steps and dependencies;
  the next discussion is natural-English sentiment (step 2). This order change
  does not authorize implementing those slices or expand reminder/email scope.
  User initially requested an uncommitted edit directly on `main`, then authorized
  a signed commit and direct push to `main` without a new PR after review.
  Reviewed sequence/dependency references and
  documentation whitespace; no application changes or runtime tests.

- **2026-10-07:** User approved step 1. Implemented and verified the interface
  cleanup with 18 existing UI checks and local desktop/mobile/direct/pending/failure
  browser checks; see the recorded outcome above. Later slices remain discussion only.

- **2026-10-07:** User clarified that sections are individual chat sessions, and
  multiple tasks require a multi-step process with one agent. Agreed chats should
  survive refresh/application restart. Authorized creation of this plan and explicit
  suspension of the original agenda. No application changes authorized by this
  documentation step; implementation contracts/tests are discussed one slice at a time.
- **2026-10-07:** Checked this planning change for discussion coverage, step ordering,
  local document links, and whitespace. Application behavior, persistence, natural-
  language quality, and streaming remain unimplemented/unverified by this change.
