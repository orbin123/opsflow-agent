# OpsFlow Rework Plan

Agreed direction: 2026-10-07. `REWORK.md` is the active agenda until the completion
criteria below are verified. The original `docs/PLAN.md` agenda is paused; do not
use it or `agenda.txt` to decide or order work. Resume the original plan only
after the recorded rework handover.

**Status:** Step 1 implemented and verified. Remaining rework steps are pending.
**Next discussion:** ⏳ Step 2, completed execution details within each chat turn.

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
  use the agent; missing material information requires clarification.
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

### 2. Move completed execution details into each chat turn

- [ ] Discuss, implement, and verify this slice.
- **Problem/change:** Remove the right-hand inspector and turn selector. Put the
  existing completed classification, confidence, route/reason, timings, and tool
  traces in a collapsed activity panel within each assistant response. Make individual
  tool sections expandable and associate them with their original turn.
- **Input → output:** Existing final chat response → readable conversation with
  optional per-turn execution details. Live streaming comes in steps 12–13.
- **Verify:** Direct, agent, no-tool, clarification, error, and partial-failure
  displays retain actual backend fields; old turns show their own details.
  Inspect collapsed/expanded layout, keyboard use, and mobile reading width.

### 3. Present readable answers and onboarding

- [ ] Discuss, implement, and verify this slice.
- **Problem/change:** Render sentiment labels, keyword lists, FAQ answers/candidates,
  summaries, and email drafts as readable content. Keep raw structured detail in
  activity panels. Replace the syntax-heavy welcome example with natural-English
  examples; do not promise input behavior before subsequent steps verify it.
- **Input → output:** Existing structured results/statuses → useful answers with
  clear clarification, failure, demo-policy, and draft/action distinctions.
- **Verify:** Representative outputs from each existing capability and absent/null
  results; no duplicated draft content or fabricated success. Use controlled data
  for display checks; generated wording should not be an exact test requirement.

### 4. Accept natural-English sentiment requests

- [ ] Discuss, implement, and verify this slice.
- **Problem/change:** Remove punctuation dependence for clearly extractable requests.
  Review classifier predictions separately from argument extraction; retain agent
  interpretation/clarification where source boundaries are uncertain.
- **Input → output:** `Just check the sentiment of this I am happy` → source
  `I am happy` → sentiment result. The same intent with quotes/colon stays valid.
- **Verify:** Representative unquoted/quoted wording, negation, multiline source,
  missing source, uncertain boundaries, contextual references, compound requests,
  and commands embedded in source text. Distinguish parsing failure from classifier
  error; do not change thresholds or retrain without a discussed need and evaluation.

### 5. Review natural-English keyword and FAQ requests

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

### 6. Verify conversational summarization and drafting

- [ ] Discuss, implement fixes if needed, and verify this slice.
- **Problem/change:** Audit source extraction, writing instructions, and follow-up
  handling for the remaining available tools; fix demonstrated failures only.
- **Input → output:** `Summarize this The outage lasted 20 minutes and is resolved`
  → summary; `Draft an email to Alex saying the outage is resolved` → draft and
  separate user actions; missing recipient/facts → clarification.
- **Verify:** Standalone and contextual requests, clarification answers, source
  preservation, demo-policy qualification, and unavailable sending/reminder requests.
  Use provider doubles in tests; agree separately on any limited live quality checks.

### 7. Verify one-agent multi-step requests

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

### 8. Agree on persistent-chat and navigation contracts

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

### 9. Implement durable chat history and runtime restoration

- [ ] Discuss, implement, and verify this slice after step 8.
- **Problem/change:** Store chat metadata, messages, execution records, and finalized
  outcomes durably. Reconstruct the context consumed by the existing agent from saved
  direct/agent outcomes without appending turns twice or changing reminder behavior.
- **Input → output:** Chat turns → durable records → restored conversational context.
  Persist incomplete work with an explicit state rather than fabricating completion.
- **Verify:** Fresh-process restoration, direct-to-agent follow-ups, independent chats,
  failed/partial turns, write failures, ordering, and existing same-session serialization.
  Prevent silent memory/disk divergence and disclose known persistence failure.

### 10. Expose chat creation, listing, and retrieval

- [ ] Discuss, implement, and verify this slice after step 9.
- **Problem/change:** Add only the backend contracts needed for New chat, a chat list,
  and loading saved turns; adapt the HTTP client. Apply the ownership decision from
  step 8. Reading history must not execute tools or submit provider calls.
- **Input → output:** Create/list/load requests → stable internal chat IDs, titles,
  ordered saved messages, outcomes, and activity detail.
- **Verify:** Empty list, create/list/load round-trip, unknown chat, restart recovery,
  invalid input, sanitized storage failures, and access boundaries where applicable.
  Preserve existing chat submission and FAQ contracts unless an agreed change requires
  an explicit compatibility update.

### 11. Build Workspace chat navigation and restoration

- [ ] Discuss, implement, and verify this slice after step 10.
- **Problem/change:** Add New chat and a selectable titled chat list. Restore messages
  and activity on selection and refresh; keep technical IDs/configuration invisible.
  Ensure active selection and pending work follow the agreed switching policy.
- **Input → output:** Sidebar selection → the corresponding isolated conversation
  and follow-up context; New chat → a separate empty conversation.
- **Verify:** Create two chats, switch and continue each, refresh, restart the backend,
  and restore saved results without resubmission. Check long titles, empty history,
  retrieval failure, keyboard navigation, and mobile sidebar behavior.

### 12. Stream actual backend execution events

- [ ] Discuss event contract/transport first, then implement and verify this slice.
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

### 13. Connect live events to collapsible chat activity

- [ ] Discuss, implement, and verify this slice after steps 11–12.
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

- **2026-10-07:** User approved step 1. Implemented and verified the interface
  cleanup with 18 existing UI checks and local desktop/mobile/direct/pending/failure
  browser checks; see the recorded outcome above. Step 2 remains discussion only.

- **2026-10-07:** User clarified that sections are individual chat sessions, and
  multiple tasks require a multi-step process with one agent. Agreed chats should
  survive refresh/application restart. Authorized creation of this plan and explicit
  suspension of the original agenda. No application changes authorized by this
  documentation step; implementation contracts/tests are discussed one slice at a time.
- **2026-10-07:** Checked this planning change for discussion coverage, step ordering,
  local document links, and whitespace. Application behavior, persistence, natural-
  language quality, and streaming remain unimplemented/unverified by this change.
