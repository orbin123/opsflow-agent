# Agent Change Record

Keep entries brief: date, completed change, verification, and any changed decision. Track actual work rather than restating the plan.

- **2026-10-09:** Approved bounded model rate-limit waiting for the failed four-tool
  demo. Reproduced Groq's 8,000 TPM rejection after sentiment/keywords and a
  19-second retry header. Added one rejected-request retry with an observable wait
  under the existing shared agent deadline, including nested summary/draft calls;
  no tool/turn replay. All 1,102 tests pass in a clean committed-code copy plus
  this fix (12 new); current dirty-tree run has 1,100 passes/two unrelated existing
  welcome-screen test failures. Dependency/whitespace checks pass. Exact live
  four-tool demo in the original chat completed in 100.07 seconds after five
  observed waits; each tool completed once and original failure is retained.
  Existing unrelated demo label/draft factual-quality issues remain documented.
  App stays open; ⏳ user review/merge pending. No email sent.

## Active Agenda — Rework First

From 2026-10-07 until all completion criteria in [REWORK.md](../REWORK.md) are
verified, the original `docs/PLAN.md` agenda is halted. Do not use that plan or
`agenda.txt` to decide the next work. Discuss and complete one bounded rework
step at a time, updating `REWORK.md` and this record in the same logical change.
Only after rework completion, reconcile the original plan, record the handover,
and continue its remaining work. Earlier next-step notes below are historical.

- **2026-10-08:** User replaced the standalone Docs entry with bottom-left Settings
  offering Docs, Emails and Reminders, and requested the saved-work pages after
  the current PR. Revised step 14 into separate Settings/Docs, saved-draft and
  reminder-page slices; recorded chat-reminder creation/delivery as a dependency
  requiring explicit scope agreement. Docs includes demo prompts for all five
  current chat tools. Documentation-only proposal; whitespace checks pass.

- **2026-10-08:** Added step 14's proposed implementation contract to `REWORK.md`:
  maintained local user guide, capability/execution coverage, read-only Docs/return
  navigation preserving chat/draft state, proposed running/unsaved entry locks,
  design decisions and proportional verification. Proposal awaits agreement;
  no application code or runtime behavior changed. Reviewed the scoped documentation
  diff and checked whitespace. Remaining step 12b stays deferred before handover.

- **2026-10-08:** Implemented approved step 14a Settings/Docs: bottom-left native
  menu, maintained guide with five tool demos and a compound example, preserved
  chat/draft state, entry locks, recovery from work detected in another tab and
  sanitized content failure. All 1,052 tests (15 new), dependency/whitespace checks
  pass. Inline review on 8509/backend 8020 verifies 1440/390 px menu/guide layout,
  keyboard interaction and multiline draft restoration without new execution.
  Six examples use scripted language stages and real routing/local tools; no live
  model quality/email/deployment checks. Figma remains rate-limited. Review app
  stays open; draft PR #40 on `feature/settings-docs-guide` awaits user confirmation
  before merge. User-only authorship/sign-off verified; Emails/Reminders remain next slices.

- **2026-10-09:** Implemented approved step 14c read-only Reminders page and GET
  catalogue/client with actual persisted states, literal tasks and recorded-zone
  due times. Missing storage is empty; invalid storage/records fail safely without
  repair or partial success. All 1,090 tests (18 new), dependency/whitespace checks
  pass; 141 final focused regressions pass after styling correction. Inline isolated
  8511/8021 review covers 1440/390 px cards/focus/wrapping,
  Refresh/Return, multiline draft preservation and no overflow. Corrected card CSS
  selectors found in browser review. Fixtures only; no worker/provider/SMTP calls,
  schema/dependency or chat integration changes. Figma remains rate-limited. Signed
  `feature/saved-reminders` stacks on Emails PR #41; app open, merge awaits review.

- **2026-10-09:** User authorized merging all open PRs after review. Reviewed
  current heads/scoped diffs and existing 1,090-test/141-focused/browser evidence;
  no blocking finding. User-only authorship, matching sign-offs and passing DCO
  verified. Merged Settings/Docs #40 and Emails #41 in dependency order; Reminders
  #42 now targets `main` with explicit merge authorization. Documentation-only
  delivery update; no repeated runtime checks or provider/email execution.

**Next:** ⏳ Discuss remaining step 12b presentation and separately scope chat
reminder creation/delivery before final handover. The original plan stays paused.

- **2026-10-08:** Implemented approved step 14b read-only saved Emails page using
  existing GET records: distinct successful draft observations, compound/partial
  outcomes, saved actions/literal content, contextual demo flags and source navigation.
  Preserves composer drafts; refresh reflects rename/delete and reports read/record
  failures honestly. Full 1,071-test regression plus final 138 focused checks pass
  (20 new overall; 1,072 collected), dependency/whitespace pass. Inline 8510/8020
  review verifies desktop/mobile wrapping, keyboard context/focus, source-chat
  navigation and multiline composer restoration; fixture log unchanged at five calls.
  Scripted backend; no live model quality/email/deployment verification. Foundations
  metadata inspected; detailed Figma context remains limited. Separate signed branch
  `feature/saved-email-drafts` in draft PR #41 stacks on PR #40; app open, merge
  awaits user review.
The initial Docs discussion was requested in a new chat
on 2026-10-08. Remaining step 12b presentation is deferred, not complete, and
must be revisited before the rework handover. User approved
merging Workspace PR #38 and summary dependency PR #37 on 2026-10-08;
PR #37 is merged and #38 now targets `main`. User approved
merging step 12a PR #35 on 2026-10-08; step 13 is merged in dependency PR #36.
Step 11 is merged in PR #34.
Step 7 PR #30 and contract dependency PR #29 are merged after user approval.
Step 7 storage/restoration is implemented and verified within its recorded limits.
Step 6's contract is
recorded and reviewed in [persistent-chat-contract.md](persistent-chat-contract.md).
Step 4 merged in PR #27;
step 5 is verified within the recorded offline/scripted-browser limits, and user
approved merging PR #28 on 2026-10-08. Original plan stays paused; later
implementation awaits discussion.

