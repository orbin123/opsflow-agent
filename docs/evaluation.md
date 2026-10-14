# Local evaluation baseline

The first evaluation slice runs the saved intent classifier and local fictional
FAQ retriever explicitly. It does not invoke the agent, a language model, chat
persistence, reminder creation or delivery. Settings → Evaluations reads its saved
reports; see [evaluation-plan.md](evaluation-plan.md).

## Run and inspect

From the repository root, with its existing dependencies installed:

```bash
python -m app.evaluation
python -m app.evaluation --report-dir /absolute/path/to/local/reports
```

The default is the ignored `var/evaluations/` directory. Set
`OPSFLOW_EVALUATIONS_DIR` to share another report root between the CLI and API;
`--report-dir` overrides it for that CLI invocation. Relative configured paths
resolve against the process working directory; absolute paths are recommended.
Every run owns a new
opaque run-ID directory containing `report.json`. The console prints its absolute
path, execution state, quality verdict and selected metrics. A completed run exits
zero even when it finds incorrect predictions: no quality threshold is agreed yet.
Startup/storage failures and failed/interrupted execution exit nonzero.

Read a report without reexecution:

```python
from pathlib import Path
from app.evaluation.reports import load_report

report = load_report(Path("/absolute/path/to/run-id/report.json"))
for item in report.cases:
    if False in item.checks.values():
        print(item.case.case_id, item.case.input, item.actual, item.checks)
```

`app.evaluation.scoring` contains pure scorers for saved observations. Importing
them, loading a report and inspecting its values never calls application tools.
The runner imports only the trusted local classifier and pure FAQ retriever.

## What is measured

- **200 original classifier holdout cases:** reproduce the notebook's stratified
  split using recorded seed 20261004, without fitting or selecting a threshold.
  Verify dataset/model fingerprints and record accuracy, macro F1, per-label
  precision/recall/F1, confusion matrix, log loss, Brier score, ECE and reliability
  bins. Brier sums squared errors across classes; ECE uses ten equal-width
  top-label confidence bins. Historical threshold precision/coverage remain
  classifier-only measurements, not actual chat routing results.
- **Eight routing development cases:** one per intent, recording intent accuracy
  and permitted classifier eligibility. Agent-only intents must stay ineligible
  for the fixed-workflow threshold. Eligibility does not execute the agent or
  decide whether extraction would clarify, proceed or hand off.
- **Sixteen FAQ development cases:** policy matches, ambiguity, no-match and two
  relevant policies with missing applicability details. Compare retrieval status,
  policy ID and the exact stored answer. Match precision/recall and false
  acceptance have explicit counts. Answer sufficiency is **not scored** because
  this slice does not run a presenter or semantic judge.

`data/evaluation/local_pilot.json` is versioned, AI-authored development data
**pending human reference review**, not established ground truth or a new held-out
benchmark. References were written before execution and are retained even when
the current tools disagree. Policy IDs must exist; matched references identify
source sufficiency; duplicate IDs, indexed FAQ questions, inconsistent reference
fields and changed policy fingerprints are rejected before execution.

Reports separate `state` (execution) from `quality_verdict` (observed criterion
failures). Every planned case remains visible, including `not_run` and failed
cases. A null check or zero-denominator metric is unscored, not perfect. Availability
counts all planned cases; criterion metrics count scorable observations. Wilson
95% intervals describe binary sample proportions and do not establish future
performance. No aggregate task-quality acceptance target has been chosen.

Provenance records source commit/dirty state, implementation and data/model
fingerprints, scorer/schema versions, split, threshold, Python/dependency versions
and reference-review status. Language-model and judge fields say `not_invoked`.
Generate a fresh report after code changes; reports are not overwritten or reused
as fresh execution evidence.

## Storage and interruption

Exclusive run-directory creation gives each run one writer. Initial and terminal
snapshots use a temporary file, file flush/fsync and atomic replacement. A failed
replacement leaves the prior valid snapshot, and a finished writer refuses more
updates. JSON/schema validation rejects malformed reports and inconsistent case,
metric or run states. This is local report storage, not a new SQLite database.

Ctrl+C during execution saves an interrupted report with completed observations
and unexecuted cases. A forced kill can leave the initial `running` snapshot with
planned cases but no execution results; per-case checkpoints are not implemented.
Treat such a snapshot as incomplete. Reading never resumes it. A storage failure
during finalization may likewise leave the initial snapshot; the CLI reports
failure rather than claiming a saved terminal result. Atomic replacement does
not promise survival of every filesystem or power-loss failure.

