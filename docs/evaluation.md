# Local evaluation baseline

The first evaluation slice runs the saved intent classifier and local fictional
FAQ retriever explicitly. It does not invoke the agent, a language model, chat
persistence, reminder creation, delivery or the UI. Settings → Evaluations remains
the proposed next slice; see [evaluation-plan.md](evaluation-plan.md).

## Run and inspect

From the repository root, with its existing dependencies installed:

```bash
python -m app.evaluation
python -m app.evaluation --report-dir /absolute/path/to/local/reports
```

The default is the ignored `var/evaluations/` directory. Every run owns a new
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
data with this development pilot. Docker does not currently package the classifier
CSV, pilot or generated reports; hosted evaluation display needs the next slice's
explicit packaging decision.

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