- **2026-10-08:** User approved merging single-draft PR #39 and chose step 14
  Docs discussion in a new chat next. Verified current implementation head,
  user-only authorship/matching DCO sign-off and passing DCO. Recorded remaining
  step 12b presentation as deferred until before final handover. Documentation-only
  approval/agenda update; prior 1,037-test/browser evidence remains applicable.

- **2026-10-08:** Implemented approved step 12b single-draft presentation: saved
  recipient/subject/literal multiline body shown once, separate saved actions,
  raw JSON in Activity and preserved contextual demo qualification. Failure,
  clarification, compound and malformed-result replies retain their presentation.
  All 1,037 tests (15 new), dependency and whitespace checks pass. Inline review
  on 8508/backend 8020 verifies desktop/mobile wrapping, submission/refresh,
  Activity JSON, qualification and clarification; two submitted drafts remain two
  drafting calls after inspection/restoration. Scripted providers; no live model
  quality, semantic contextual drafting or email checks. Figma remains rate-limited;
  native styling retained and existing LangChain deprecation remains. Review app
  stays open; user approved merging PR #39 on `feature/readable-single-draft`.

- **2026-10-08:** User approved merging Workspace PR #38 and summary dependency
  PR #37 after inline review. Verified current heads, user-only authorship/sign-offs
  and passing DCO; merged #37 and retargeted #38 to `main`. This delivery record
  changes documentation only; prior 1,022-test/browser evidence remains applicable.

- **2026-10-08:** Implemented user-approved Workspace Rename/Delete: themed
  right-click/More actions menu, native styled dialogs, persistent custom titles,
  SQLite v1→v2 migration, transactional deletion/context cleanup, and protected
  PATCH/DELETE/client contracts. All 1,022 tests (21 new), dependency/whitespace
  checks pass. Inline browser on 8507/backend 8019 verifies both menu entry paths,
  keyboard/focus, literal rename, refresh/restart, deletion confirmation/cancel,
  and 1440/390 px themed layouts without overflow. Confirmed deletion/selected
  recovery covered by AppTest/API; no permanent browser delete click. Management
  calls no providers/tools; existing scripted summary counts remain unchanged.
  Figma remains rate-limited; approved adaptation documented. Review app stays
  open; signed branch `feature/workspace-chat-management` stacks on summary
  PR #37; user approved both merges and #38 now targets `main`. No live-provider/email checks.

- **2026-10-08:** Implemented the user-approved step 12b single-summary slice:
  completed single-summary agent turns show saved summary/key points once;
  empty points omit the section, raw records stay in Activity, and fallback/
  compound/draft replies retain their presentation. All 1,001 tests (10 new),
  dependencies and whitespace checks pass. Inline browser on 8507/backend 8019
  verifies literal multiline output, Activity JSON, empty points, non-executing
  refresh and 1440/390 px wrapping without mobile overflow. Scripted providers,
  real classifier/tool validation/HTTP/SSE/SQLite; no live-provider/email checks.
  Figma remains rate-limited; native styling retained. Review app stays open;
  scoped signed change on `feature/readable-single-summary` is merged as PR #37
  after user approval. Other step 12b presentation remains separately agreed work.

- **2026-10-08:** User approved merging step 12a PR #35. Verified user-only
  authorship, matching sign-offs and passing DCO; merged step 13 dependency PR #36,
  retargeted #35 to `main` and marked it ready. Documentation-only delivery record;
  application verification remains unchanged. Step 12b still needs separate agreement.

- **2026-10-08:** User requested removal of the sidebar draft/reminder/email
  limitation caption in PR #35; capability boundaries and draft actions stay unchanged.
  All 38 UI checks pass; inline browser confirms removal and usable chat controls.

- **2026-10-08:** At the user's request, right-aligned Send beneath the composer
  with a native container in PR #35. All 79 UI/navigation/stream checks pass;
  inline desktop/mobile review confirms alignment, a 48 px target and no mobile
  overflow. Existing submission/disabled checks retained; no new tests or CSS.
  App remains open for review; merge still awaits confirmation.

- **2026-10-08:** Implemented approved step 12a: direct/fixed-workflow sentiment
  shows the existing reply and saved label; exact scores/JSON remain in Activity.
  Welcome uses verified natural-English sentiment, keyword and fictional FAQ
  examples. All 991 tests pass (six new restoration/onboarding cases, strengthened
  success/partial-failure assertions), plus dependencies/whitespace. Inline review
  on 8506/backend 8018 confirms restored/new sentiment, saved scores in Activity,
  refresh and 1440/390 px answer/welcome wrapping without mobile overflow. Scripted
  language stages; real classifier/VADER/HTTP/SQLite. Figma remains rate-limited;
  native styling retained. No backend/dependency/layout or live-provider/email changes.
  Scoped signed change on `feature/readable-sentiment-onboarding`, stacked on step 13;
  app stays open and merge awaits user review. Step 12b requires separate agreement.

- **2026-10-08:** Implemented user-requested step 13 before step 12: one consumed
  SSE submission shows a right prompt, left live Activity, then left saved answer.
  Strict identity/sequence/step/final validation, sanitized failures and read-only
  recovery prevent automatic resubmission; interrupted UI reruns recover by GET.
  Live header stays stable to preserve expansion, with actual observable stages.
  Full 983-test suite and final 73 focused checks pass (24 added stream/recovery
  cases overall), plus dependencies/whitespace. Inline 8506/backend 8018 review
  confirms workflow and three-tool live progress before answer, refresh/recovery,
  exactly one POST per turn, retained-result partial failure, keyboard focus and
  1440/390 px layout without overflow. Providers/compound gate are scripted;
  VADER/YAKE/FAQ/HTTP/SQLite are real. App stays open; merge awaits user review.
  No live provider/email, backend/schema, event journal, token streaming or
  dependencies/deployment changes. Existing history deprecation remains. Screenshots
  `/tmp/opsflow-step13-live-final.png`, `/tmp/opsflow-step13-mobile.png`.

