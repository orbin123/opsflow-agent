# Evaluations

Settings → Evaluations has two sections: the classifier classification report and
one generation-quality table. Calculation explanations are collapsed by default.
The page has no run history, report downloads, raw logs/JSON, case selectors or
comparison controls. Opening it and ordinary chat use never trigger evaluation.

## Classifier report

The page reads `artifacts/models/intent_router_svm_metadata.json`, recorded on
2026-10-04 alongside the trusted TF-IDF + sigmoid-calibrated linear SVM. The model
file's SHA-256 must match the metadata. This read does not deserialize the model,
predict, train, call a provider or execute tools. Docker already includes both
model files; no additional evaluation report is packaged.

The dataset contains 1,000 fictional labelled requests across eight intents. The
recorded deterministic stratified split used 800 development and 200 holdout
examples, with 25 holdout examples per intent. Scores describe that same-source
synthetic holdout, not current live chat or generated-answer quality.

The full classification report displays per-intent precision, recall, F1 and
support, plus overall accuracy (0.88) and macro/weighted averages (F1 0.8813).

- Accuracy = correct intent predictions / all holdout examples.
- Precision = correct predictions of an intent / all predictions of that intent.
- Recall = correct predictions of an intent / all examples labelled with that intent.
- F1 = 2 × precision × recall / (precision + recall), with the recorded scorer's
  zero-denominator convention of zero.
- Support = number of holdout examples labelled with an intent.
- Macro average = unweighted mean across the eight intents (12.5% each).
- Weighted average = sum of each intent's score × support / total support.

Per-class scores and accuracy are read from metadata; macro and weighted rows
are simple arithmetic over the recorded per-class scores. Recorded aggregate F1
and accuracy must agree with the rows, labels/split/support must agree, and scores
must be finite and in range. Missing, invalid or mismatched evidence returns a
safe unavailable state. No report storage, execution CLI or evaluation run catalogue
remains in this implementation.

`GET /api/v1/evaluations` returns this compact validated classifier report.
There are no mutation or per-run detail endpoints. The old catalogue response
contract is intentionally removed with the user's approved scope reduction.

## Generation quality

One six-row table defines faithfulness, coverage, relevance, instruction
compliance, status accuracy and context relevance. All ratings say **Not scored**:
no human-reviewed answer dataset or ratings have been supplied. These are review
criteria, not measured model-quality results. No Ragas, automated judge, annotation
import, saved review snapshots or comparison pipeline remains.

The collapsed explanation describes reviewing an actual answer against the request,
source text, retrieved policy, relevant conversation history and tool/action outcomes.
A human must check reference facts and record an evidence-based rating. The manual
scale is 0 (fundamental failure), 1 (major errors/omissions), 2 (minor errors/omissions)
and 3 (fully meets the criterion). Missing review is not a zero.

Each dimension stands alone. If answer reviews are added in a separately agreed
future slice, its mean would use supplied ratings with equal weight per answer and
an explicit reviewed count. There is no combined generation score or custom
weighting across dimensions. Critical fabricated action/delivery claims must stay
explicit rather than being cancelled by other high scores.

## Navigation and scope

Return to chat preserves the selected chat and its browser-session multiline draft.
Existing running/pending/unsaved locks remain. Browser reload retains existing
page/session-draft limitations; it restores the chat URL rather than a durable
Evaluations page selection. The backend endpoint and UI only read results.
The separate chat Activity and monitoring features are unaffected.
