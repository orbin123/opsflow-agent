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

The same six-row table now reads `data/evaluation/generation_quality.json`, a
single explicitly collected AI-subagent review of actual Groq/application outputs.
There is no Ragas, automated judge API, catalogue, annotation-import workflow or
scoring on normal chat/page entry. `GET /api/v1/evaluations/generation` only validates
and returns this saved sample; means/counts are arithmetic over its explicit ratings.
Invalid or missing data remains unavailable, never a fabricated zero or pass.

The 2026-10-14 pilot planned eight fictional cases: factual and uncertainty/injection
summaries, constrained email draft, policy explanation, missing contractor eligibility,
history follow-up, policy-to-draft and reminder status. Five outputs were available
in 12 real Groq attempts (nine successful and three rate-limited), using
`openai/gpt-oss-20b`. Two examples used actual standalone generation tools; the
others used the chat/session runtime. Storage was disposable, SMTP/worker execution
blocked and collection retries disabled. No reminder was created and no email was submitted or delivered.

The reviewing subagent assigned the existing 0–3 scale against source facts,
request constraints, actual policy/tool evidence and application outcome labels:
0 fundamental failure, 1 major error, 2 minor error, 3 fully meets. These are AI
judgments, not independently supplied human labels. References and ratings came
from the same reviewing agent; human calibration and repeat stability are absent.
The eight examples are development material, not a representative held-out benchmark.

| Dimension | Mean / 3 | Rated / applicable planned answers |
| --- | ---: | ---: |
| Faithfulness | 3.00 | 5 / 8 |
| Coverage | 2.80 | 5 / 8 |
| Relevance | 3.00 | 5 / 8 |
| Instruction compliance | 2.80 | 5 / 8 |
| Status accuracy | 2.33 | 3 / 6 |
| Context relevance | 3.00 | 5 / 8 |

Each dimension's mean = sum of supplied applicable ratings / number of rated
applicable answers, with equal weight per answer. Missing outputs/reviews remain
in the applicable planned count; genuinely inapplicable dimensions are excluded.
Two pure summaries have no action-status claim and are inapplicable for status
accuracy. The three rate-limited cases retain null scores and failure evidence;
history generation, compound drafting and successful reminder status remain unassessed.
There is no combined generation score or percentage interpretation.

The contractor answer correctly acknowledges missing eligibility but its application
outcome incorrectly says `completed` instead of the prompt-required
`needs_clarification`. It also says demo without explicitly saying fictional.
These defects reduce status/instruction/coverage ratings and remain in the evidence;
this scoring slice does not change the workflow. No unauthorized action or fabricated
delivery claim was observed among available outputs. Such critical findings would
stay explicit in the page rather than being averaged away.

The saved sample records the execution-source commit `e6a30b0`; a post-collection
source audit matched 36 runtime/data/model files to that commit. The exact dirty
state at invocation was not captured, so no clean-invocation claim is made. Results
are historical sample evidence, not verification of every future or hosted answer.
The collapsible explanation shows definitions, model/version/date, reviewed counts,
limitations and a representative lowest-rated case's reason for each dimension.

## Navigation and scope

Return to chat preserves the selected chat and its browser-session multiline draft.
Existing running/pending/unsaved locks remain. Browser reload retains existing
page/session-draft limitations; it restores the chat URL rather than a durable
Evaluations page selection. The backend endpoint and UI only read results.
The separate chat Activity and monitoring features are unaffected.