- **2026-10-08:** User corrected alignment to right user prompt and left Activity/
  assistant answer, retaining vertical sequencing and live formation request.
  Apply to step 11 PR #34 before the separate step 13 stream hookup.

- **2026-10-08:** Corrected step 11 layout from the user's sketch: vertically
  sequential left prompt, centered Activity, then right answer, each capped at
  560 px with native alignment and mobile shrinking. Supersedes the initial
  placement and intermediate columns. All 49 UI/navigation checks pass; inline
  1440/390 px checks confirm alignment/order and no overflow. PR #34 remains open.
  User also requested live formation; step 13 follows as a separate slice before
  step 12. Screenshot `/tmp/opsflow-sequential-layout.png`.

- **2026-10-08:** Implemented approved step 11 completed per-turn Activity with
  collapsed native workflow/tool sections, stable turn keys, exact retained fields,
  and no inspector/selector. Conversation uses a 760 px desktop reading width,
  8 px mobile expander padding and visible summary focus. All 961 tests (six new),
  dependencies and whitespace pass; final assertions passed 49 UI/navigation checks.
  Inline browser on 8506/backend 8017 verifies restored workflow/tool records, new
  scripted no-tool agent turn, independent panels, refresh, keyboard/focus and
  1440/390 px layout without overflow. Saved JSON remains byte-identical after
  inspection. App stays open for review; merge awaits user confirmation. Figma is
  rate-limited; native adaptation approved. No live provider/email, dependencies,
  backend/routing, answer redesign, live UI events or deployment changes. Existing
  history deprecation remains. Screenshots `/tmp/opsflow-step11-review.png` and
  `/tmp/opsflow-step11-mobile.png`.

- **2026-10-08:** User authorized merging step 10 PR #33 after review. Verified
  the tested application head, user-only authorship/sign-off, passing DCO and clean
  mergeability. This approval record changes documentation only; existing 955-test
  and scripted-browser evidence remains applicable. Step 11 stays discussion only.

- **2026-10-08:** Implemented approved step 10 actual runtime/workflow/agent events
  and `POST /api/v1/chat/stream` SSE with chat/turn/sequence/step correlation,
  validated tool data, sanitized failures and saved terminal outcomes. Progress is
  transient; disconnect keeps backend work running, shutdown drains workers, replay
  returns saved outcomes, and unknown/interrupted work never automatically retries.
  All 955 tests (16 new), dependency, OpenAPI and whitespace checks pass. Real HTTP
  tests verify early delivery/disconnect/shutdown; inline backend review on 8017
  verifies progress/running state, disconnect recovery, identical replay and saved
  payload equality with real classifier/VADER/SQLite and scripted LLMs. Existing
  Streamlit chat/inspector on 8506 restores history and completes a nonstreaming
  turn; both pages stay open for user review. No live provider/email, dependency,
  schema, production UI, token-streaming or event-journal changes. Existing history
  deprecation remains; proxy behavior is unverified. Step 11 needs separate agreement;
  user approved merging PR #33 on 2026-10-08. Screenshot `/tmp/opsflow-step10-review.jpg`.

- **2026-10-08:** User approved merging step 9 and its step 8 dependency. Verified
  current heads, user-only authorship/sign-offs, passing DCO and mergeability.
  Merged #31 and retargeted #32 to `main`. This delivery-record update changes
  documentation only; existing 939-test/scripted-browser evidence still applies.
  Step 10 remains discussion only; original plan stays paused.

- **2026-10-08:** Implemented approved step 9 Workspace New chat/title navigation,
  URL-selected/latest/empty restoration, per-chat browser-session multiline drafts
  and one frozen/consumed submission queue. Running/unsaved states lock navigation
  and submission; read-only recovery retains exact outcomes and never retries.
  All 939 tests (17 new), dependency and whitespace checks pass; final wording
  changes passed 88 targeted checks. Inline browser on 8505/backend 8016 verifies
  two isolated sentiment/follow-up chats, an unsent draft, refresh during delayed
  execution, retrieval-failure recovery and byte-identical records after backend
  restart. Desktop/mobile checks confirm native navigation, literal/truncated
  accessible titles, 48 px targets, visible focus, stacked panels and no overflow.
  Review app stays open; user approved merging PR #32 after review. Its step 8
  dependency PR #31 is merged and #32 now targets `main`. Figma remains rate-limited; documented-token
  adaptation approved. No live provider/email, dependency, reminder, streaming,
  inline Activity, Docs or deployment changes; inspector remains in place.

- **2026-10-08:** Implemented approved step 8 create/list/load catalogue APIs and
  optional HTTP submission-ID replay, with client helpers, sanitized failures,
  consistent ordered snapshots and no read execution. All 922 tests (20 new),
  dependency and whitespace checks pass; final OpenAPI documentation changes passed
  41 targeted checks. Inline Swagger on 8015 verifies empty/create/load/list,
  scripted sentiment with real classifier/VADER, identical replay, 409/404 and
  unchanged saved records after backend restart. PR #31 merged after user approval.
  No live provider/email, dependencies, ownership, navigation,
  Streamlit UI or reminder changes. Step 9 remains a separate discussion.