The normal CLI belongs in a separate offline process. It makes no production
task/HTTP metrics and never starts the reminder worker. Generated reports contain
synthetic source text, not sanitized operational logs. Do not use real employee
data with this development pilot. Docker packages only the explicitly selected
historical synthetic baseline, not the classifier CSV, pilot or local generated
reports. It does not run evaluation.

## Observed development baseline — 2026-10-14

All 224 cases executed. The historical holdout reproduces accuracy **0.8800**,
macro F1 **0.8813**, log loss **0.4549**, Brier **0.2226** and ECE **0.1606**.
The 0.71 threshold accepts 47/200, all 47 with correct intents; its Wilson lower
95% bound is approximately 0.9244, not a guarantee of perfect future precision.

The router pilot has **7/8 correct intent labels** and **8/8 allowed eligibility
decisions**. Its unsupported flight-booking request is predicted as reminder
creation at low confidence and stays agent-required. No booking or reminder runs.

The FAQ pilot has **12/16 exact status matches**, **8/8 correct accepted policies**,
**8/10 expected matches retrieved**, and **0/6 false matches on ambiguity/no-match
references**. Payslip wording and the temporary-employee salary question return
no-match. Two broad leave/payroll ambiguity references also return no-match;
both abstain safely, but differ from the provisional exact-status label. Human
review should adjudicate these references before treating them as ground truth.
Missing-detail clarification and generated policy claims remain unverified.

## Settings catalogue (slice 2)

`GET /api/v1/evaluations` lists saved runs and the selected bundled baseline.
`GET /api/v1/evaluations/{run_id}?source=local` returns the exact validated Report
with its source; `source=bundled` selects only the tracked historical baseline.
Run IDs are 32 lowercase hexadecimal characters. No mutation/execution endpoint
is provided. These readers import no runner, classifier or application tools.

A missing local root is empty and is never created. Invalid/missing/unreadable
run snapshots remain visible in the catalogue. Detail responses use 404 for missing,
422 for invalid identities/schema/symlinks and 503 for unavailable storage; no raw
filesystem or exception information is returned. IDs must agree with the saved
report. Run/report symlinks are rejected. The configured root is trusted local
storage: this is not a multi-user or hostile concurrent-filesystem boundary.
Finished, failed, interrupted and incomplete `running` snapshots are read literally,
without repair, rescoring or resume. A snapshot cannot prove a process is still active.

Settings → Evaluations reuses the native 760 px Settings layout and navigation locks.
Refresh and selection use GET; downloads serialize the selected validated Report
without recalculating it. Empty/error states retain Return to chat. Browser-session
multiline drafts and selected chats survive navigation; a browser reload still has
existing session-draft limitations. Lists include suite/date/source commit/model/
pilot fingerprint; detail exposes full provenance, counts, metric definitions,
classifier details and literal per-case references/observations. Missing values
remain unscored. Classifier eligibility/retrieval are not runtime/semantic quality.
Later unimplemented categories say Not evaluated; no single agent accuracy is shown.
Filters, comparison and run controls remain later slices.

`data/evaluation/baseline.json` is an exact copy of selected run
`89c111c7f91d4382b6ca872b62dbada4`, evaluated locally on 2026-10-14 at clean commit
`140d8f6`. The page displays its recorded date/commit, pending human-reference
review and historical-version warning. It is not a live hosted run or evidence
for the currently deployed version. Generated Docker/Render records use disposable
`/tmp/opsflow-data/evaluations`; no reports are generated at startup. Packaging
this baseline does not authorize deployment or live evaluation.


## Runtime harness (slice 3, approved offline scope)

```bash
python -m app.evaluation --suite runtime
python -m app.evaluation --suite runtime --case agent-policy-to-draft --case reminder-saved-replay
python -m app.evaluation --suite runtime --case extract-missing-source --repeat 3
```

Runtime defaults to **scripted provider doubles**, with the unchanged application
workflows, agent loop, classifier, tools, HTTP/SSE and storage paths. The 24 new
scenarios comprise eight standalone extraction, eight agent/compound/history and
eight reminder/recovery cases. Standalone observations preserve the actual workflow
record and declare runtime routing unobserved/unscored; chat cases retain actual
classifier/runtime routing. References in `runtime_pilot.json` were authored
before execution and remain **pending human review**. `runtime_scripts.json`
contains separate synthetic provider responses; passing these cases verifies
contracts, not a model's decisions or general robustness. They are development
cases, not the proposed future independent semantic holdout.

