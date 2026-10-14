"""Explicit offline classifier/FAQ execution, separate from pure scoring."""

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import uuid

import pandas as pd
from sklearn.model_selection import train_test_split

from app.core import intent_router
from app.core.intent_router import load_router
from app.evaluation.contracts import Case, CaseResult, Observation, Pilot, Report
from app.evaluation.reports import ReportWriter
from app.evaluation.scoring import classifier_scores, eligibility, score_case, summarize_cases
from app.tools import faq
from app.tools.faq import retrieve_faq


ROOT = Path(__file__).resolve().parents[2]
LIMITATIONS = [
    "Classifier results reuse the original synthetic holdout; no retraining or threshold tuning.",
    "Pilot cases are development data authored by AI, pending human reference review.",
    "Eligibility measures the classifier threshold, not workflow extraction, agent handoff or runtime execution.",
    "FAQ retrieval and exact stored-answer checks do not establish policy applicability or generated-answer quality.",
    "No live LLM, agent, reminder, SMTP, worker, chat persistence or UI evaluation is performed.",
    "Running snapshots after a forced process stop are incomplete; reading them never resumes work.",
]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_cases(pilot_path: Path):
    pilot = Pilot.model_validate_json(pilot_path.read_text(encoding="utf-8"))
    faq_path = ROOT / "data/company_faq.json"
    if _hash(faq_path) != pilot.faq_sha256:
        raise ValueError("Pilot FAQ fingerprint mismatch")
    answers = {item["policy_id"]: item["answer"] for item in json.loads(faq_path.read_text())["faqs"]}
    indexed = {text.casefold().strip() for item in json.loads(faq_path.read_text())["faqs"]
               for text in [item["question"], *item["alternate_phrasings"]]}
    if any(case.expected_policy_id is not None and case.expected_policy_id not in answers for case in pilot.cases):
        raise ValueError("Unknown reference policy ID")
    if any(case.suite == "faq_pilot" and case.input.casefold().strip() in indexed for case in pilot.cases):
        raise ValueError("Pilot must not duplicate an indexed FAQ question")
    metadata = json.loads((ROOT / "artifacts/models/intent_router_svm_metadata.json").read_text())
    dataset_path = ROOT / "data/tasks_benchmark.csv"
    if _hash(dataset_path) != metadata["dataset"]["sha256"]:
        raise ValueError("Classifier dataset fingerprint mismatch")
    data = pd.read_csv(dataset_path).reset_index(names="row_id")
    if list(data.columns) != ["row_id", "text", "label"] or len(data) != metadata["dataset"]["row_count"]:
        raise ValueError("Classifier dataset structure mismatch")
    _, heldout = train_test_split(data, test_size=0.2, random_state=metadata["split"]["random_state"], stratify=data.label)
    if len(heldout) != metadata["split"]["test_rows"]:
        raise ValueError("Classifier holdout size mismatch")
    if _hash(ROOT / "artifacts/models/intent_router_svm.joblib") != metadata["model_sha256"]:
        raise ValueError("Classifier model fingerprint mismatch")
    cases = [Case(case_id=f"holdout-{row.row_id:04d}", suite="classifier_holdout", input=row.text,
                  reference_note="Original synthetic classifier holdout label; historical comparison only.",
                  expected_intent=row.label, expected_eligibility="either") for row in heldout.itertuples()]
    return cases + pilot.cases, metadata, pilot, answers


def _provenance(pilot_path, metadata, pilot):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    working_tree = git("status", "--porcelain")
    return {
        "source_commit": git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(working_tree) if working_tree is not None else None,
        "classifier_dataset_sha256": metadata["dataset"]["sha256"],
        "classifier_model_sha256": _hash(ROOT / "artifacts/models/intent_router_svm.joblib"),
        "pilot_sha256": _hash(pilot_path), "pilot_name": pilot.name, "reference_status": pilot.reference_status,
        "faq_sha256": pilot.faq_sha256, "threshold": metadata["routing_threshold"]["selected"],
        "implementation_sha256": hashlib.sha256(b"".join(
            path.read_bytes() for path in sorted((ROOT / "app/evaluation").glob("*.py")))
            + (ROOT / "app/tools/faq.py").read_bytes() + (ROOT / "app/core/intent_router.py").read_bytes()).hexdigest(),
        "python_version": platform.python_version(),
        "split": metadata["split"], "versions": {name: version(name) for name in ("scikit-learn", "pandas", "joblib", "pydantic")},
        "runtime_model": "not_invoked", "judge_model": "not_invoked",
    }


def run_baseline(report_root: Path, *, pilot_path: Path | None = None) -> Path:
    pilot_path = pilot_path or ROOT / "data/evaluation/local_pilot.json"
    cases, metadata, pilot, answers = load_cases(pilot_path)
    report = Report(run_id=uuid.uuid4().hex, started_at=_now(), provenance=_provenance(pilot_path, metadata, pilot),
                    cases=[CaseResult(case=case) for case in cases], limitations=LIMITATIONS)
    writer = ReportWriter(report_root, report.run_id)
    writer.save(report)
    probabilities, predictions = [], []
    try:
        # Every explicit run observes the fingerprinted files, not a prior run's caches.
        intent_router.load_router.cache_clear()
        faq._load_index.cache_clear()
        model, threshold = load_router()  # Trusted artifact, fingerprint verified before deserialization.
        for index, case in enumerate(cases):
            try:
                if case.suite == "faq_pilot":
                    result = asdict(retrieve_faq(case.input))
                    actual = Observation(faq_status=result["status"], policy_id=result["policy_id"],
                                         answer=result["answer"], candidates=list(result["candidates"]))
                else:
                    probs = model.predict_proba([case.input])[0]
                    intent = str(model.classes_[probs.argmax()])
                    confidence = float(probs.max())
                    actual = Observation(intent=intent, confidence=confidence, eligibility=eligibility(intent, confidence, threshold))
                    if case.suite == "classifier_holdout":
                        probabilities.append(probs)
                        predictions.append(intent)
                report.cases[index] = CaseResult(case=case, execution="completed", actual=actual,
                                                checks=score_case(case, actual, answers))
            except Exception:
                report.cases[index] = CaseResult(case=case, execution="failed", failure_code="execution_failed")
        holdout = [item for item in report.cases if item.case.suite == "classifier_holdout"]
        if all(item.execution == "completed" for item in holdout):
            report.metrics, report.classifier_details = classifier_scores(
                [item.case.expected_intent for item in holdout], predictions, probabilities, model.classes_, threshold)
        report.state = "failed" if any(item.execution != "completed" for item in report.cases) else "completed"
        if report.state == "failed":
            report.failure_code = "case_execution_failed"
    except KeyboardInterrupt:
        report.state = "interrupted"
        report.failure_code = "interrupted"
    except Exception:
        report.state = "failed"
        report.failure_code = "evaluation_failed"
    report.metrics.update(summarize_cases(report.cases))
    checks = [value for item in report.cases for value in item.checks.values() if value is not None]
    report.quality_verdict = "has_failures" if False in checks else "passed" if checks else "not_scored"
    report.finished_at = _now()
    writer.save(report)
    return writer.path