- **2026-10-08:** User approved merging step 7 PR #30 and contract dependency #29.
  Verified both current heads, user-only authorship/sign-offs, passing DCO, and
  clean mergeability. Merged #29 and retargeted #30 to `main`. Existing 902-test
  and scripted-browser verification remains applicable; this approval record adds
  no application behavior or new live-provider/email checks.

- **2026-10-08:** Implemented approved step 7 durable chat history/restoration in
  separate versioned SQLite storage. Commit-before-execution/final acknowledgement,
  conservative interrupted recovery, exclusive local ownership, Python turn-ID
  replay, exact outcomes/context/demo markers, and durable clearing prevent silent
  memory/disk divergence. API/client reports unsaved storage failures explicitly.
  All 902 tests (25 new), dependency and whitespace checks pass. Inline browser
  verifies sentiment-to-agent context after backend restart, non-executing rerender,
  and a forced unsaved finalization with a retained marker, followed by conservative
  interrupted recovery and explicit continuation. Review app stays open
  on 8504 (scripted providers, real local runtime/tools/storage); user confirmation
  required before merge. No live provider/email, dependency/reminder, catalogue API,
  browser refresh restoration, or deployment changes. Step 6 PR #29 is the dependency.

- **2026-10-08:** Completed step 6 contract documentation after the user selected
  local single-user ownership and disabled navigation during execution. Defined
  separate SQLite chat storage, ordered durable outcomes/context, commit and
  interruption boundaries, non-repeating submission identity, catalogue API shapes,
  titles/URL restoration, and sidebar/Activity interaction proposals. Reviewed
  against current history/API/client/UI and reminder/design contracts; whitespace
  checks pass. No runtime changes/tests, provider calls, or browser verification.
  Figma inspection was rate-limited; visual approval remains in later UI slices.
  Next is a separately discussed step 7 implementation; original plan stays paused.

- **2026-10-08:** User approved merging step 5 PR #28 after the browser review.
  Verified the current head, user-only authorship/sign-off, passing DCO, and clean
  mergeability. Existing 877-test and scripted-browser verification remains
  applicable; no application changes or new live provider/side-effect checks.

- **2026-10-08:** Completed step 5 one-agent multi-step audit. Explicit prompt
  guidance covers dependency order and bounded work. Draft replies now retain
  earlier sentiment/keyword/summary/policy outcomes; stopped requests explain
  unfinished work. All 877 tests (seven added), `pip check`, and whitespace checks
  pass. Scripted loop/API/history checks cover three/four tools, dependent inputs,
  missing recipient, later failure, five-tool completion, sixth-tool rejection, and
  time overrun. Saved classifier routes the complaint to `compound_request` (0.7867).
  Inline browser verifies four outcomes, clarification with retained results, and
  tool-budget stopping using scripted agent/writing providers and real local tools.
  Review app remains open on 8503; confirmation required before merge. No live
  model-quality, email, reminder, deployment, dependency, or limit changes.

- **2026-10-08:** Completed step 4's agreed conversational writing audit. Missing/
  blank required summary source or draft recipient/content now asks a question
  without tool execution; malformed arguments/provider failures remain errors.
  Chat clarification replies have no technical warning banner; status remains in
  the inspector. All 870 tests (16 added scripted checks), `pip check`, and whitespace
  checks pass. Inline browser verified clarification answers, completed draft with
  separate actions, and contextual summary against a temporary scripted backend.
  Review app remains open on port 8502. User authorized merging PR #27 on
  2026-10-08; delivery uses user-only authorship and DCO sign-off.
  No live provider/email/reminder/deployment checks; semantic quality remains
  unverified. Recorded settings/Reminders/Email-page ideas for future discussion,
  with side-effect integration kept outside rework. No dependencies changed.

- **2026-10-08:** Moved sentiment, keyword, and FAQ workflow modules into
  `app/workflows/` and updated imports/documentation references. This keeps the
  focused workflow implementations grouped while preserving their behavior.
  All 855 tests pass. Inline-browser chat reached the updated backend but the
  sentiment extraction stage failed with reason `configuration`, so a successful
  live workflow remains unverified. The app is open for user review; wait for
  confirmation before pushing to `main`.

- **2026-10-08:** Added a pre-merge chat/Streamlit verification step: after
  automated tests, exercise the changed flow in the inline browser, leave the app
  open for the user's independent review, and wait for confirmation before merge.
  Documentation-only update; no application behavior or tests changed.

- **2026-10-08:** User authorized merging FAQ PR #26 and its required standalone
  dependency. PR #25 merged into `main` with a user-authored signed merge message;
  PR #26 retargeted to `main`. Implementation and caption checks remain the recorded
  855-test regression run and 26 UI checks; this delivery record changes only docs.
  Confirm current heads, DCO, and mergeability before the integration merge. Step 4
  remains a separate discussion; the original plan stays paused.

- **2026-10-08:** Removed the fixed `Fictional demo policy — verify your actual
  company policy.` chat caption at the user's request. Existing data, generated
  replies, and inspector records remain intact. Updated the existing FAQ UI
  assertion and usage docs; all 26 current UI checks and whitespace checks pass.
  No new tests, dependencies, backend/provider behavior, or live calls. One scoped
  user-authored DCO-signed correction in PR #26.

- **2026-10-07:** Completed approved step 3d: high-confidence FAQ chat uses fixed
  `llm_assisted`, retaining reply/exact policy/question and actual tool/workflow
  stages through API/client/history. Native reply/FAQ stage inspector avoids main
  JSON duplication and rerun execution. Clarification, original-context handoff,
  HTTP 200/503 and no-retry contracts are retained. Corrected agent policy/draft
  recipient instructions; an initial live eligibility error prompted an explicit
  grounding example. Final fresh/post-draft contractor samples clarified correctly;
  high-confidence workflow and missing-recipient draft samples also passed review.
  All 855 tests (22 new), dependency and whitespace checks pass. Figma rate-limited;
  existing native adaptation retained. No dependencies, classifier/index/FAQ-only
  contracts, side effects, or later work changed. Live samples do not establish
  general model fidelity. One user-authored DCO-signed integration change stacked
  on open PR #25; step 4 is next.

