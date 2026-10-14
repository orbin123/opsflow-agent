# Evaluation submission plan

## Current approved scope — 2026-10-14

The user replaced the earlier five-slice implementation plan with a simple
submission page: **classifier report, then generation quality**. Ragas, live
model judging and automatic evaluation of chat turns are excluded. The user
explicitly asked to remove unwanted code instead of retaining it as backup.

## Deliverable

1. **Classifier report:** display the trained TF-IDF + calibrated linear SVM's
   saved eight-label precision, recall, F1, support and overall accuracy. Include
   macro and support-weighted averages. Read the existing model metadata; do not
   execute or retrain the classifier on page entry. Explain the 1,000 fictional
   examples, 800/200 stratified split, formulas and weighting in a collapsed panel.
2. **Generation quality:** one six-row table for faithfulness, coverage, relevance,
   instruction compliance, status accuracy and context relevance. Human ratings
   have not been supplied, so show pending review rather than invented scores.
   Explain each criterion, the manual 0–3 scale, source evidence and equal
   per-answer weighting in a collapsed panel. No aggregate generation score.

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
- Check pending generation scores, no invented weights, only two visible sections,
  no obsolete controls, and existing navigation/draft preservation/locks.
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

**Status:** implemented and verified locally. All 1,210 offline tests pass,
including 20 focused evaluation checks; dependencies/whitespace and native ARM64
Docker build/authentication checks pass. Packaged metadata reads without evaluation
fixtures. Inline desktop/390 px mobile verifies values, collapsed explanations,
table-contained horizontal scrolling, Return/draft and reload selection. Review
backend task counts remain zero, the review chat has zero turns and no reminder DB
exists. App stays open on 8517/backend 8024. Figma deeper inspection is quota-limited;
the documented native adaptation was used. Publication/user review remains pending. No Ragas/live model,
judge, SMTP/worker, merge or deployment is authorized. Generation quality has no
actual human scores and cannot be claimed as a completed benchmark. The classifier
results remain limited to the recorded same-source synthetic holdout.
