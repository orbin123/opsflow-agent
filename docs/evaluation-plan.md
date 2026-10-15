# Evaluation submission plan

## Final publication — authorized 2026-10-15

The user authorized review/merge of all remaining PRs and verification of the
existing deployment. Publish the final simplified scope in #55, retain the
scoped signed commits and require CI/DCO before merge. Check the combined tree
with the reviewed #54 configuration fix; then confirm main CI, matching Render
release and hosted Evaluations. Earlier no-publication statements below are
historical boundaries superseded by this instruction. No new scoring collection
or application feature is authorized.

## Current approved scope — 2026-10-14

**Presentation update:** The user requested shorter project-voice explanations,
without visible subagent wording. Use bold Markdown labels and a concise automated
sample-review caption; preserve the evidence origin and scores. This is wording
and formatting only, not personal/manual grading or new model execution. All
37 focused checks, dependencies/whitespace and inline desktop/mobile formatting
checks pass; saved evidence and scores are unchanged.

**Latest scoring request:** The user approved delegated testing of actual generation
outputs to fill the six scores. A subagent reviewed eight planned fictional
application examples, with a 20-provider-attempt cap and isolated state/blocked
delivery. The results must be labelled AI-reviewed development samples, with
real denominators, retained failures and evidence. One compact data file and
read-only display are authorized; the removed evaluation machinery stays removed.
Ragas, automatic chat scoring, human-review claims and merge/deployment remain
excluded. This overrides the earlier pending-score/live-sample exclusion for this
bounded review. Collection is complete: eight planned cases, five available answers,
12 actual Groq attempts and three rate-limited cases retained unscored. All six
aggregate dimensions have ratings; details and defects are in docs/evaluation.md.
The new read-only display is verified locally: 1,227 offline tests and final 37
focused checks pass, along with dependencies/whitespace, native ARM64 Docker
packaging/authentication and inline desktop/mobile/explanation/Return/draft/reload
checks. Packaged file/API/table means agree; browser reads leave backend task
counts and review-chat turns at zero, with no review-server reminder database.

The user replaced the earlier five-slice implementation plan with a simple
submission page: **classifier report, then generation quality**. Ragas, external
judge API calls and automatic evaluation of chat turns are excluded. The user
explicitly asked to remove unwanted code instead of retaining it as backup.

## Deliverable

1. **Classifier report:** display the trained TF-IDF + calibrated linear SVM's
   saved eight-label precision, recall, F1, support and overall accuracy. Include
   macro and support-weighted averages. Read the existing model metadata; do not
   execute or retrain the classifier on page entry. Explain the 1,000 fictional
   examples, 800/200 stratified split, formulas and weighting in a collapsed panel.
2. **Generation quality:** one six-row table for faithfulness, coverage, relevance,
   instruction compliance, status accuracy and context relevance. Use the explicitly
   collected AI-subagent sample ratings, label their origin and
   show rated/applicable counts. Human ratings remain absent. Explain each criterion,
   the 0–3 scale, source evidence, limitations and equal per-answer weighting in a
   collapsed panel. No aggregate generation score.

Remove the run history/catalogue, report downloads, logs/traces, per-case raw JSON,
annotation import/snapshot/comparison workflow, isolated runtime evaluation harness,
report storage/CLI and their development fixtures/tests. These features are removed,
not hidden. The existing chat application, reminder worker and monitoring stay
outside this evaluation-only removal.

## Verification

- Check saved classifier values, all eight labels and macro/weighted averages.
- Reject malformed metrics and mismatched model/metadata; show a safe unavailable
  state without hiding the generation criteria or Return to chat.
- Prove GET/UI reads never load/run/train a model or execute chat/tools.
- Check supplied AI ratings/means/counts, missing/inapplicable/invalid data, no invented
  weights, only two visible sections, no obsolete controls, and existing navigation/draft preservation/locks.
- Run the full offline suite, dependency/whitespace and container packaging checks.
- Review desktop/390 px mobile, explanation panels, navigation and reload in the
  inline browser. Leave the page open for independent user verification.

## Continue in a new chat

Use `/Users/orbin/.codex/worktrees/evaluation-baseline/opsflow-agent`, branch
`feature/evaluation-baseline`, and existing draft
[PR #55](https://github.com/orbin123/opsflow-agent/pull/55). Preserve primary-checkout
changes belonging to the separate workflow configuration fix. Keep scoped,
user-only DCO-signed commits; do not squash previous slice boundaries or open a
second evaluation PR. The current scope supersedes earlier five-slice next steps.

**Status:** simplified page and sample display merged in PR #55 as `a5c1f4d`
after final CI/DCO passed. The combined 1,233 tests pass. Main CI `38668904494` passes; Render deployment
`dep-db83a6k9v7es73bg9d1g` is live on the exact merge SHA. Hosted access checks
pass. Chrome verifies both tables, ratings/counts and short explanations after
reload. Hosted Evaluations stays open; no new scoring or chat execution ran.
The app remains open on 8517/backend 8024. Source execution was recorded at
`e6a30b0`, with a post-collection runtime-source audit; exact dirty state at
invocation was not captured. Human calibration, independent reference review,
repeat stability and the three rate-limited cases remain outstanding. These are
small development-sample ratings, not a general quality benchmark. User approved final review/merge and existing deployment on 2026-10-15.
No Ragas, external judge API or SMTP/worker is authorized. Further collection requires its
own bounded discussion; reopening the page never regenerates scores.