- **2026-10-07:** User requested attaching the FAQ workflow to app chat after an
  irrelevant recipient clarification. Recorded approved step 3d: classifier-first
  high-confidence workflow, preserved low-confidence agent routing, bounded FAQ
  agent-prompt correction, HTTP/history/traces, native presentation, offline checks,
  and a small synthetic live HTTP review. Standalone PR #25 is its dependency.

- **2026-10-07:** Completed approved step 3c standalone FAQ workflow: strict
  question extraction → unchanged local retrieval once → grounded matched-policy
  explanation, retaining exact answers and actual stages/timings. Ambiguous/no-match
  skips presentation; missing policy details may clarify with matched result intact;
  failed presentation uses a qualified exact-answer fallback without retry. All 833
  tests (47 new), `pip check`, and whitespace checks pass. Fake SDK transport checks
  both supported models; corrected new-test JSON tuple/list expectations. Added
  `docs/faq-workflow.md`. No live language-quality/injection evaluation, dependencies,
  classifier/index, runtime/API/UI/history/agent-registry, or side effects changed.
  One user-authored DCO-signed change; step 3d integration remains separate.

- **2026-10-07:** User approved the proposed first FAQ slice: standalone structured
  question extraction, unchanged local retrieval, and grounded presentation retaining
  exact policies. Recorded the step 3c input/outcome/failure and offline-verification
  contract before implementation; no chat integration or live quality check approved.

- **2026-10-07:** Reviewed the user's FAQ diagram and recorded a discussion-only
  proposal in `REWORK.md`: reuse local TF-IDF/ID lookup, preserve ambiguity/no-match,
  distinguish similarity from confidence and answer coverage, retain exact policies,
  and split standalone workflow from chat integration. Seven local read-only probes
  exposed unsupported qualifiers and classifier gating limitations; checked primary
  scikit-learn/Groq docs. Prose/source presentation choice was open at that review
  and subsequently resolved by the approved step 3c contract.
  No application code, automated suite, live provider, or side-effect execution.

- **2026-10-07:** User authorized merging keyword PR #24. Verified the tested application head, clean mergeability, user-only authorship, all DCO sign-offs, and passing DCO. Documentation-only delivery record; application/tests remain identical to the verified 786-test head. FAQ stays the next discussion; no new runtime/provider/email checks or later implementation.

- **2026-10-07:** Corrected keyword presentation from user feedback within PR #24: the LLM introduces the result, while the application renders an ordered Phrase/Score table from actual YAKE results. Scores display to five decimal places; full-precision JSON stays in API/history/inspector. Fallback/empty replies remain factual without repeating phrases; retained results still render on presentation failure. All 786 tests pass (two new UI boundaries and updated success/failure checks), with `pip check` and whitespace checks. Installed native table/number-format APIs checked; literal cells, precision/order, inspector-only JSON, empty results, and non-executing rerenders verified offline. No live LLM or browser-layout checks, dependencies, routing/tool/agent/FAQ changes, or new CSS/Figma work. Additional user-authored DCO-signed correction commit; FAQ remains the next discussion.

- **2026-10-07:** Completed approved step 3b in existing PR #24 at the user's request. High-confidence keywords now use `llm_assisted` extraction → YAKE → presentation; API/client/history retain readable reply/raw results, exact tool input, and actual workflow stages. Inspector labels LLM/local stages using its existing expander. Clarification, original-history handoff, HTTP 200/503 failures, empty/retained results, and no-retry behavior match sentiment. The 784-test suite passes (21 new integration/UI checks), with all 21 UI checks repeated after the final label change; `pip check` and whitespace checks pass. Saved-classifier examples inspected separately. No live Groq/SMTP, dependencies, thresholds/training, agent presentation, FAQ, CSS/layout, or deployment changes; Figma inspection was rate-limited. Additional user-authored DCO-signed integration commit; FAQ is the next discussion.

- **2026-10-07:** Completed approved REWORK step 3a, standalone natural-English keyword workflow: strict LLM source extraction → unchanged YAKE once → bounded LLM reply. Retains verbatim source, ranked phrases/raw scores, actual stage timings, clarification/handoff, sanitized failures, and factual presentation fallback including empty results. All 763 tests (42 new), `pip check`, and whitespace checks pass; installed adapter exercised with fake SDK transport and Groq schema compatibility checked. Added `docs/keyword-workflow.md`; user-authored DCO-signed PR #24 on `feature/keyword-language-workflow`. No live language-quality evaluation, dependencies, classifier/threshold, runtime/API/UI/history, pure tool/agent registry, FAQ, email, or deployment changes. Keyword chat integration and FAQ require separate discussion.

- **2026-10-07:** User authorized merging both sentiment slices. Merged standalone PR #22 and retargeted integration PR #23 to `main` for its authorized merge. Updated dependency/delivery records; user-only authorship and DCO verified. Application/tests remain identical to the tested step 2b commit, so existing 721-test evidence remains applicable. Documentation whitespace checked; no new runtime tests, provider calls, or later-step implementation.

- **2026-10-07:** Completed approved REWORK step 2b using the user's chosen `llm_assisted` route and existing HTTP status rules. Classifier-first sentiment now uses the fixed workflow; clarification/failures stop appropriately and contextual/compound abstention hands the original request/history to the agent once. API/client/history retain actual tool results, replies, and `workflow_trace`; the inspector reuses its native expander pattern. All 721 tests (15 new, existing sentiment checks migrated), `pip check`, and whitespace checks pass. A new mock-history test needed invocation snapshots. Saved-classifier examples inspected separately; no retraining/threshold/dependency change, live Groq/SMTP, or browser-layout/deployment checks. Figma remained rate-limited; documented design adaptation retained. Step 2b is a separate signed change on `feature/sentiment-chat-workflow`, stacked on open PR #22; step 3 awaits discussion.