Each selected sample runs in a fresh subprocess and disposable directory. Before
application imports, the worker fixes chat/reminder paths, blocks worker imports
and SMTP constructors, and blocks socket connections in scripted mode. SQLite
connections are restricted to those two disposable files; isolation is checked
again before actual reminder insertion. Reminder context/resolution/creation use
a frozen instant and real scheduling logic. Real provider factories are replaced
only in scripted mode. Parent/operational databases and process metrics are not
used. No delivery worker, real email recipient or SMTP submission is permitted.
Temporary files are removed after observations; reports retain literal records,
creation keys, turn outcomes and read/replay evidence, not disposable database paths.

The run records **every planned sample**, including not-run, budget-limited,
interrupted and failed collection. Defaults are 24 samples and at most 60 model
attempts. `--max-cases` (1–72), `--max-model-requests` (1–60), `--case` and
`--repeat` (1–3) are explicit runtime options. Repeated samples keep distinct IDs.
Wrappers count orchestration, extraction/presentation and summary/draft model
invocations, including the existing bounded rate-limit retry. A denied request
never calls the provider. Timeout or unmeasured worker failure stops the run
rather than assuming a fresh call budget. Successful observations are checkpointed
atomically; page entry/refresh never starts, resumes or rescores a run.

Schema-v2 reports preserve raw observable executions, tool arguments/results,
workflow/SSE events, replies, model-attempt timings, human input transported to
the agent, HTTP transport and terminal outcome status, isolated reminder records
and recovery evidence. They record data/script/code/model hashes, configured
model IDs/settings for opt-in live mode, dependency/scorer versions and budgets.
No private reasoning, system prompt, credentials or raw provider response is saved.
Readers remain compatible with schema-v1; Docker still bundles only the selected
historical schema-v1 baseline, never runtime cases or execution at startup.

Pure `runtime_scoring` checks exact literal argument fields, maximum one-to-one
call matching/multiplicity, independent versus required order, exact dependency
values from prior tool results, policy IDs, successful result presence, transported
user history, expected outcomes, forbidden calls and isolated state. Reminder task
and zone stay literal; due/creation timestamps compare as aware instants (precision
or equivalent UTC notation alone must not cause a miss). Replay closes/reopens
storage, submits the same turn ID and compares exact saved outcomes/state while
asserting zero new model/tool calls. Interrupted recovery only reads retained state.

Metrics distinguish observation coverage, application availability and observable
contract success, all with explicit planned-sample denominators. Controlled partial
failures can pass their expected failure-handling contract while remaining failures
in application availability. Tool precision uses recorded calls once; required-tool
coverage includes all planned required calls. Empty tool denominators are unscored;
no-call constraints are separate. Supporting evidence reports matched/missing/extra
calls. Per-criterion aggregates count only recorded applicable checks. Recorded
counts and nearest-rank scenario p50/p95 are descriptive; unknown worker attempts
are not included in those observed counts. No live SLA, NLP accuracy, semantic
faithfulness/relevance or complete user-goal score is claimed.

Settings shows schema-v2 mode qualifications, harness versus application outcomes,
exact per-turn source/reply/execution, saved stage events, state/recovery evidence
and criterion details. Generated-answer semantics remains Not scored. All controls
remain GET/read-only; no Run evaluation control was introduced.

**Live verification was explicitly deferred by the user on 2026-10-14.** The runner
supports explicit `--suite runtime --mode live` with existing configured Groq
factories and the same isolation/call cap. It is not invoked automatically. Live
provider/configuration compatibility, extraction/trajectory quality and three-run
model stability are unverified; human reference review is also outstanding. Do not
call the original full slice 3 live-validation plan complete. The user subsequently
approved proceeding to slice 4's offline saved-review scope, keeping these gaps and
the optional judge deferred.

## Saved generation review (slice 4, offline scope)

Slice 4 processes **saved schema-v2 runtime outputs**, without rerunning application
code, models, tools, scheduling or delivery. Its schema-v3 snapshots coexist with
schema-v1/v2 reports. The original runtime report is never modified. Snapshot
`completed` means review processing completed, not application success or completed
human review. Application mode, historical commit/configuration, source-report
fingerprint, reference/rubric/review fingerprints and semantic implementation hash
remain visible. The optional model judge and all live calls remain deferred.

Prepare an annotation template and an unscored snapshot explicitly:

```sh
python -m app.evaluation.semantic_review \
  --report /absolute/path/to/runtime/report.json \
  --template /absolute/path/to/annotations.json
```

The template uses exclusive creation and refuses to overwrite a previous file.
Without `--template`, the same command saves only an unscored snapshot. Report
storage uses the existing `--report-dir`/`OPSFLOW_EVALUATIONS_DIR` contract. Every
snapshot gets a new run ID; saved results are immutable through these commands.

