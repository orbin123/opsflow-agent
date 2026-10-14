"""Saved human review contracts. No provider, tool or execution imports."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.evaluation.contracts import Record, Report, Text

ID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,64}$")]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
DIMENSIONS = ("faithfulness", "coverage", "relevance", "instruction_compliance", "status_accuracy", "context_relevance")
Dimension = Literal["faithfulness", "coverage", "relevance", "instruction_compliance", "status_accuracy", "context_relevance"]


class Fact(Record):
    fact_id: ID
    statement: Text
    source_quote: Text

    @model_validator(mode="after")
    def nonblank(self):
        if not self.statement.strip() or not self.source_quote.strip():
            raise ValueError("Nonblank fact and source quote required")
        return self


class SemanticReference(Record):
    case_id: ID
    suite: Literal["generated_answer"] = "generated_answer"
    input: Text
    reference_note: Text
    runtime_case_id: ID
    turn: Annotated[int, Field(ge=1, le=2)] = 1
    target: Literal["reply", "summarize_text", "draft_email"] = "reply"
    occurrence: Annotated[int, Field(ge=1, le=5)] = 1
    source: Text
    facts: list[Fact]
    instructions: Text
    dimensions: Annotated[list[Dimension], Field(min_length=1)]

    @model_validator(mode="after")
    def coherent(self):
        if (len({fact.fact_id for fact in self.facts}) != len(self.facts)
                or len(set(self.dimensions)) != len(self.dimensions)
                or any(fact.source_quote not in self.source for fact in self.facts)):
            raise ValueError("Unique facts/dimensions and literal source quotes required")
        if self.target == "reply" and self.occurrence != 1:
            raise ValueError("Reply has only one occurrence")
        if not all(text.strip() for text in (self.input, self.reference_note, self.source, self.instructions)):
            raise ValueError("Nonblank semantic references required")
        return self


class SemanticReferences(Record):
    schema_version: Literal[1] = 1
    name: Text
    reference_status: Literal["ai_authored_pending_human_review"] = "ai_authored_pending_human_review"
    provenance_note: Text
    runtime_pilot_sha256: Hash
    faq_sha256: Hash
    rubric_version: Literal["semantic-human-v1"] = "semantic-human-v1"
    rubric: dict[Dimension, dict[str, str]]
    cases: Annotated[list[SemanticReference], Field(min_length=1)]

    @model_validator(mode="after")
    def coherent(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate semantic reference")
        if set(self.rubric) != set(DIMENSIONS) or any(set(scale) != {"0", "1", "2", "3"} for scale in self.rubric.values()):
            raise ValueError("All dimensions require a versioned 0–3 rubric")
        return self


class Rating(Record):
    status: Literal["scored", "not_scored", "not_applicable", "scorer_error"] = "not_scored"
    score: Annotated[int, Field(ge=0, le=3)] | None = None
    explanation: Text = "Awaiting human review."

    @model_validator(mode="after")
    def coherent(self):
        if (self.status == "scored") != (self.score is not None) or not self.explanation.strip():
            raise ValueError("Only scored dimensions have a score; every status requires an explanation")
        return self


class ClaimReview(Record):
    output_quote: Text
    supported: bool
    source_quote: Text | None = None
    explanation: Text


class FactReview(Record):
    fact_id: ID
    expressed: bool
    output_quote: Text | None = None
    explanation: Text


class Annotation(Record):
    case_id: ID
    sample: Annotated[int, Field(ge=1, le=3)]
    output_sha256: Hash
    evidence_sha256: Hash
    reviewer: Text | None = None
    reviewed_at: str | None = None
    reference_reviewed: bool = False
    dimensions: dict[Dimension, Rating]
    claims_complete: bool = False
    claims: list[ClaimReview] = Field(default_factory=list)
    facts_complete: bool = False
    facts: list[FactReview] = Field(default_factory=list)
    critical_review_complete: bool = False
    critical_violations: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def coherent(self):
        from datetime import datetime
        reviewed = (any(r.status != "not_scored" for r in self.dimensions.values())
                    or self.claims or self.facts or self.claims_complete or self.facts_complete
                    or self.critical_review_complete or self.critical_violations or self.reference_reviewed)
        if reviewed and (not self.reviewer or not self.reviewer.strip() or not self.reviewed_at or not self.reference_reviewed):
            raise ValueError("Review requires reviewer, timestamp and explicit reference review")
        if self.reviewed_at and datetime.fromisoformat(self.reviewed_at).tzinfo is None:
            raise ValueError("Review timestamp requires timezone")
        if self.critical_violations and not self.critical_review_complete:
            raise ValueError("Critical findings require a completed critical review")
        if any(not finding.strip() for finding in self.critical_violations):
            raise ValueError("Critical findings must explain the violation")
        if len({f.fact_id for f in self.facts}) != len(self.facts):
            raise ValueError("Duplicate reviewed fact")
        return self


class AnnotationFile(Record):
    schema_version: Literal[1] = 1
    origin: Literal["human", "synthetic_test"] = "human"
    report_sha256: Hash
    references_sha256: Hash
    rubric_version: Literal["semantic-human-v1"] = "semantic-human-v1"
    annotations: list[Annotation]

    @model_validator(mode="after")
    def unique(self):
        if len({(a.case_id, a.sample) for a in self.annotations}) != len(self.annotations):
            raise ValueError("Duplicate answer annotation")
        return self


class SemanticObservation(Record):
    output: str | None
    evidence: Text
    output_sha256: Hash
    evidence_sha256: Hash
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if (self.output is None) != (self.unavailable_reason is not None):
            raise ValueError("Unavailable output requires a reason")
        return self


class SemanticCaseResult(Record):
    case: SemanticReference
    sample: Annotated[int, Field(ge=1, le=3)]
    execution: Literal["completed"] = "completed"
    actual: SemanticObservation
    annotation: Annotation
    checks: dict[str, bool | None]
    failure_code: None = None


class SemanticReport(Report):
    schema_version: Literal[3] = 3
    scorer_version: Literal["semantic-human-v1"] = "semantic-human-v1"
    cases: list[SemanticCaseResult]
    references: SemanticReferences
    review: AnnotationFile
    review_counts: dict[str, dict[str, int]]

    @model_validator(mode="after")
    def coherent_semantics(self):
        from app.evaluation.semantic_scoring import fingerprint, validate_case
        if self.state != "completed" or self.failure_code or self.classifier_details:
            raise ValueError("Semantic snapshot is a completed review operation, not application execution")
        if self.scorer_version != self.references.rubric_version or self.review.rubric_version != self.scorer_version:
            raise ValueError("Incompatible semantic rubric")
        references = {r.case_id: r for r in self.references.cases}
        annotations = {(a.case_id, a.sample): a for a in self.review.annotations}
        if (self.review.references_sha256 != fingerprint(self.references.model_dump(mode="json"))
                or self.provenance.get("source_report_sha256") != self.review.report_sha256
                or self.provenance.get("review_sha256") != fingerprint(self.review.model_dump(mode="json"))
                or self.provenance.get("references_sha256") != self.review.references_sha256
                or self.provenance.get("annotation_origin") != self.review.origin
                or len(self.cases) != len(annotations)):
            raise ValueError("Saved review identity mismatch")
        for item in self.cases:
            reference = references.get(item.annotation.case_id)
            if reference is None or item.annotation != annotations.get((item.annotation.case_id, item.sample)):
                raise ValueError("Unexpected saved review target")
            validate_case(item, reference, item.annotation)
            expected = {name + ".fully_meets_rubric": r.score == 3 if r.status == "scored" else None
                        for name, r in item.annotation.dimensions.items()}
            expected["no_critical_violation"] = not item.annotation.critical_violations if item.annotation.critical_review_complete else None
            if item.checks != expected:
                raise ValueError("Saved checks disagree with annotations")
        # Validate saved aggregate arithmetic without invoking the scoring entry points.
        for dimension in DIMENSIONS:
            ratings = [c.annotation.dimensions[dimension] for c in self.cases if dimension in c.annotation.dimensions]
            scores = [r.score for r in ratings if r.status == "scored"]
            counts = self.review_counts.get(dimension)
            if (counts != {"planned": len(ratings), "applicable": sum(r.status != "not_applicable" for r in ratings),
                           "scored": len(scores), "not_scored": sum(r.status == "not_scored" for r in ratings),
                           "not_applicable": sum(r.status == "not_applicable" for r in ratings),
                           "scorer_error": sum(r.status == "scorer_error" for r in ratings)}
                    or self.metrics.get("semantic." + dimension) is None
                    or self.metrics["semantic." + dimension].value != (sum(scores) / len(scores) if scores else None)):
                raise ValueError("Saved rubric aggregate disagrees with annotations")
        claims = [claim for c in self.cases if c.annotation.claims_complete for claim in c.annotation.claims]
        facts = [fact for c in self.cases if c.annotation.facts_complete for fact in c.annotation.facts]
        ratios = {"supported_claims": (sum(c.supported for c in claims), len(claims)),
                  "required_fact_coverage": (sum(f.expressed for f in facts), len(facts)),
                  "review_coverage": (sum(c["scored"] for c in self.review_counts.values()), sum(c["applicable"] for c in self.review_counts.values())),
                  "output_availability": (sum(c.actual.output is not None for c in self.cases), len(self.cases)),
                  "no_critical_violation": (sum(not c.annotation.critical_violations for c in self.cases if c.annotation.critical_review_complete),
                                            sum(c.annotation.critical_review_complete for c in self.cases))}
        if (set(self.review_counts) != set(DIMENSIONS)
                or set(self.metrics) != {"semantic." + name for name in (*DIMENSIONS, *ratios)}):
            raise ValueError("Unexpected saved metric set")
        for name, counts in ratios.items():
            metric = self.metrics["semantic." + name]
            if (metric.numerator, metric.denominator) != counts:
                raise ValueError("Saved metric denominators disagree with annotations")
        return self