- **2026-10-07:** Implemented approved REWORK step 2a: standalone strict LLM source extraction → unchanged VADER → bounded LLM explanation, with verbatim validation, clarification/handoff abstention, sanitized failures, actual stage timings, and a retained-result fallback when presentation fails. All 709 tests (39 new), `pip check`, and whitespace checks pass; installed LangChain serialization verified with fake SDK transport. Fixed an initial pytest reserved parameter name. Added `docs/sentiment-workflow.md` and recorded the standalone boundary in `AGENTS.md`. No live Groq/language-quality checks, dependencies, classifier/runtime/API/UI/history wiring, or email execution; existing LangChain warnings remain. Prepared as one signed change on `feature/sentiment-language-workflow`; step 2b needs separate agreement.

- **2026-10-07:** Recorded the user's proposed natural-language scaffold in `REWORK.md`: one sentiment workflow with structured source extraction, unchanged VADER scoring, grounded explanation, validation/abstention, retained-result failure handling, and proportional tests. Proposed a standalone first slice, then chat integration with explicit LLM-assisted routing semantics. Inspected current code and checked documentation whitespace; implementation and routing changes await agreement. No application code, runtime tests, live provider calls, or dependency/model compatibility checks.

- **2026-10-07:** Reordered `REWORK.md` at the user's request: inline completed execution details now follow backend behavior/persistence/events as step 11; their dependent readable-answer presentation is step 12, followed by live activity in step 13. Updated numbering, dependencies, and next discussion to natural-English sentiment. Reviewed sequence/references and whitespace. Documentation only, edited on `main`; after review the user authorized a signed commit and direct push without a new PR. No runtime tests.

- **2026-10-07:** Implemented approved REWORK step 1: Streamlit viewer toolbar mode removes Deploy/developer actions; removed redundant header/session/history copy and retained concise draft/reminder limitations. All 18 existing UI checks, `pip check`, and whitespace checks pass. Local browser verification covered a real direct sentiment request, 1440/390 px layouts, menu/keyboard/sidebar/focus behavior, and delayed HTTP-fixture loading/failure recovery with one submission. Temporary fixture services were stopped. Existing LangChain warnings remain; Figma contents were rate-limited, so the documented approved adaptation was retained. No new tests, backend/dependency changes, live provider/email, or deployment verification.

- **2026-10-07:** Created `REWORK.md` from the frontend discussion, including independent persistent chats, natural-English requests, inline collapsible execution activity, one-agent multi-step workflows, and in-app usage documentation. Updated `AGENTS.md` and the original plan's pause notice to make rework the active agenda until verified completion. Reviewed discussion coverage, sequencing, local links, and documentation whitespace; no application code, runtime tests, provider calls, or email execution changed.

## Earlier Change Record

- **2026-10-06:** Added proportional testing guidance to `AGENTS.md` and the plan: discuss test scope before coding, prioritize meaningful behavior and risks, and avoid redundant coverage. Reviewed the documentation diff and checked whitespace; no application code or tests changed.

- **2026-10-05:** Added `docs/design-system.md` as the project reference for the OpsFlow light-terminal Figma system and instructed future frontend design work in `AGENTS.md` to use it. Checked the document against the Figma file and captured palette, type, layout, tokens, component states, and usage guidance; no application code changed.

- **2026-10-03:** Added `docs/PLAN.md`, `docs/agents_doc.md`, and root `AGENTS.md`. Confirmed v1 emails the user with separate draft/instructions sections; reminders always use agent orchestration and include due-time email delivery. Direct sentiment receives the extracted text. Reviewed documents for consistency with the agreed scope; no application code or runtime tests yet.
- **2026-10-03:** Changed the planned classifier dataset from JSON to CSV with `text,label` columns. Increased the initial synthetic benchmark target from 120 to 1,000 rows, to be generated and reviewed in coordinated batches. The classifier will train on text and labels only; route/tool metadata remains outside the first training CSV.

- **2026-10-03:** Defined all eight dataset labels and generated the first three 125-row batches. The user approved reusing three sub-agents for the remaining batches after the session refused a fourth agent.
- **2026-10-04:** Completed `data/tasks_benchmark.csv` with exactly 1,000 examples, 125 per label, and only `text,label`. Strict CSV/shape/count/blank/label checks and value round-trip checks passed. Reviewed all examples and all 499,500 pairs through similarity screening; replaced one template-like reminder and logged it in `docs/dataset_validation_report.md`. No exact/normalized duplicates, confirmed near-duplicate clusters, or unresolved relabeling cases were identified. No classifier training or independent evaluation split performed.
- **2026-10-04:** Initialized the FastAPI development foundation on Python 3.12.13 with a repository-local `.venv`, exact direct dependency pins, a `/health` endpoint, and an endpoint test. Replaced deprecated `httpx` test support with `httpx2==2.13.0` after verification exposed Starlette's migration warning. `pip check`, package version checks, the test suite, and a live Uvicorn HTTP 200 response all passed.
- **2026-10-04:** Replaced the planned Logistic Regression router with a word TF-IDF + sigmoid-calibrated `LinearSVC`. Added and clean-kernel executed `notebooks/train_evaluate_svm.ipynb` using a deterministic stratified 80/20 development/test split, development-only model/threshold selection, calibration diagnostics, error review, and feature inspection. The saved evaluated pipeline reached 0.8800 test accuracy and 0.8813 macro F1. Its development-selected 0.71 direct-route threshold reached 1.0 precision at 0.235 coverage on the untouched synthetic test set with zero reminder/compound false-directs. Saved the trusted-local joblib pipeline and provenance metadata under `artifacts/models/`; artifact reload, dependency checks, and the test suite passed. Results remain limited to same-source synthetic data.

