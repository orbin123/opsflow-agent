"""Explicit offline preparation/scoring of saved outputs; no runtime imports."""

import argparse
import hashlib
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from app.evaluation.catalogue import report_directory
from app.evaluation.reports import ReportWriter, load_report
from app.evaluation.semantic_contracts import (Annotation, AnnotationFile, Rating, SemanticCaseResult,
        SemanticObservation, SemanticReferences, SemanticReport)
from app.evaluation.semantic_scoring import fingerprint, score_cases, summarize

REFERENCES = Path(__file__).resolve().parents[2] / "data/evaluation/semantic_references.json"


def collect_targets(runtime, references):
    if runtime.schema_version != 2 or runtime.provenance.get("pilot_sha256") != references.runtime_pilot_sha256:
        raise ValueError("Semantic review requires the referenced runtime dataset")
    if runtime.provenance.get("faq_sha256") != references.faq_sha256:
        raise ValueError("Changed FAQ source")
    samples = sorted({item.sample for item in runtime.cases})
    if not samples:
        raise ValueError("Runtime report must retain planned samples")
    targets = []
    for reference in references.cases:
        for sample in samples:
            item = next((c for c in runtime.cases if c.reference_case_id == reference.runtime_case_id and c.sample == sample), None)
            output, reason = None, "Runtime case not collected or target output unavailable."
            # Source evidence excludes the evaluated answer and model request records.
            evidence = {"reference_source": reference.source, "input": reference.input, "turns": [], "reminders": []}
            if item is not None:
                evidence["planned_inputs"] = [turn.input for turn in item.case.turns[:reference.turn]]
            if item is not None and item.actual is not None:
                evidence["reminders"] = item.actual.reminder_records
                for number, turn in enumerate(item.actual.turns[:reference.turn], 1):
                    execution = turn.execution or {}
                    trace = execution.get("trace", [])
                    evidence["turns"].append({"input": turn.input, "status": turn.status, "tools": trace})
                    if number == reference.turn:
                        if reference.target == "reply":
                            output = execution.get("reply") or None
                        else:
                            calls = [call for call in trace if call["tool"] == reference.target]
                            if len(calls) >= reference.occurrence and calls[reference.occurrence - 1].get("result") is not None:
                                output = json.dumps(calls[reference.occurrence - 1]["result"], ensure_ascii=False, indent=2)
                        # Generated outputs cannot serve as their own grounding evidence.
                evidence["turns"] = [{**turn, "tools": [{k: v for k, v in step.items()
                        if k != "result" or step["tool"] not in {"summarize_text", "draft_email"}}
                        for step in turn["tools"]]} for turn in evidence["turns"]]
            evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2)
            observation = SemanticObservation(output=output, evidence=evidence_text, output_sha256=fingerprint(output),
                    evidence_sha256=fingerprint(evidence_text), unavailable_reason=reason if output is None else None)
            annotation = Annotation(case_id=reference.case_id, sample=sample,
                    output_sha256=observation.output_sha256, evidence_sha256=observation.evidence_sha256,
                    dimensions={name: Rating() for name in reference.dimensions})
            targets.append(SemanticCaseResult(case=reference.model_copy(update={"case_id": f"{reference.case_id}-r{sample}"}),
                    sample=sample, actual=observation, annotation=annotation, checks={}))
    return targets


def prepare_review(runtime, references):
    cases = collect_targets(runtime, references)
    return AnnotationFile(report_sha256=fingerprint(runtime.model_dump(mode="json")),
            references_sha256=fingerprint(references.model_dump(mode="json")), annotations=[c.annotation for c in cases])


