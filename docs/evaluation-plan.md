# OpsFlow evaluation implementation plan

Researched 2026-10-14. **Status: slices 1–2 implemented and verified locally;
slice 3's approved offline scope is implemented, with live verification deferred;
slices 4–5 remain proposed.** This plan covers a Settings → Evaluations
area, measurable quality criteria, implementation order, verification and
assessment talking points. It does not authorize every slice at once.

## Continue in a new chat

This file is the evaluation implementation guide. Follow the five slices below
in order; update their status, evidence and next step after each slice. Discuss
scope or order changes before implementing them.

- **One shared PR:** [draft PR #55](https://github.com/orbin123/opsflow-agent/pull/55),
  branch `feature/evaluation-baseline`, targeting `main`. On 2026-10-14 the user
  changed publication grouping: implement the whole evaluation plan in this PR,
  with distinct scoped commits for each agreed slice. Keep handoff/verification
  documentation in the same PR. Do not open a new PR for each slice or squash
  away the slice commits during the build. Keep the PR draft until all agreed
  slices are verified and the user authorizes final review/merge.
- **Existing checkout on this machine:**
  `/Users/orbin/.codex/worktrees/evaluation-baseline/opsflow-agent`.
  Verify its branch and worktree status before editing and reuse this checkout.
  If it is unavailable, fetch the existing branch into a suitable clean checkout;
  preserve user changes. The primary project checkout was on
  `fix/workflow-configuration` at handoff and does not contain evaluation code.
  A copy of this plan there is for finding the feature work, not evidence that
  the implementation is on that branch or on `main`.
- **Read first:** this file, `AGENTS.md`, `docs/package-structure.md`,
  `docs/PLAN.md`, `docs/agents_doc.md`, `docs/evaluation.md` and
  `skills/karpathy-guidelines/SKILL.md` in the evaluation checkout. Before UI work,
  also read `docs/design-system.md` and the required Streamlit skill and references.
- **Latest application verification:** slice 3's approved offline scope at
  `3738c50` (initial harness commit `5a90b82`). All 1,295 offline tests pass
  (44 new); dependencies/whitespace and native ARM64 Docker/container checks pass.
  Inline desktop/390 px mobile, exact download, Return/draft and Refresh pass.
  Clean report: `var/evaluations/45dbe8795b9c4b32ae534d43133be12b/report.json`,
  24 observations, 48 scripted model attempts, 21 tool calls and zero SMTP/worker
  attempts. It records a clean `3738c50` and no provider invocation. If missing,
  explicitly regenerate with `python -m app.evaluation --suite runtime`; reads
  never rerun it. Live calls and human reference review remain deferred.
  App stays open on 8517. Slice 2 CI/DCO pass (`38523659729`); fresh slice 3
  hosted CI runs after publication. Keep the shared PR draft.
- **Saved slice 1 evidence:**
  `var/evaluations/89c111c7f91d4382b6ca872b62dbada4/report.json` in that checkout.
  It records commit `140d8f6` with a clean working tree and all 224 cases executed.
  Reports are ignored local files; if missing, explicitly regenerate with
  `python -m app.evaluation` in the evaluation checkout. Reading never reruns work.
- **Current boundary:** slice 3's harness/offline implementation is approved and
  implemented. The user explicitly deferred live calls on 2026-10-14. Do not mark
  live model quality/stability or human reference review complete. Discuss completing
  that deferred slice 3 work, or an explicit order change, before slice 4. Keep PR #55
  draft; no merge/deployment or semantic judge is authorized by this continuation.

| Slice | Status | Completion evidence / next action |
| --- | --- | --- |
| 1 — Local baseline | ✅ Implemented and verified | Commit `140d8f6`; CLI, 24-case development pilot, 200-row holdout, pure scorers and atomic saved reports; verification above and detailed outcome below. |
| 2 — Settings catalogue | ✅ Implemented and verified locally | GET list/detail, native Settings, shared report root and exact historical synthetic packaging. 1,251 tests; Docker/container checks; inline desktop/mobile/download/draft/refresh; details below. Hosted deployment remains unverified. |
| 3 — Real workflows and agent | ⏳ Offline scope verified; live calls deferred | 24 development scenarios, pure evaluators, isolated bounded runner and saved traces. User deferred live calls; live quality/stability and human reference review remain explicit gaps. |
| 4 — Generation quality | Planned | Reviewed facts/rubrics, human annotations, optional validated judge, generation scores and compatible version comparisons. |
| 5 — Assessment and CI | Planned | Final benchmark/CI regression gates, exports, browser walkthrough and assessment talking points. Slice 1's existing CI checks do not complete this assessment slice. |

### Slice 2 contract — approved 2026-10-14

Inputs are the existing saved `Report` records and configured local report storage.
Outputs are a read-only run catalogue/detail API and native Settings page showing
run state, quality verdict, category metrics/counts and literal expected/actual
case evidence. Reuse current contracts and storage readers; keep execution behind
the explicit CLI. Page entry, refresh, filtering, detail reads and downloads must
not run models/tools or resume interrupted reports. Preserve selected chat,
browser-session drafts and existing pending/running/unsaved navigation locks.

The user approved the native Settings adaptation, shared `OPSFLOW_EVALUATIONS_DIR`
and selected historical synthetic report packaging on 2026-10-14. Completed
verification is below; operation/API/storage details are in [evaluation.md](evaluation.md).

Suggested opening message for the next chat:

> Read AGENTS.md and docs/evaluation-plan.md, use the existing evaluation checkout
> and draft PR #55. Slices 1–2 are complete; slice 3's harness/offline scope is
> implemented, with live calls deferred by user choice. Discuss human reference
> review and the deferred isolated live subset (at most 60 requests; representative
> scenarios repeated three times), or explicitly agree an order change before
> starting slice 4. Keep scoped signed commits in the shared draft PR.

Assumptions: English, fictional policies and synthetic evaluation inputs remain
the project boundary. “Condensed relevance” is interpreted as context relevance
and summary faithfulness/coverage; confirm that wording before its implementation.
“Talkers” is interpreted as talking points supported by implementation evidence.

## Slice 1 outcome — verified 2026-10-14

The user approved the local baseline after reviewing this proposal. Implemented
`python -m app.evaluation`, versioned cases/reports, pure scorers and atomic
report storage; see [evaluation.md](evaluation.md) for operation and limitations.
All 224 cases execute: the unchanged 200-row holdout plus eight routing and
sixteen FAQ development cases. New pilot references remain AI-authored and
pending human review. No application routing, model artifact or policy was changed.

All 1,219 offline tests pass, including 29 new evaluation checks; dependency and
whitespace checks pass. A fresh-process CLI test blocks network access, classifier
fitting and provider/side-effect module imports. Tests cover hand-computable
scores, deliberately incorrect observations, malformed references/reports,
fingerprint changes, zero denominators, interruption and atomic-write failures.
No browser check is required for this CLI-only slice; chat/Streamlit are unchanged.

Observed pilot results are 7/8 intent labels, 8/8 eligibility decisions, 12/16 FAQ
statuses, 8/8 correct accepted policies and 8/10 expected matches. Two broad
ambiguity references return no-match; these safe abstentions still differ from
the provisional labels. Failures are retained, not used to tune tools or references.
Settings display and live agent/generation evaluation remain later agreed slices.

## Slice 2 outcome — verified locally 2026-10-14

Implemented GET-only run catalogue/detail APIs and native Settings → Evaluations.
Shared configurable report storage, explicit missing/invalid/unavailable snapshots,
literal incomplete/interrupted reports, counts/definitions/versions, exact case
expectations/observations and unscored criteria preserve slice 1 contracts. Reads,
reruns, selection and downloads import no runner and never execute/rescore/resume.
The approved selected baseline is copied byte-for-byte into the Docker image,
with its recorded commit/date and explicit historical-version warning. No new
model/provider/dependency or hosted execution control was added.

All 1,251 offline tests pass, including 32 new storage/API/transport/navigation
checks, plus dependency/whitespace checks. Fresh-process reading blocks runner,
agent/runtime and side-effect imports. Native ARM64 Docker build, packaged report
reading without generated storage/CSV/pilot, HTTP/WebSocket authentication and
missing-password startup smoke checks pass. Hosted AMD64 CI run `38523659729` and DCO pass on documentation head
`a9c6f3c`, retaining application commit `ca25384`.

Inline browser on `http://127.0.0.1:8517` verifies desktop and 390×844 mobile layout,
bundled warning, literal failed FAQ evidence and Not scored criteria, JSON download
matching the complete baseline, Refresh, Return with an unsent multiline draft,
and browser reload restoring selected chat. Reload returns to chat and retains
existing session-draft limitations; page/view persistence was not added. Actual
backend catalogue/detail GETs retain all cases and saved scores. The review chat
has zero turns, task/tool counters stay zero, and no reminder database was created.
The app remains open for user review. Figma Foundations listing succeeded; deeper
inspection hit its quota, so the approved documented Settings adaptation was used.
No live LLM, worker, SMTP, Render deployment or merge was performed. Slice 3 awaits
its separate contract discussion.

## Slice 3 offline outcome — 2026-10-14

The user approved implementation and offline checks and explicitly deferred live
calls. Added 24 separate development scenarios, pure literal-argument/trajectory/
dependency/context/state scorers and schema-v2 reports. The bounded runner uses
fresh subprocesses/disposable SQLite, frozen reminder time, real scheduling and
HTTP/SSE/persistence, scripted provider doubles, blocked SMTP/worker startup and
an explicit model-attempt budget. Live mode is opt-in and was not invoked.

All 1,295 offline tests pass (44 new), including defective observations, missing/
extra/forbidden calls, dependency/order/history mistakes, wrong reminder instants/
zones/states, replay/recovery, bounded requests/cases, interruption/worker/storage
failures, reader/API/UI compatibility and zero execution on reads. Dependencies
and whitespace pass. Native ARM64 Docker build, authentication smoke and schema-v1
baseline packaging pass. Browser review verifies desktop/390 px mobile saved
partial-failure evidence, exact JSON download, mode qualification, Return/draft
and Refresh. The running review backend's task/tool counts remain zero, its chat
has no turns and its reminder DB is absent.

The full scripted pilot observes all 24 scenarios, 48 model attempts and 21 tool
calls, with zero SMTP/worker attempts and isolated state. Expected contract checks
pass 24/24; two controlled partial failures remain in application availability
(22/24). Generated-answer semantics is unscored. Standalone workflow records retain
actual extraction fields and mark runtime routing unobserved; chat records retain
real classifier/runtime routes. Collection state/observed counts include retained
budget-limited observations and do not imply application success. Final clean-report
and publication evidence are recorded in the handoff/change record.

This completes the approved **offline** scope, not the original full slice 3 live
validation. Reference human review, actual live model quality/provider compatibility
and three-repeat live stability remain deferred/unverified. Discuss completing
those checks, or explicitly agree a plan order change, before slice 4. Keep PR #55
draft; no merge/deployment or semantic judge was authorized.

## Existing evidence and gaps

- The classifier notebook and saved metadata already report classification,
  calibration and a confidence-threshold study. On 2026-10-14, an offline check
  verified dataset/model fingerprints, reproduced the exact 200-row holdout and
  recomputed the recorded scores without retraining: accuracy **0.8800**, macro F1
  **0.8813**, log loss **0.4549**, multiclass Brier **0.2226** (sum over classes),
  and top-label ECE **0.1606** (ten equal-width confidence bins).
- The 0.71 threshold accepted 47/200 cases, with 47/47 correct labels and 23.5%
  coverage. These are classifier-level synthetic results. The historical
  `direct_precision` field does **not** establish current end-to-end chat safety:
  high-confidence chat sentiment/keywords/FAQ now use `llm_assisted`, and can
  clarify or hand off after extraction. `/api/v1/faq` retains a separate local gate.
- Canonical FAQ questions retrieved the correct policy for 25/25 entries in the
  same offline check. These questions are indexed retrieval material, so this is
  a regression check, not independent paraphrase-quality evidence.
- Existing tests exercise contracts with provider doubles. Saved execution records
  contain route, tool arguments/results, workflow stages, outcomes and timings.
  These support evaluation but are not ground truth or proof of live model quality.
- Prometheus/Grafana already measure operation. Evaluation should measure quality
  against references, with execution failures and performance shown separately.

During initial research, no live model, SMTP, reminder worker, deployment or new
UI was exercised, and the full suite was not rerun at that point. Current slice 1
verification is recorded above; live model and UI quality remain unverified.

## Recommended criteria

Ground truth is the reference dataset underlying these criteria, not an additional
score. Every score must identify its dataset, scorer and applicable denominator.

| Area | Primary criteria | Reference/evidence | Important boundaries |
| --- | --- | --- | --- |
| Intent and routing | Macro F1; per-intent precision/recall/F1; confusion matrix; correct permitted route; high-confidence precision and coverage | Reviewed intent labels, route constraints, actual classifier and runtime outputs | Measure classifier and runtime routing separately. Reminder/compound requests require agent orchestration; workflow extraction may hand off. Include out-of-scope false acceptance. |
| Extraction and tool use | Verbatim source/question/phrase accuracy; correct tool names and arguments; required-tool coverage; unnecessary/forbidden calls; dependency order | Labelled payload spans, required/allowed/forbidden tools, actual arguments/results and ordered traces | Negation, qualifiers, names, dates, punctuation and line breaks matter. Clarification can require zero calls. Permit independent tools in either order. |
| FAQ resources and context | Correct policy ID; matched/ambiguous/no-match accuracy; wrong-policy acceptance; appropriate missing-detail clarification | Independent questions, relevant policy IDs, exact versioned FAQ answers and missing-fact annotations | A high similarity score cannot establish contractor eligibility or another unstated fact. Distinguish resource selection from whether its facts answer the question. |
| Generated answers | Factual faithfulness; required-fact coverage; response relevance; instruction/tone compliance; accurate action/status claims | Source text, retrieved policy/tool evidence, required facts and a reviewed rubric | Apply to summaries, drafts, workflow explanations and final agent answers. A readable or valid JSON answer can still invent facts. |
| End-to-end agent goals | All requested subtasks achieved; appropriate clarification; dependency outputs used correctly; multi-turn context accuracy | Scenario outcomes, allowed trajectories, retained results, history and isolated storage state | A completed tool call is not a successful user goal. Partial failure must retain successes and describe unfinished work accurately. |
| Side effects and recovery | Correct reminder task/time/zone; creation exactly once; no unauthorized scheduling/sending; replay/refresh causes zero execution | Frozen evaluation time, labelled literal time phrases, isolated records, transport doubles and call counts | Scheduling is not delivery; SMTP acceptance is not inbox arrival. Source instructions cannot authorize extra actions. |
| Reliability and efficiency | Execution success/failure by stage; model/tool call counts; observed p50/p95 latency; repeat-run stability | Actual stage outcomes, elapsed times and repeated live samples | Judge failure differs from app failure and quality failure. Count a tool once when it appears in both tool and workflow records. Token/cost fields stay unavailable until measured. |

Agent trajectory evaluation should check observable actions, arguments and
dependencies. Strict and order-independent comparisons are established options;
the chosen comparison must fit the task. See the official
[AgentEvals trajectory documentation](https://github.com/langchain-ai/agentevals).
OpsFlow can implement the small required checks against its own traces without
adopting another framework or collecting private reasoning.

### Metric definitions and applicability

- **Payload accuracy:** proportion of applicable calls with the exact reviewed
  payload. No fuzzy normalization for fields whose contract requires literal text.
  Reminder resolution additionally compares the resolved instant and zone.
- **Tool precision/recall:** match actual calls one-to-one against allowed reference
  calls, including argument rules and multiplicity. Report extra and missing calls
  separately. Required-call recall alone cannot detect unwanted scheduling. For
  no-tool cases, score the no-call constraint; empty denominators are not perfect
  precision/recall. Overall goal success requires successful results, not just calls.
- **FAQ match quality:** accepted correct matches / all accepted matches; correct
  accepted matches / answerable cases; and incorrect matches on unanswerable cases.
  Report ambiguity/no-match decisions separately. Initially use policy IDs and
  information sufficiency. Recall@k/MRR require a future explicit ranked retrieval
  contract: the current API exposes thresholded candidates, not a full ranking.
- **Context relevance:** does the selected policy or prior-turn evidence help
  answer this question? **Information coverage:** does it contain the labelled
  facts needed? Do not manufacture multi-document context-precision scores for
  OpsFlow's current one-policy answer. ID-based recall is an established option
  when reference resources are known; see
  [Ragas context recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/).
- **Faithfulness:** supported factual claims / evaluated factual claims, retaining
  source evidence for each decision. Zero claims is not automatic success; answer
  completeness still applies. Claim assessment needs human review or a validated
  judge, not a keyword-match shortcut. This follows the
  [Ragas faithfulness definition](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/).
- **Required-fact coverage:** supported required facts expressed / labelled required
  facts. For summaries, preserve material dates, numbers, uncertainty and decisions.
  Compression ratio is descriptive; shorter output is not automatically better.
- **Response relevance:** does the answer address the request without distracting
  additions? Score separately from correctness. Ragas likewise distinguishes these
  properties in its [response relevancy metric](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/).
  Our initial rubric is not the Ragas embedding-based implementation and must not
  be labelled a Ragas score.
- **Calibration:** keep Brier/log loss with reliability bins and ECE. Record the
  Brier convention, binning and sample counts; neither Brier nor log loss isolates
  calibration from discrimination. See
  [scikit-learn calibration guidance](https://scikit-learn.org/stable/modules/calibration.html).

For semantic review, propose a 0–3 rubric for each dimension: 0 unacceptable,
1 major omission/error, 2 minor issue, 3 fully meets the criterion. Store short
evidence-based explanations. Do not average critical violations into a passing
overall score. Use `not_applicable`, `not_scored` and `scorer_error` explicitly;
show applicable/scored/missing counts and reasons beside aggregates.

## Ground truth and dataset design

1. Preserve the existing 1,000-row classification corpus and original 200-row
   holdout. Do not retrain, tune thresholds or alter the data in this addition.
2. Create a separate, versioned end-to-end corpus. Each case records ID, scenario
   family, input/history, frozen time/zone where needed, expected intent or allowed
   intents, route constraints, exact payload fields, required/allowed/forbidden
   calls, dependency requirements, reference policy/source facts, acceptable outcome
   and semantic rubric. Expectations must be written before running the model.
3. Start with a small 24-case development pilot: eight routing-boundary cases and
   sixteen independent FAQ cases spanning matches, ambiguity, no-match and missing
   details. The pilot validates the harness and surfaces errors; it is not an
   independent benchmark claim. Extraction/agent/generation cases follow later.
4. Grow proportionally to approximately 120 reviewed end-to-end cases: 20 source
   extraction, 40 FAQ/resource cases (cover all 25 policies plus negative cases),
   20 summary/draft cases, 20 compound/conversation cases and 20 reminder/action
   boundary cases. Categories are a proposed coverage budget, not exhaustive
   paraphrase counts. Injection and realistic provider failures cross these groups.
5. Keep development and held-out evaluation scenario families separate; a proposed
   40/80 split must retain meaningful category coverage. Group near-paraphrases and
   related histories together. Do not reuse training requests or indexed FAQ
   phrasings as independent evaluation questions. Audit overlap and provenance.
   The holdout must not select prompts, scorers or acceptance thresholds; after
   tuning against observed failures, describe that set as regression evidence and
   reserve fresh cases for another independent claim. See
   [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).
6. Label semantic sentiment independently of VADER, and keywords with accepted
   concepts/phrase alternatives. VADER/YAKE snapshots measure tool regression;
   they do not prove NLP accuracy. Do not compare YAKE's score to a confidence
   probability or require one arbitrary generated sentence as the only answer.
7. Have a human review references and adjudicate disputed labels before calling
   them ground truth. AI-generated cases/reviews remain identified as such until
   reviewed. Judge-vs-human agreement requires actual independently supplied
   human labels; another agent is not a human reviewer.

Representative cases include: sentiment text with a negative instruction wrapper
but positive source; a FAQ question with an unsupported eligibility qualifier;
a summary with numbers and uncertainty; a draft with no supplied reopening date;
lookup → draft using that policy; independent sentiment/keyword operations;
“summarize it” with and without relevant history; reminder clarification followed
by a literal time; a successful reminder followed by model failure; and source text
containing an instruction to schedule or send something unrelated.

## Implementation approach and Settings experience

Recommend a small local harness using the existing Python stack. Separate case
execution from scoring, so saved synthetic outcomes can be rescored without
executing tools. Use existing tool/workflow/agent/runtime entry points; later
contract scenarios also exercise actual HTTP/SSE/persistence in isolated processes.

| Option | Fit for OpsFlow | Proposed decision |
| --- | --- | --- |
| Local Python scorers, pytest, immutable JSON reports | Deterministic labels, field/trace checks, local policy IDs and existing storage boundaries | First implementation; no new hosted evaluation service |
| LangSmith / AgentEvals | Offline experiments and trajectory comparison patterns | Use researched methodology; do not enable currently disabled hosted tracing implicitly |
| Ragas | Established retrieval/faithfulness metrics; some implementations need judges or embeddings | Use relevant definitions; revisit package adoption only if its added capability justifies dependencies |

[LangSmith's evaluation types](https://docs.langchain.com/langsmith/evaluation-types)
distinguish curated offline benchmarking from online evaluation and support code,
human-oriented and model-based scoring patterns. OpsFlow should begin offline.
No automatic scoring of every real chat or cloud trace export is proposed.

Proposed modules are `app/evaluation/` for case/report contracts, runners and
scorers, `app/api/evaluations.py` for read-only catalogue/detail APIs, and existing
UI helpers for transport/presentation. Versioned fixtures belong in
`data/evaluation/`; generated reports use a separately configured local directory,
not the chat/reminder databases. Start with atomic per-run JSON reports rather
than a new SQLite migration. Validate schemas, use opaque run IDs, reject path
traversal, distinguish missing/corrupt reports and enforce one writer per run.
Record interrupted/incomplete runs explicitly; opening a report never resumes it.

Each report identifies source commit/dirty state, dataset and model hashes, FAQ
and prompt fingerprints, relevant dependency versions, runtime/evaluator model
IDs and settings, scorer/rubric version, run time, case outcomes, traces, metric
numerators/denominators and limitations. Preserve actual generated outputs; do
not overwrite previous runs. Execution completion, quality verdict and scorer
availability are separate fields. Compare only compatible dataset/scorer versions;
show changed model/prompt configuration explicitly.

Settings → **Evaluations** should provide:

- Return to chat and Refresh, retaining selected chat and browser-session drafts.
  Existing pending/running/unsaved chat locks continue to block page entry.
- Saved run history with suite, date, app/model/dataset versions, execution state
  and quality verdict. Filters and a compatible baseline comparison follow the
  initial catalogue. Show all retained runs, including failures and interruptions.
- Category summaries with definitions, counts and scorer type. No fabricated
  single “agent accuracy” number. Unimplemented categories say “Not evaluated”.
- Case details: literal input, reviewed expectation, actual route/calls/results,
  generated answer, failed criterion and supporting evidence. Dataset/reference
  provenance belongs beside these results, with downloads of synthetic reports.
- Clear empty, loading, unavailable, invalid-report and partial-score states.
  Refresh, filters, detail selection and download only read saved reports.

Start with CLI execution and a read-only Settings page. A later “Run evaluation”
control requires its own bounded job/submission/cancellation/cost contract; do not
hide execution behind page entry. Existing reports can be judged again explicitly
without replaying tools. Initial reports contain only curated synthetic data.

Reuse the existing 760 px Settings reading layout, native tables/expanders,
VT323 headings, IBM Plex Mono content, square borders and semantic colors from
`docs/design-system.md`. Figma Foundations metadata was inspected on 2026-10-14;
it contains no evaluation-specific composition. The proposed native adaptation
needs agreement at the UI slice; new reusable dashboard patterns require discussion.

Hosted display is a separate packaging decision within the UI slice: Docker
currently omits the classifier CSV and generated reports. Propose shipping an
explicitly selected synthetic baseline report for the demo, with its evaluated
commit/date and stale-version warning; do not portray it as a live hosted run.
Generated cloud reports remain disposable under Render Free's current contract.

## Semantic judging and safe execution

Begin with human review for factual faithfulness, coverage and relevance. An
optional model judge follows only after agreeing its model, dataset exposure and
call budget. Prefer a supported model through the existing Groq integration;
confirm current schema/model compatibility before implementing. No additional
provider or embeddings are needed for the initial rubric.

Pin the judge prompt/version, use structured results with source evidence, treat
case text as untrusted data, and do not give the judge tools. Blind app-version
labels and vary order for pairwise comparisons. Review a small balanced calibration
set independently with a human, include intentionally defective outputs, compare
agreement/disagreements and check repeat stability. Same-family judges can share
generator biases; retain that limitation. Research documents position, verbosity
and self-enhancement bias in [LLM-as-judge evaluation](https://arxiv.org/abs/2306.05685).
Judge scores must never silently replace missing human references or establish
side-effect safety.

Live execution uses dedicated subprocesses/temporary databases and a fixed test
clock, synthetic recipients, disabled worker startup and an SMTP double that
rejects real delivery. Assert storage isolation before any case can schedule.
Exercise actual scheduling logic against disposable records rather than replacing
it with a canned success. Production chat/reminder files and operational metrics
remain outside these runs. No evaluation invokes a real email sender.

Record every planned case, including unavailable-provider cases. Report model
quality on scorable responses alongside availability/overall goal success so
excluding timeouts cannot inflate success. Stop a run at its explicit case/call
budget; expose exhaustion. Repeat a representative live subset three times for
stability, retaining each sample; temperature zero does not imply determinism.

## Bounded implementation order and verification

Each row is a separately discussed slice with a scoped commit in the single shared
draft PR #55. Its verification scope is confirmed before coding. Update this
file's completion table, `docs/PLAN.md` and `docs/agents_doc.md` with actual results,
limits and the next step after each slice. Keep slice commits distinct during
the build; do not create or merge a PR for an individual evaluation slice.

| Slice | Deliverable and contract | Proportional verification |
| --- | --- | --- |
| 1 — Local baseline | Versioned case/report schemas, 24-case development pilot, saved classifier holdout evaluation, local FAQ and classifier route-eligibility checks, atomic reports and CLI. Eligibility does not execute or evaluate LLM runtime handoff. No live LLM or UI yet. | Known hand-computable scorer cases; reproduce fingerprinted classifier metadata without fitting; wrong-policy/no-match cases; zero denominators; malformed references/reports; interrupted writes; prove zero model/scheduling/SMTP calls. One CLI run produces inspectable per-case evidence. |
| 2 — Settings catalogue | Read-only list/detail APIs and Evaluations page with summaries, literal case evidence, Refresh/Return, missing-score states and synthetic baseline packaging agreed here. | API empty/missing/corrupt report cases and path handling; Streamlit navigation/draft retention/locks; assert reruns/refresh make no execution calls. After automated checks, inline browser review on desktop/mobile and refresh; leave app open for user verification. |
| 3 — Real workflows and agent | Extraction, trajectory, compound/history, reminder/recovery evaluators; independent case expansion and isolated opt-in live runner. | Provider doubles verify evaluators and failure reporting; live samples evaluate real models. Verify exact payloads, dependencies, forbidden calls, clarification, time/zone resolution, partial failures, one-time creation and read-only restoration. Inspect disposable DBs and SMTP call counts. |
| 4 — Generation quality | Reviewed reference facts/rubrics; persisted human annotations; optional validated judge; groundedness/coverage/relevance scores and compatible run comparison. | Hand-scored good/bad answers, fabricated policy/number/date, omitted uncertainty, unsupported draft promise, off-topic prose, judge malformed output/timeout/injection; actual human agreement if annotations are available. Repeated live subset, with app vs judge failures distinguished. |
| 5 — Assessment and CI | Deterministic evaluation regression checks in existing CI, final benchmark report, browser walkthrough and assessment talking points. Live evaluation stays explicitly invoked outside credential-free CI. | Existing full offline suite/dependency/whitespace checks; deliberately wrong output must fail the appropriate evaluator; compatible baseline comparison; fresh/restart/refresh UI checks; export agrees with displayed scores; app remains open for user review before merge. |

The 24-case pilot is development data. Preserve the existing 200-row router
holdout for historical comparison, and freeze the new semantic holdout before
running live benchmark claims. Framework tests, application tests and live model
evaluations are three different types of evidence and must stay labelled.

Proposed gates: 100% agreement on hand-computable scorer contracts; zero observed
critical violations (unauthorized action, duplicate creation, fabricated delivery
claim) in the relevant cases; report exact counts rather than claiming universal
safety. Adopt task-quality thresholds only after reviewing development baselines,
then freeze them before the holdout. The historical classifier 98% precision
criterion is not an automatic quality target for generation. Show confidence
intervals for accuracy/pass rates and sample counts; 47/47 is not proof of perfect
future precision. CI should gate deterministic regressions, not unstable live
judge scores. Latency budgets need measured baselines, not invented SLAs.

## Assessment talking points and final evidence

The eventual assessment pack should contain a frozen run report, dataset/label
provenance, classifier confusion/calibration views, category results and counts,
one successful trace, one honest failure/clarification trace, version comparison
and measured limits. Prepare answers to:

- **Why evaluate beyond classifier accuracy?** A correct intent can still produce
  wrong arguments, retrieve insufficient policy facts or generate unsupported prose.
- **What is ground truth?** Reviewed labels, payloads, policy IDs, source facts and
  acceptable outcomes, with development/holdout separation and provenance.
- **How is the agent evaluated?** Required/forbidden observable actions, validated
  arguments, dependency use and final goal satisfaction; flexible independent order.
- **Relevance versus faithfulness?** An answer can address a question while inventing
  a policy fact, or state true facts while omitting the requested information.
- **Why these tools/frameworks?** Local deterministic scorers fit current traces and
  policy IDs; human/model semantic review is added where exact comparison is inadequate.
- **How are reminders tested safely?** Real creation logic in isolated storage,
  frozen time, no worker, blocked SMTP and duplicate/recovery call-count checks.
- **What do the numbers prove?** Performance on the identified samples/configuration,
  with synthetic-data and judge limitations; they do not establish real-world SLA
  reliability, inbox delivery or a real company's policy accuracy.
- **How does evaluation guide improvement?** Classify failures by routing,
  extraction, retrieval, presentation, provider or persistence, fix one agreed slice,
  and compare a compatible regression run while preserving fresh evaluation data.

The implementation review must report actual automated/live/browser checks, failed
cases, unresolved blockers and limits. Slices 1–2 supply the local baseline and read-only Settings display;
the live workflow/agent verification and generation quality benchmark remain
unverified/unimplemented respectively.