- **2026-10-05:** Implemented the agreed English sentiment slice using `vaderSentiment==3.3.2`, structured label/scores, standard compound thresholds, and conservative whole-request extraction of one double-quoted payload. Added an intent/confidence gate with an explicit threshold and observable fallback reasons; agent decisions do not execute the scorer or an agent. Verified Python 3.12.13 compatibility, `pip check`, `git diff --check`, and all 53 tests (including health, negation, payload preservation, repeatability without network connections, and fallback non-execution). Fixed a pytest parameter-name collision and colon extraction found during verification. No model loading, chat/API wiring, language detection, or real-world sentiment accuracy evaluation in this slice.

- **2026-10-05:** Added local English `yake==0.7.3` keyword extraction returning up to five ranked one-to-three-word phrases with raw relevance scores, plus conservative quoted-payload extraction and an intent/confidence gate. Verified the installed API and Python 3.12 compatibility, relevant example phrases, empty/no-candidate inputs, repeatability without network connections, and fallback non-execution. All 105 tests, `pip check`, and `git diff --check` passed. Example tests are not a real-world quality benchmark; model/API/agent wiring remains pending. FAQ direction is fictional employee policies, with local JSON proposed for the next discussion.

- **2026-10-05:** Moved keyword and sentiment execution-routing helpers into `app/routes/`, added the package description, and updated test imports and the architecture note. No routing behavior changed; all 105 existing tests and `git diff --check` passed.

- **2026-10-05:** Added 25 fictional employee policies with 75 question phrasings in `data/company_faq.json` and local TF-IDF/cosine retrieval in `app/tools/faq.py`. Results return an exact stored answer, candidate questions, or no match, with a demo flag. Adjusted conservative development heuristics after initial checks exposed vague-query and weak-match issues; some valid paraphrases intentionally abstain. Verified all 208 tests, installed scikit-learn API compatibility, `pip check`, and `git diff --check`; no dependencies added. Tests cover dataset integrity, all stored phrasings, example paraphrases, ambiguity, unsupported questions, input validation, and offline repeatability across index reloads and working directories. No independent retrieval-quality evaluation or routing/API/agent wiring yet.

- **2026-10-06:** Added conservative FAQ routing, trusted saved-model loading with metadata/hash checks, and stateless `POST /api/v1/faq` with validated message input, classification, actual tool traces/timing, and explicit `agent_required` fallback. Documented accepted question forms, demo results, and HTTP 422/503 behavior in `docs/faq-api.md`. All 347 tests, `pip check`, and `git diff --check` pass, including real saved-model API matches/ambiguity/no-match, compound/contextual/reminder fallback without execution, invalid bodies, artifact validation, and sanitized failure reporting. No new dependencies, agent invocation, session history, shared chat endpoint, or live-server/network deployment testing.

- **2026-10-06:** Implemented the agreed shared deterministic runtime: classify once, dispatch sentiment/keywords/FAQ through existing extraction/confidence gates, return structured results and actual tool traces/timing, and preserve the FAQ API contract with FAQ-only execution. Added sanitized sentiment/keyword failure results and proportional runtime/API integration checks. All 375 tests, `pip check`, and `git diff --check` pass. Saved-model checks cover sentiment execution, FAQ outcomes, and keyword low-confidence fallback; controlled predictions cover keyword dispatch. No dependencies added, threshold changes, agent invocation, session memory, or live-server/deployment verification.

- **2026-10-06:** Recorded a proposed standalone structured summarization slice in the plan: payload/output limits, ChatGroq strict-schema model/configuration, sanitized failures, and proportional offline/manual verification. Checked Groq and LangChain documentation and confirmed local key presence without exposing it. Scope awaits agreement; key validity, dependency compatibility, and live behavior remain unverified. No application code changed.

- **2026-10-06:** Implemented the agreed standalone `summarize_text` tool using lazy ChatGroq configuration, strict provider JSON Schema, local Pydantic bounds, sanitized failures, no retries/repair, and disabled external tracing. Pinned compatible dependencies; all 413 tests (38 new), `pip check`, and whitespace checks pass. Three live synthetic examples passed schema/fidelity review; embedded instructions were quoted rather than followed, but relevance selection remains unevaluated beyond these examples. Added `docs/summarization.md`; deterministic runtime/agent/session behavior is unchanged.

- **2026-10-06:** Recorded a proposed standalone email-drafting contract in `docs/PLAN.md`: recipient/source/writing inputs, generated subject/body separated from fixed user actions, strict Groq settings, sanitized failures, and proportional offline/live verification. Reviewed existing summarization code and current Groq/LangChain documentation. Proposal awaits agreement; no application code, provider calls, or runtime tests changed.

- **2026-10-06:** Implemented the agreed standalone `draft_email` tool with separate source/writing inputs, unchanged recipient, strict subject/body generation, fixed user actions, lazy Groq configuration, and sanitized failures. All 456 tests (43 new), `pip check`, and whitespace checks pass. Nine synthetic live calls across three prompt iterations exposed invented reopening dates; explicit grounding examples corrected the final inspected set. Final samples preserved inspected facts and excluded an embedded command, without establishing general fidelity/injection resistance. Added `docs/email-drafting.md`; no delivery, routing, agent, API, or memory changes.

- **2026-10-06:** Recorded a provider-independent notification-delivery proposal: configured-user-only envelope, separate draft/action sections, accepted/failed/unknown outcomes, no automatic retries, and proportional transport-double tests. Requested the existing sender provider and confirmation of Asia/Kolkata as the future reminder default. No delivery code or messages sent; settings/implementation agreement remain pending. Email-drafting PR #11 remains open and separate.