`data/evaluation/semantic_references.json` supplies eight development targets:
summary facts, draft facts, prior-turn summary, policy-to-draft coverage, missing
FAQ eligibility, reminder status, partial-failure status and unavailable summary.
Tool outputs and final replies are separate targets. Selected runtime subsets retain
missing cases/outputs in planned denominators; repeated samples remain separate.
Actual output, input/history, local tool evidence and isolated reminder state are
retained. Generated summaries/drafts and the evaluated reply are excluded from
source evidence so an answer cannot ground itself.

These references were authored **after scripted runtime collection**, not before an
independent benchmark. They remain AI-authored development review material pending
human review. Required facts have stable IDs and literal source quotes. The six
0–3 rubric dimensions are faithfulness, coverage, relevance, instruction compliance,
status accuracy and context relevance. Scales and explanations are versioned in
that file. Context relevance covers the supplied resource/history and acknowledged
information gaps; coverage concerns what the answer expresses. No embedding/Ragas
implementation or keyword-based semantic inference is claimed.

A human reviewer inspects each target's saved output/evidence and its reference:

1. Resolve incorrect/disputed reference facts in a new references file, prepare a
   new template with `--references`, and retain the prior snapshot for provenance.
2. For each reviewed target, enter `reviewer`, timezone-aware `reviewed_at` and
   `reference_reviewed: true`. Software checks this **attestation**, not identity
   or whether the semantic judgment is correct. No AI review is labelled human.
3. Rate each requested dimension with `status: scored`, `score: 0`–`3`, and a short
   evidence-based `explanation`. Alternatives are `not_scored`, `not_applicable`
   and `scorer_error`, each with an explanation and null score. Required facts make
   coverage applicable. Leave unavailable outputs unscored.
4. Review factual claims using literal `output_quote`, `supported`, `explanation`
   and a literal `source_quote` for supported claims. Set `claims_complete` only
   after reviewing all factual claims. Zero claims produces an unscored claim ratio.
5. Review every required fact by `fact_id`, `expressed`, `explanation` and a literal
   `output_quote` when expressed with source support. Set `facts_complete` only
   when all required facts were reviewed. Omissions have no answer quote.
6. Set `critical_review_complete` when unauthorized-action/fabricated-delivery or
   other critical findings have been inspected. Keep each finding in
   `critical_violations`. Findings force `has_failures` even alongside high ratings.

Preserve every template entry, including unreviewed targets. Fingerprints bind
annotations to the source report, reference/rubric, sample, exact output and source
evidence. Unknown/missing/duplicate targets, invalid scores, missing attribution,
stale hashes, nonliteral evidence, fabricated source quotes and contradictory
fully-faithful/full-coverage ratings are rejected. Text remains untrusted data;
no evaluation follows source instructions or invokes a judge.

Save the reviewed/partially reviewed snapshot:

```sh
python -m app.evaluation.semantic_review \
  --report /absolute/path/to/runtime/report.json \
  --annotations /absolute/path/to/annotations.json
```

The CLI accepts only `origin: human`. `synthetic_test` exists for explicitly labelled
fixture checks and cannot be imported through the human CLI. Harness fixtures
exercise good/bad arithmetic and findings; they are not independently supplied
human annotations or evidence of model quality. Actual human review remains absent
until the user supplies it. Missing/partial/scorer-error counts stay beside scores.

`semantic_scoring` performs pure arithmetic over explicit judgments, never semantic
classification. Means use scored applicable dimensions only; supported-claim and
required-fact ratios use explicitly complete reviews only. Review/output coverage
retain missing planned targets. Empty denominators remain unscored. A rubric check
means **fully meets (3)**; lower ratings flag rubric issues, without adopting a
benchmark acceptance threshold. The quality verdict covers recorded criteria,
with missing reviews still visible. No overall agent accuracy or universal safety
claim is produced.

Settings shows literal answers, required facts, source evidence, per-dimension
ratings/reasons, review origin and critical findings. Comparison reads two saved
snapshots. Matching reference/rubric/scorer implementation/runtime dataset, execution mode, annotation
origin and target/sample sets are required. Only paired scored dimensions get a
delta; missing pairs have none. Changed app/prompt/model configuration and review
fingerprints are explicit. No comparison between scripted and live evidence or
between human and synthetic fixture annotations is allowed. Refresh, selection,
comparison, Return and downloads remain read-only, with no scoring entry-point,
provider or tool invocation. Saved-schema validation checks identities and aggregate
arithmetic without creating or updating scores.