def make_snapshot(runtime, references, review):
    if review.report_sha256 != fingerprint(runtime.model_dump(mode="json")):
        raise ValueError("Annotations belong to a different saved runtime report")
    cases = collect_targets(runtime, references)
    annotations = {(a.case_id, a.sample): a for a in review.annotations}
    for case in cases:
        annotation = annotations.get((case.annotation.case_id, case.sample))
        if annotation is None:
            raise ValueError("Missing annotation target; retain explicit unscored entries")
        case.annotation = annotation
    checks = score_cases(cases, review, references)
    for case, scores in zip(cases, checks):
        case.checks = scores
    metrics, counts = summarize(cases)
    checked = [value for case in cases for value in case.checks.values() if value is not None]
    now = datetime.now(UTC).isoformat()
    provenance = {**runtime.provenance, "source_report_id": runtime.run_id,
            "source_report_started_at": runtime.started_at, "source_report_finished_at": runtime.finished_at,
            "source_report_sha256": review.report_sha256, "references_sha256": review.references_sha256,
            "runtime_pilot_sha256": references.runtime_pilot_sha256, "review_sha256": fingerprint(review.model_dump(mode="json")),
            "annotation_origin": review.origin, "semantic_operation": "offline_saved_review",
            "judge_model": "not_invoked", "reference_status": "per_target_explicit_human_review_required",
            "source_reference_status": runtime.provenance.get("reference_status")}
    provenance["semantic_implementation_sha256"] = hashlib.sha256(b"".join(
            Path(__file__).with_name(name).read_bytes() for name in
            ("semantic_contracts.py", "semantic_scoring.py", "semantic_review.py"))).hexdigest()
    return SemanticReport(run_id=uuid4().hex, started_at=now, finished_at=now, state="completed",
            quality_verdict="has_failures" if False in checked else "passed" if checked else "not_scored",
            provenance=provenance, cases=cases, metrics=metrics, references=references, review=review, review_counts=counts,
            limitations=["Offline human review of saved synthetic outputs; no application/model/tool execution.",
                "0–3 ratings are descriptive rubric assessments, not an agreed acceptance threshold or Ragas implementation.",
                "Human origin and reference review are reviewer attestations; software cannot establish reviewer identity or semantic correctness.",
                "Synthetic test annotations are harness evidence only; missing human annotations stay unscored.",
                "Critical findings stay explicit and force has_failures, regardless of other ratings.",
                "References were authored after scripted runtime collection; these are development review material, not an independent holdout.",
                "Live quality/stability, a validated model judge and judge/human agreement remain unverified."])


def main():
    parser = argparse.ArgumentParser(description="Review saved runtime answers offline; never rerun models/tools.")
    parser.add_argument("--report", type=Path, required=True, help="Saved schema-v2 runtime report.")
    parser.add_argument("--references", type=Path, default=REFERENCES)
    parser.add_argument("--template", type=Path, help="Write a new annotation template (exclusive creation).")
    parser.add_argument("--annotations", type=Path, help="Explicitly supplied completed/partial human annotations.")
    parser.add_argument("--report-dir", type=Path, default=report_directory())
    args = parser.parse_args()
    try:
        if args.template and args.annotations:
            raise ValueError("Choose template preparation or supplied annotations")
        runtime = load_report(args.report)
        references = SemanticReferences.model_validate_json(args.references.read_text())
        review = (AnnotationFile.model_validate_json(args.annotations.read_text()) if args.annotations
                  else prepare_review(runtime, references))
        if review.origin != "human":
            raise ValueError("CLI accepts human attestations only; synthetic tests cannot become human evidence")
        report = make_snapshot(runtime, references, review)
        if args.template:
            with args.template.open("x", encoding="utf-8") as handle:
                handle.write(review.model_dump_json(indent=2) + "\n")
        writer = ReportWriter(args.report_dir, report.run_id)
        writer.save(report)
    except (OSError, ValueError):
        print("Review could not be validated or saved. Check report, reference/answer fingerprints, annotations and output paths.")
        return 1
    print(f"Review report: {writer.path.resolve()}")
    print(f"Quality: {report.quality_verdict}; human scores remain missing until explicitly supplied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