- **2026-10-06:** User confirmed Asia/Kolkata as the default timezone. Gmail address alone does not authorize sending; discussing app-password versus OAuth setup before selecting transport. No delivery code or messages sent.

- **2026-10-06:** Implemented the agreed standalone Gmail draft-notification utility using verified TLS, fixed configured-user envelope, separate draft/actions, no retries, and sanitized accepted/failed/unknown submission outcomes. Cleanup cannot overwrite acceptance; Message-ID is explicitly not deduplication. All 492 tests (36 new), `pip check`, and whitespace checks pass; local configuration format is valid without exposing credentials. No live authentication or email sent. Added `docs/email-notifications.md`; delivery branch/PR is separate from the still-open drafting PR.

- **2026-10-06:** Recorded proposed reminder slices: structured timezone validation/SQLite scheduling first, then a due-time Gmail worker with durable attempts, bounded definite-failure retries, exclusive recovery, and unknown outcomes held without automatic retry. Reviewed existing notification behavior and primary Python/SQLite documentation; checked documentation whitespace. Contracts and tests await agreement; no application code, runtime tests, or emails executed.

- **2026-10-06:** User approved the persistence/timezone slice. Implemented structured `schedule_reminder` with Asia/Kolkata default, UTC round-trip validation and confirmed offsets for DST ambiguity, durable SQLite records, transactional creation-key deduplication, and sanitized persistence failures. All 538 tests (46 new), `pip check`, and whitespace checks pass; concurrent creation, fresh-process overdue recovery, and simulated commit rollback were verified. No new dependencies, email submission, worker, agent, API, or UI integration. Added `docs/reminders.md` and ignored local SQLite storage.

- **2026-10-06:** User approved the due-time worker policy/test slice. Implemented a separate local Unix polling worker with durable attempts, exclusive file-lock ownership, persisted three-attempt budget and one/five-minute retry delays, conservative unknown recovery, and graceful signal shutdown. Reminder emails share the existing Gmail transport; safe pre-submission retry metadata is additive. All 572 tests (34 new), `pip check`, whitespace checks, and CLI help pass. Verified actual process exit, second-process exclusion, post-acceptance interruption, database write failures, SMTP-stage classification, and SIGTERM during submission. No real SMTP connection/message, inbox verification, new dependency, deployment, manual reconciliation, or agent/API/UI wiring. Worker change is separate from open dependency PR #13.

- **2026-10-06:** User authorized merging both reminder slices. Merged persistence PR #13 and retargeted worker PR #14 to `main`; updated dependency notes and checked documentation whitespace. Existing 572-test verification remains applicable; no application behavior changed or real email sent.

**Historical next step (superseded by rework):** Discuss one bounded remaining-endpoint, observability or reminder/email chat-integration slice before deployment. Worker deployment and real SMTP/inbox testing remain unverified.

- **2026-10-06:** Implemented the approved standalone five-tool ChatGroq loop with strict local arguments/final validation, sequential observations, six orchestration calls/five tools/soft 120-second budget, sanitized failures and retained structured results. Application renders drafts with fixed actions and demo qualification. Pinned the already-installed directly imported LangChain Core 1.6.6. All 608 tests (36 new), pip check and whitespace checks pass. Final synthetic live clarification, FAQ-to-draft and summary samples passed inspected behavior; earlier invented JSON-tool calls/source-command leakage and final summary relevance limitations remain documented, without establishing general reliability/injection resistance. No runtime/API/memory wiring, reminder creation or email submission.

- **2026-10-06:** Implemented the approved stateless runtime-to-agent handoff: classify once, pass deferred requests unchanged to the agent, retain reply/status/failure reason and actual traces, and time the full operation. Direct failures stop; FAQ-only behavior is preserved. All 614 tests (six new), `pip check` and whitespace checks pass, including offline real-loop integration. No new live provider/email tests, session memory, chat API/UI or reminder/email execution.

- **2026-10-06:** Implemented approved process-local session history across both routes with explicit clearing, per-session serialization, agent follow-up context, accurate failure records and retained demo/draft actions. All 631 tests (17 new), `pip check` and whitespace checks pass; scripted provider doubles verify context transport, isolation and concurrency without proving model reference resolution. Installed LangChain history APIs are deprecated; no dependency/framework change. History resets on restart without automatic truncation/eviction. No live provider/email, HTTP/UI or deployment checks. Handoff dependency PR #16 is merged; memory PR #17 now targets `main`.

- **2026-10-06:** User authorized merging the session-memory slice and its handoff dependency. Merged runtime PR #16 and retargeted memory PR #17 to `main`; updated dependency notes and checked documentation whitespace. Existing 631-test verification remains applicable; no application behavior changed or live provider/email calls made.

- **2026-10-06:** Planned and implemented the requested bounded `POST /api/v1/chat` endpoint with strict session/message validation, existing process-local history, structured direct/agent results and actual traces, and 503 errors/partial failures retaining observations. All 652 tests (21 new), `pip check`, whitespace checks and a local Uvicorn direct sentiment HTTP smoke pass. No dependencies added; existing LangChain deprecations remain. No live Groq/email, UI or deployment checks. Added `docs/chat-api.md`; logs, metrics and other endpoints remain separate slices.

- **2026-10-06:** Implemented the approved local Streamlit chat/inspector with stable session identity, one-shot HTTP submission, preserved intent/route/results/traces and exact backend timings, clarification and partial-failure display, safe transport errors and no automatic retry. Pinned Streamlit 1.65.0; bundled licensed local fonts and adapted Figma Foundations with user approval because Components/Console pages were unavailable. All 670 tests (18 new), `pip check` and whitespace checks pass. Real local backend/direct sentiment browser verification and offline agent/UI integration cover core behavior; no live Groq, SMTP/inbox or deployment verification. See `docs/streamlit-console.md`.
