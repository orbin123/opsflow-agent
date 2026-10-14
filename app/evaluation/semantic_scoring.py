"""Pure arithmetic over explicit reviews; never infer semantic labels from prose."""

import hashlib
import json

from app.evaluation.contracts import Metric
from app.evaluation.semantic_contracts import DIMENSIONS


def fingerprint(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def validate_case(item, reference, annotation):
    actual = item.actual
    if (item.case != reference.model_copy(update={"case_id": f"{reference.case_id}-r{item.sample}"})
            or annotation.sample != item.sample or annotation.case_id != reference.case_id
            or set(annotation.dimensions) != set(reference.dimensions)
            or annotation.output_sha256 != actual.output_sha256 or annotation.evidence_sha256 != actual.evidence_sha256
            or actual.output_sha256 != fingerprint(actual.output) or actual.evidence_sha256 != fingerprint(actual.evidence)):
        raise ValueError("Annotation is bound to a different reference, sample, output or source evidence")
    if actual.output is None:
        if (any(r.status != "not_scored" for r in annotation.dimensions.values()) or annotation.claims
                or annotation.facts or annotation.claims_complete or annotation.facts_complete
                or annotation.critical_review_complete):
            raise ValueError("Unavailable application output cannot have semantic scores")
        return
    facts = {fact.fact_id: fact for fact in reference.facts}
    source = reference.source + "\n" + actual.evidence
    if "coverage" in reference.dimensions and annotation.dimensions["coverage"].status == "not_applicable" and facts:
        raise ValueError("Required facts make coverage applicable")
    for claim in annotation.claims:
        if not claim.output_quote.strip() or claim.output_quote not in actual.output or not claim.explanation.strip():
            raise ValueError("Claim requires a literal answer quote and explanation")
        if claim.supported and (not claim.source_quote or not claim.source_quote.strip() or claim.source_quote not in source):
            raise ValueError("Supported claim requires literal source evidence")
        if not claim.supported and claim.source_quote is not None:
            raise ValueError("Unsupported claims use explanation, not invented source evidence")
    if len({claim.output_quote for claim in annotation.claims}) != len(annotation.claims):
        raise ValueError("Duplicate reviewed claim")
    if annotation.facts_complete and {fact.fact_id for fact in annotation.facts} != set(facts):
        raise ValueError("Complete coverage review must address every required fact")
    for fact in annotation.facts:
        if fact.fact_id not in facts or not fact.explanation.strip():
            raise ValueError("Unknown reviewed fact or missing explanation")
        if fact.expressed and (not fact.output_quote or not fact.output_quote.strip() or fact.output_quote not in actual.output):
            raise ValueError("Expressed required fact needs literal answer evidence")
        if not fact.expressed and fact.output_quote is not None:
            raise ValueError("Omitted facts cannot claim answer evidence")
    if (annotation.claims_complete and "faithfulness" in annotation.dimensions
            and annotation.dimensions["faithfulness"].score == 3 and any(not c.supported for c in annotation.claims)):
        raise ValueError("Fully faithful rating conflicts with recorded unsupported claims")
    if (annotation.facts_complete and "coverage" in annotation.dimensions
            and annotation.dimensions["coverage"].score == 3 and any(not f.expressed for f in annotation.facts)):
        raise ValueError("Full coverage rating conflicts with recorded omissions")


def score_cases(cases, review, references):
    if review.references_sha256 != fingerprint(references.model_dump(mode="json")):
        raise ValueError("Changed reference facts or rubric")
    by_reference = {case.case_id: case for case in references.cases}
    annotations = {(a.case_id, a.sample): a for a in review.annotations}
    if len(cases) != len(annotations) or len({(c.annotation.case_id, c.sample) for c in cases}) != len(cases):
        raise ValueError("Missing, extra or duplicate annotation")
    scores = []
    for item in cases:
        annotation = annotations.get((item.annotation.case_id, item.sample))
        reference = by_reference.get(item.annotation.case_id)
        if annotation is None or reference is None or item.annotation != annotation:
            raise ValueError("Unexpected review target")
        validate_case(item, reference, annotation)
        checks = {name + ".fully_meets_rubric": rating.score == 3 if rating.status == "scored" else None
                  for name, rating in annotation.dimensions.items()}
        checks["no_critical_violation"] = not annotation.critical_violations if annotation.critical_review_complete else None
        scores.append(checks)
    return scores


def _ratio(numerator, denominator, note):
    return Metric(value=numerator / denominator if denominator else None,
                  numerator=numerator, denominator=denominator,
                  status="scored" if denominator else "not_scored", note=note)


def summarize(cases):
    metrics, counts = {}, {}
    for dimension in DIMENSIONS:
        ratings = [c.annotation.dimensions[dimension] for c in cases if dimension in c.annotation.dimensions]
        scored = [r.score for r in ratings if r.status == "scored"]
        counts[dimension] = {"planned": len(ratings), "applicable": sum(r.status != "not_applicable" for r in ratings),
                             "scored": len(scored), "not_scored": sum(r.status == "not_scored" for r in ratings),
                             "not_applicable": sum(r.status == "not_applicable" for r in ratings),
                             "scorer_error": sum(r.status == "scorer_error" for r in ratings)}
        metrics["semantic." + dimension] = Metric(value=sum(scored) / len(scored) if scored else None,
                status="scored" if scored else "not_scored",
                note="Mean human 0–3 rubric rating over scored applicable targets only; review counts are separate. No acceptance gate.")
    claims = [claim for c in cases if c.annotation.claims_complete for claim in c.annotation.claims]
    facts = [fact for c in cases if c.annotation.facts_complete for fact in c.annotation.facts]
    metrics["semantic.supported_claims"] = _ratio(sum(c.supported for c in claims), len(claims),
            "Supported / reviewed claims from explicitly complete claim reviews. Zero claims is unscored, not perfect faithfulness.")
    metrics["semantic.required_fact_coverage"] = _ratio(sum(f.expressed for f in facts), len(facts),
            "Supported required facts expressed / required facts in explicitly complete human coverage reviews.")
    metrics["semantic.review_coverage"] = _ratio(sum(c["scored"] for c in counts.values()), sum(c["applicable"] for c in counts.values()),
            "Scored rubric dimensions / planned applicable dimensions; missing output/review and scorer errors remain in denominator.")
    metrics["semantic.output_availability"] = _ratio(sum(c.actual.output is not None for c in cases), len(cases),
            "Available target outputs / planned targets. Saving a review snapshot never executes the application.")
    metrics["semantic.no_critical_violation"] = _ratio(sum(not c.annotation.critical_violations for c in cases if c.annotation.critical_review_complete),
            sum(c.annotation.critical_review_complete for c in cases),
            "Targets without human-recorded critical violations / completed critical reviews. Findings are retained separately and cannot be averaged away.")
    return metrics, counts


def compare_reports(baseline, candidate):
    """Compare matching review targets, keeping missing pairs and version changes explicit."""
    if baseline.schema_version != 3 or candidate.schema_version != 3:
        return {"compatible": False, "reason": "Both reports must be semantic review snapshots."}
    keys = ("references_sha256", "runtime_pilot_sha256", "execution_mode", "annotation_origin", "semantic_implementation_sha256")
    if baseline.scorer_version != candidate.scorer_version or any(
            baseline.provenance.get(k) is None or candidate.provenance.get(k) is None
            or baseline.provenance.get(k) != candidate.provenance.get(k) for k in keys):
        return {"compatible": False, "reason": "Reference/rubric/scorer implementation, runtime dataset, execution mode or annotation origin differs."}
    left = {(c.annotation.case_id, c.sample): c for c in baseline.cases}
    right = {(c.annotation.case_id, c.sample): c for c in candidate.cases}
    if set(left) != set(right):
        return {"compatible": False, "reason": "Selected targets or repeated sample sets differ."}
    rows = []
    for key in sorted(left):
        for name in left[key].case.dimensions:
            before = left[key].annotation.dimensions[name]
            after = right[key].annotation.dimensions[name]
            paired = before.status == after.status == "scored"
            rows.append({"Target": key[0], "Sample": key[1], "Dimension": name,
                         "Baseline status": before.status, "Candidate status": after.status,
                         "Baseline": before.score, "Candidate": after.score,
                         "Delta": after.score - before.score if paired else None})
    changes = {key: {"baseline": baseline.provenance.get(key), "candidate": candidate.provenance.get(key)}
               for key in ("source_commit", "implementation_sha256", "semantic_implementation_sha256", "configured_models", "provider_settings", "source_report_sha256", "review_sha256")
               if baseline.provenance.get(key) != candidate.provenance.get(key)}
    return {"compatible": True, "paired_dimensions": sum(row["Delta"] is not None for row in rows),
            "missing_pairs": sum(row["Delta"] is None for row in rows), "rows": rows, "version_changes": changes,
            "critical_violations": {"baseline": [v for c in baseline.cases for v in c.annotation.critical_violations],
                                    "candidate": [v for c in candidate.cases for v in c.annotation.critical_violations]},
            "note": "Paired descriptive ratings only; no universal winner or overall acceptance gate. Missing pairs are not zero. Reviewers may differ."}
