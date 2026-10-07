# OpsFlow Rework Plan

Agreed direction: 2026-10-07. `REWORK.md` is the active agenda until the completion
criteria below are verified. The original `docs/PLAN.md` agenda is paused; do not
use it or `agenda.txt` to decide or order work. Resume the original plan only
after the recorded rework handover.

**Status:** Steps 1 and 2 (2a/2b) implemented and verified within their recorded limits.
Keyword steps 3a/3b are implemented and verified offline; FAQ and remaining
rework steps are pending.
**Next discussion:** ⏳ Step 3 FAQ review. Keyword steps 3a/3b are in PR #24.

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

Preserve these contracts throughout the rework:

- Direct execution needs a high-confidence, single-purpose request and reliable
  argument extraction. Ambiguous, contextual, compound, and LLM-dependent requests
  use the agent, except the approved fixed high-confidence sentiment/keyword workflows,
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

- [ ] Discuss, implement, and verify this slice; split by capability if needed.
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

### 4. Verify conversational summarization and drafting

- [ ] Discuss, implement fixes if needed, and verify this slice.
- **Problem/change:** Audit source extraction, writing instructions, and follow-up
  handling for the remaining available tools; fix demonstrated failures only.
- **Input → output:** `Summarize this The outage lasted 20 minutes and is resolved`
  → summary; `Draft an email to Alex saying the outage is resolved` → draft and
  separate user actions; missing recipient/facts → clarification.
- **Verify:** Standalone and contextual requests, clarification answers, source
  preservation, demo-policy qualification, and unavailable sending/reminder requests.
  Use provider doubles in tests; agree separately on any limited live quality checks.

### 5. Verify one-agent multi-step requests

- [ ] Discuss, implement fixes if needed, and verify this slice.
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

### 6. Agree on persistent-chat and navigation contracts

- [ ] Discuss and record the contract before storage/UI implementation.
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

### 7. Implement durable chat history and runtime restoration

- [ ] Discuss, implement, and verify this slice after step 6.
- **Problem/change:** Store chat metadata, messages, execution records, and finalized
  outcomes durably. Reconstruct the context consumed by the existing agent from saved
  direct/agent outcomes without appending turns twice or changing reminder behavior.
- **Input → output:** Chat turns → durable records → restored conversational context.
  Persist incomplete work with an explicit state rather than fabricating completion.
- **Verify:** Fresh-process restoration, direct-to-agent follow-ups, independent chats,
  failed/partial turns, write failures, ordering, and existing same-session serialization.
  Prevent silent memory/disk divergence and disclose known persistence failure.

### 8. Expose chat creation, listing, and retrieval

- [ ] Discuss, implement, and verify this slice after step 7.
- **Problem/change:** Add only the backend contracts needed for New chat, a chat list,
  and loading saved turns; adapt the HTTP client. Apply the ownership decision from
  step 6. Reading history must not execute tools or submit provider calls.
- **Input → output:** Create/list/load requests → stable internal chat IDs, titles,
  ordered saved messages, outcomes, and activity detail.
- **Verify:** Empty list, create/list/load round-trip, unknown chat, restart recovery,
  invalid input, sanitized storage failures, and access boundaries where applicable.
  Preserve existing chat submission and FAQ contracts unless an agreed change requires
  an explicit compatibility update.

### 9. Build Workspace chat navigation and restoration

- [ ] Discuss, implement, and verify this slice after step 8.
- **Problem/change:** Add New chat and a selectable titled chat list. Restore messages
  and activity on selection and refresh; keep technical IDs/configuration invisible.
  Ensure active selection and pending work follow the agreed switching policy.
- **Input → output:** Sidebar selection → the corresponding isolated conversation
  and follow-up context; New chat → a separate empty conversation.
- **Verify:** Create two chats, switch and continue each, refresh, restart the backend,
  and restore saved results without resubmission. Check long titles, empty history,
  retrieval failure, keyboard navigation, and mobile sidebar behavior.

### 10. Stream actual backend execution events

- [ ] Discuss event contract/transport first, then implement and verify this slice
  after steps 7–8.
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

### 11. Move completed execution details into each chat turn

- [ ] Discuss, implement, and verify this slice after steps 2–10.
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

### 12. Present readable answers and onboarding

- [ ] Discuss, implement, and verify this slice after step 11.
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

### 13. Connect live events to collapsible chat activity

- [ ] Discuss, implement, and verify this slice after steps 9–12.
- **Problem/change:** Replace the generic wait with compact in-chat progress. Update
  classification, route, and expandable tool steps as events arrive; leave the
  final answer readable outside the collapsed detail.
- **Input → output:** Live events → running/completed/failed step states and final
  answer → the same meaningful activity when replayed from saved history.
- **Verify:** Observe live direct and controlled multi-step requests; steps appear
  during work, failures retain successful observations, and rerenders do not duplicate
  turns or execution. Check expansion usability, disconnect messaging, restored
  history, keyboard accessibility, and mobile layout.

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
