"""Versioned synthetic reference cases and saved baseline reports."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator


Intent = Literal["compound_request", "email_drafting", "faq_retrieval", "keyword_extraction",
                 "out_of_scope", "reminder_creation", "sentiment_analysis", "summarization"]
Eligibility = Literal["workflow_eligible", "agent_required"]
FAQStatus = Literal["matched", "ambiguous", "no_match"]
Text = Annotated[str, StringConstraints(min_length=1, max_length=10000)]
Count = Annotated[int, Field(ge=0)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Case(Record):
    case_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,64}$")]
    suite: Literal["classifier_holdout", "router_pilot", "faq_pilot"]
    input: Text
    reference_note: Text
    expected_intent: Intent | None = None
    expected_eligibility: Literal["workflow_eligible", "agent_required", "either"] | None = None
    expected_faq_status: FAQStatus | None = None
    expected_policy_id: str | None = None
    source_sufficiency: Literal["sufficient", "missing_detail", "not_applicable"] | None = None

    @model_validator(mode="after")
    def coherent_reference(self):
        if not self.input.strip() or not self.reference_note.strip():
            raise ValueError("Case text and reference note must be nonblank")
        if self.suite == "faq_pilot":
            if (self.expected_faq_status is None or self.source_sufficiency is None
                    or self.expected_intent is not None or self.expected_eligibility is not None):
                raise ValueError("FAQ case requires only FAQ references")
            matched = self.expected_faq_status == "matched"
            if matched != bool(self.expected_policy_id):
                raise ValueError("Only matched references have a policy ID")
            if matched == (self.source_sufficiency == "not_applicable"):
                raise ValueError("Only matched references assess source sufficiency")
        elif (self.expected_intent is None or self.expected_eligibility is None
              or self.expected_faq_status is not None or self.expected_policy_id is not None
              or self.source_sufficiency is not None):
            raise ValueError("Router case requires only intent and eligibility references")
        return self


class Pilot(Record):
    schema_version: Literal[1]
    name: Text
    reference_status: Literal["ai_authored_pending_human_review", "human_reviewed"]
    faq_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    cases: Annotated[list[Case], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_pilot_cases(self):
        if (len({case.case_id for case in self.cases}) != len(self.cases)
                or any(case.suite == "classifier_holdout" for case in self.cases)):
            raise ValueError("Pilot requires unique development cases")
        return self


class Observation(Record):
    intent: Intent | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    eligibility: Eligibility | None = None
    faq_status: FAQStatus | None = None
    policy_id: str | None = None
    answer: str | None = None
    candidates: list[dict[str, JsonValue]] = Field(default_factory=list)


class CaseResult(Record):
    case: Case
    execution: Literal["not_run", "completed", "failed"] = "not_run"
    actual: Observation | None = None
    checks: dict[str, bool | None] = Field(default_factory=dict)
    failure_code: Literal["execution_failed"] | None = None

    @model_validator(mode="after")
    def consistent_outcome(self):
        if self.execution == "completed":
            if self.actual is None or not self.checks or self.failure_code is not None:
                raise ValueError("Completed case requires observations and scores")
            if self.case.suite == "faq_pilot":
                if (self.actual.faq_status is None or self.actual.intent is not None
                        or self.actual.confidence is not None or self.actual.eligibility is not None):
                    raise ValueError("FAQ observation requires only retrieval fields")
                if self.actual.faq_status == "matched":
                    if not self.actual.policy_id or not self.actual.answer:
                        raise ValueError("Matched observation requires policy and answer")
                elif self.actual.policy_id is not None or self.actual.answer is not None:
                    raise ValueError("Unmatched observation must not claim an answer")
            elif (self.actual.intent is None or self.actual.confidence is None or self.actual.eligibility is None
                  or self.actual.faq_status is not None or self.actual.policy_id is not None
                  or self.actual.answer is not None or self.actual.candidates):
                raise ValueError("Router observation requires only classification fields")
        elif self.actual is not None or self.checks:
            raise ValueError("Uncompleted case must not claim observations or scores")
        if (self.execution == "failed") != (self.failure_code is not None):
            raise ValueError("Failed case requires a failure code")
        return self


class Metric(Record):
    value: Annotated[float, Field(ge=0)] | None
    numerator: Count | None = None
    denominator: Count | None = None
    interval_95: list[float] | None = None
    status: Literal["scored", "not_scored"]
    note: str

    @model_validator(mode="after")
    def consistent_metric(self):
        if (self.status == "scored") != (self.value is not None):
            raise ValueError("Unscored metric must not have a value")
        if (self.numerator is None) != (self.denominator is None):
            raise ValueError("Ratio metric requires both counts")
        if self.denominator is not None:
            if self.numerator > self.denominator:
                raise ValueError("Invalid metric counts")
            expected = self.numerator / self.denominator if self.denominator else None
            if self.value != expected:
                raise ValueError("Metric value must agree with counts")
        if self.interval_95 is not None:
            if (len(self.interval_95) != 2 or not 0 <= self.interval_95[0] <= self.interval_95[1] <= 1
                    or not self.denominator):
                raise ValueError("Invalid confidence interval")
        return self


class Report(Record):
    schema_version: Literal[1] = 1
    scorer_version: Literal["local-baseline-v1"] = "local-baseline-v1"
    run_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
    started_at: str
    finished_at: str | None = None
    state: Literal["running", "completed", "failed", "interrupted"] = "running"
    quality_verdict: Literal["not_scored", "passed", "has_failures"] = "not_scored"
    failure_code: Literal["case_execution_failed", "evaluation_failed", "interrupted"] | None = None
    provenance: dict[str, JsonValue]
    cases: list[CaseResult]
    metrics: dict[str, Metric] = Field(default_factory=dict)
    classifier_details: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str]

    @model_validator(mode="after")
    def consistent_report(self):
        if len({item.case.case_id for item in self.cases}) != len(self.cases):
            raise ValueError("Duplicate report case ID")
        if (self.state == "running") != (self.finished_at is None):
            raise ValueError("Only running reports have no finish time")
        if (self.state in {"failed", "interrupted"}) != (self.failure_code is not None):
            raise ValueError("Failed or interrupted run requires a failure code")
        if self.state == "completed" and any(item.execution != "completed" for item in self.cases):
            raise ValueError("Completed run requires all cases executed")
        checks = [check for item in self.cases for check in item.checks.values() if check is not None]
        verdict = "has_failures" if False in checks else "passed" if checks else "not_scored"
        if self.quality_verdict != verdict:
            raise ValueError("Quality verdict must agree with case checks")
        return self
