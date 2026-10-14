"""Pure local scorers; rescoring observations never invokes application tools."""

from math import isfinite, sqrt

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score, log_loss

from app.evaluation.contracts import Case, Metric, Observation


WORKFLOW_INTENTS = {"sentiment_analysis", "keyword_extraction", "faq_retrieval"}


def eligibility(intent: str, confidence: float, threshold: float) -> str:
    """Classifier eligibility only; no extraction, handoff or execution is observed."""
    return "workflow_eligible" if intent in WORKFLOW_INTENTS and confidence >= threshold else "agent_required"


def ratio(numerator: int, denominator: int, note: str) -> Metric:
    interval = None
    value = numerator / denominator if denominator else None
    if denominator:
        # Wilson interval for an observed binary proportion, not a guarantee.
        z = 1.959963984540054
        scale = 1 + z * z / denominator
        centre = (value + z * z / (2 * denominator)) / scale
        margin = z * sqrt(value * (1 - value) / denominator + z * z / (4 * denominator**2)) / scale
        interval = [max(0.0, centre - margin), min(1.0, centre + margin)]
    return Metric(value=value, numerator=numerator, denominator=denominator,
                  interval_95=interval, status="scored" if denominator else "not_scored", note=note)


def score_case(case: Case, actual: Observation, policy_answers: dict[str, str]) -> dict[str, bool | None]:
    if case.suite != "faq_pilot":
        return {"intent_correct": actual.intent == case.expected_intent,
                "eligibility_allowed": case.expected_eligibility == "either"
                or actual.eligibility == case.expected_eligibility}
    matched = case.expected_faq_status == "matched"
    return {"status_correct": actual.faq_status == case.expected_faq_status,
            "policy_correct": actual.policy_id == case.expected_policy_id if matched else None,
            "stored_answer_exact": actual.answer == policy_answers[case.expected_policy_id] if matched else None,
            "answer_sufficiency": None}  # Presenter/semantic evaluation belongs to a later slice.


def classifier_scores(expected, predicted, probabilities, labels, threshold):
    """Measure the fixed holdout, including the historical threshold study."""
    expected, predicted, labels = np.asarray(expected), np.asarray(predicted), np.asarray(labels)
    probabilities = np.asarray(probabilities, dtype=float)
    if (not isfinite(threshold) or not 0 < threshold <= 1
            or len(labels) < 2 or len(set(labels)) != len(labels)
            or len(expected) == 0 or predicted.shape != expected.shape
            or probabilities.shape != (len(expected), len(labels))
            or not np.isfinite(probabilities).all() or (probabilities < 0).any()
            or (probabilities > 1).any() or not np.allclose(probabilities.sum(axis=1), 1)
            or not set(expected).issubset(labels) or not set(predicted).issubset(labels)
            or not np.array_equal(predicted, labels[probabilities.argmax(axis=1)])):
        raise ValueError("Invalid classification observations")
    confidence = probabilities.max(axis=1)
    correct = predicted == expected
    accepted = np.isin(predicted, sorted(WORKFLOW_INTENTS)) & (confidence >= threshold)
    metrics = {
        "classifier.accuracy": ratio(int(correct.sum()), len(expected), "Fixed synthetic holdout; Wilson 95% interval."),
        "classifier.threshold_precision": ratio(int((correct & accepted).sum()), int(accepted.sum()),
                                               "Correct intent among threshold-eligible predictions; not runtime routing."),
        "classifier.threshold_coverage": ratio(int(accepted.sum()), len(expected), "Classifier threshold study only."),
        "classifier.agent_only_false_acceptance": ratio(int((accepted & ~np.isin(expected, sorted(WORKFLOW_INTENTS))).sum()),
                                                       int((~np.isin(expected, sorted(WORKFLOW_INTENTS))).sum()),
                                                       "Agent-only labels incorrectly accepted by the classifier threshold."),
    }
    calibration = pd.DataFrame({"confidence": confidence, "correct": correct})
    calibration["bin"] = pd.cut(confidence, bins=np.linspace(0, 1, 11), include_lowest=True)
    bins = calibration.groupby("bin", observed=True).agg(
        count=("correct", "size"), accuracy=("correct", "mean"), mean_confidence=("confidence", "mean"))
    values = {
        "macro_f1": float(f1_score(expected, predicted, labels=labels, average="macro", zero_division=0)),
        "log_loss": float(log_loss(expected, probabilities, labels=labels)),
        "multiclass_brier_score": float(np.mean(np.sum((probabilities - (expected[:, None] == labels))**2, axis=1))),
        "top_label_ece": float((bins["count"] / len(expected) * (bins.accuracy - bins.mean_confidence).abs()).sum()),
    }
    for name, value in values.items():
        metrics["classifier." + name] = Metric(value=value, status="scored",
            note="Fixed synthetic holdout; Brier sums over classes; ECE uses ten equal-width top-label confidence bins.")
    details = {
        "labels": labels.tolist(),
        "confusion_matrix": confusion_matrix(expected, predicted, labels=labels).tolist(),
        "per_label": classification_report(expected, predicted, labels=labels, output_dict=True, zero_division=0),
        "calibration_bins": [{"bin": str(index), "count": int(row["count"]),
                              "accuracy": float(row["accuracy"]), "mean_confidence": float(row["mean_confidence"])}
                             for index, row in bins.iterrows()],
    }
    return metrics, details


def summarize_cases(results):
    metrics = {"execution.availability": ratio(sum(item.execution == "completed" for item in results), len(results),
                                              "Completed observations / all planned cases, including errors and interruptions.")}
    for suite in ("classifier_holdout", "router_pilot", "faq_pilot"):
        completed = [item for item in results if item.case.suite == suite and item.execution == "completed"]
        keys = sorted({key for item in completed for key in item.checks})
        for key in keys:
            scores = [item.checks[key] for item in completed if item.checks.get(key) is not None]
            metrics[suite + "." + key] = ratio(sum(scores), len(scores),
                "Scored cases only; unavailable and unscored cases remain in the report. Pilot references are provisional.")
    faqs = [item for item in results if item.case.suite == "faq_pilot" and item.execution == "completed"]
    accepted = [item for item in faqs if item.actual.faq_status == "matched"]
    correct = sum(item.case.expected_faq_status == "matched" and item.actual.policy_id == item.case.expected_policy_id
                  for item in accepted)
    metrics["faq.match_precision"] = ratio(correct, len(accepted), "Correct policy acceptance / accepted matches.")
    metrics["faq.match_recall"] = ratio(correct, sum(item.case.expected_faq_status == "matched" for item in faqs),
                                       "Correct policy acceptance / references expecting a match; not information sufficiency.")
    negative = [item for item in faqs if item.case.expected_faq_status != "matched"]
    metrics["faq.wrong_acceptance"] = ratio(sum(item.actual.faq_status == "matched" for item in negative), len(negative),
                                            "Match accepted on an ambiguous or no-match reference.")
    return metrics
