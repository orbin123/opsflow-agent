"""Schema-v2 observable runtime references; no application/provider imports."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from app.evaluation.contracts import Count, Record, Report, Text

Tool = Literal["analyze_sentiment", "extract_keywords", "retrieve_faq", "summarize_text", "draft_email", "schedule_reminder"]
Route = Literal["agent", "llm_assisted", "direct"]
Status = Literal["completed", "needs_clarification", "agent_required", "partial_failure", "error", "interrupted"]
ID = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,64}$")]


class ExpectedCall(Record):
    call_id: ID
    tool: Tool
    arguments: dict[str, JsonValue]
    status: Literal["completed", "failed"] = "completed"
    result_fields: dict[str, JsonValue] = Field(default_factory=dict)
    # A reference to an earlier call's result, never executable code.
    dependency_call: ID | None = None
    dependency_argument: Literal["text", "content"] | None = None
    dependency_result_field: str | None = None

    @model_validator(mode="after")
    def complete_dependency(self):
        fields = {"retrieve_faq": ["question"], "draft_email": ["recipient", "content"],
                  "schedule_reminder": ["task", "date", "time"]}.get(self.tool, ["text"])
        for field in fields:
            value = self.arguments.get(field)
            if field != self.dependency_argument and (not isinstance(value, str) or not value.strip()):
                raise ValueError("Reference call requires literal nonblank argument fields")
        if any((self.dependency_call, self.dependency_argument, self.dependency_result_field)) and not all(
                (self.dependency_call, self.dependency_argument, self.dependency_result_field)):
            raise ValueError("Dependency requires call, argument and result field")
        if self.dependency_argument in self.arguments:
            raise ValueError("Dependency argument cannot also have a literal reference")
        return self


class RuntimeReferenceTurn(Record):
    input: Text
    allowed_routes: list[Route]
    expected_statuses: Annotated[list[Status], Field(min_length=1)]
    calls: Annotated[list[ExpectedCall], Field(max_length=5)] = Field(default_factory=list)
    independent_order: bool = False
    forbidden_tools: list[Tool] = Field(default_factory=lambda: ["schedule_reminder"])
    transport: Literal["python", "http", "sse"] = "python"
    expected_http_status: Literal[200, 503] | None = None
    expected_outcome_http_status: Literal[200, 503] | None = None

    @model_validator(mode="after")
    def coherent_turn(self):
        if not self.input.strip() or len({call.call_id for call in self.calls}) != len(self.calls):
            raise ValueError("Nonblank input and unique reference calls required")
        prior = set()
        for call in self.calls:
            if call.tool in self.forbidden_tools:
                raise ValueError("Required tool is forbidden")
            if call.dependency_call and (call.dependency_call not in prior or self.independent_order):
                raise ValueError("Dependencies require an earlier ordered reference call")
            prior.add(call.call_id)
        if self.expected_outcome_http_status is not None and self.transport != "sse":
            raise ValueError("Only SSE separates terminal and transport HTTP status")
        if (self.transport == "python") != (self.expected_http_status is None):
            raise ValueError("Only HTTP/SSE references declare transport status")
        return self


class ExpectedReminder(Record):
    task: Text
    due_at: str
    timezone: str
    state: Literal["pending"] = "pending"

    @model_validator(mode="after")
    def aware_due(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        if datetime.fromisoformat(self.due_at).tzinfo is None:
            raise ValueError("Reminder reference requires an instant")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError):
            raise ValueError("Unknown reminder reference timezone") from None
        return self


class RuntimeCase(Record):
    case_id: ID
    suite: Literal["workflow_extraction", "agent_trajectory", "reminder_recovery"]
    reference_note: Text
    entry_point: Literal["chat", "sentiment_workflow", "keyword_workflow", "faq_workflow"]
    turns: Annotated[list[RuntimeReferenceTurn], Field(min_length=1, max_length=2)]
    frozen_now: str = "2026-10-14T06:00:00+00:00"
    expected_reminders: Annotated[list[ExpectedReminder], Field(max_length=2)] = Field(default_factory=list)
    recovery: Literal["none", "replay", "interrupted"] = "none"
    fault: Literal["none", "provider_after_schedule", "summary_provider_failure"] = "none"

    @property
    def input(self):
        return self.turns[0].input

    @model_validator(mode="after")
    def coherent_case(self):
        from datetime import datetime
        if datetime.fromisoformat(self.frozen_now).tzinfo is None:
            raise ValueError("Frozen clock must include a timezone")
        if (self.suite == "workflow_extraction") != (self.entry_point != "chat"):
            raise ValueError("Suite must identify standalone workflow or chat execution")
        if self.entry_point == "chat" and self.recovery != "interrupted" and any(not turn.allowed_routes for turn in self.turns):
            raise ValueError("Executed chat references require allowed runtime routes")
        if self.entry_point != "chat" and (len(self.turns) != 1 or self.recovery != "none"
                or any(turn.transport != "python" for turn in self.turns)):
            raise ValueError("Standalone workflow requires one Python turn and no recovery")
        if self.recovery == "interrupted" and (len(self.turns) != 1 or self.expected_reminders
                or self.turns[0].calls or self.turns[0].expected_statuses != ["interrupted"]):
            raise ValueError("Interrupted recovery must not expect execution")
        return self


class RuntimePilot(Record):
    schema_version: Literal[2] = 2
    name: Text
    reference_status: Literal["ai_authored_pending_human_review", "human_reviewed"]
    faq_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    cases: Annotated[list[RuntimeCase], Field(min_length=1, max_length=24)]

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate scenario ID")
        return self


class RuntimeTurn(Record):
    input: Text
    status: Status
    execution: dict[str, JsonValue] | None
    events: list[dict[str, JsonValue]] = Field(default_factory=list)
    http_status: int | None = None
    outcome_http_status: int | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def coherent_execution(self):
        if self.execution is not None:
            execution = self.execution
            if (execution.get("status") != self.status or execution.get("route") not in {"agent", "llm_assisted", "direct", None}
                    or not isinstance(execution.get("trace"), list)
                    or not isinstance(execution.get("workflow_trace"), list)):
                raise ValueError("Invalid runtime execution snapshot")
            if execution.get("route") is None and execution.get("entry_point") not in {"sentiment_workflow", "keyword_workflow", "faq_workflow"}:
                raise ValueError("Only standalone workflows omit a runtime route")
            for step in execution["trace"]:
                if (not isinstance(step, dict) or step.get("tool") not in Tool.__args__
                        or step.get("status") not in {"completed", "failed"}
                        or not isinstance(step.get("arguments"), dict)):
                    raise ValueError("Invalid observable tool trace")
        elif self.status not in {"error", "interrupted"}:
            raise ValueError("Unavailable execution cannot claim a successful outcome")
        return self


class RuntimeObservation(Record):
    turns: list[RuntimeTurn]
    reminder_records: list[dict[str, JsonValue]]
    recovery_evidence: dict[str, JsonValue]
    model_requests: Count
    request_records: list[dict[str, JsonValue]]
    smtp_attempts: Count
    worker_import_attempts: Count
    storage_isolated: bool
    budget_exhausted: bool
    elapsed_ms: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def counted_requests(self):
        if self.model_requests != len(self.request_records):
            raise ValueError("Request count must match observed attempts")
        return self


class RuntimeCaseResult(Record):
    case: RuntimeCase
    reference_case_id: ID
    sample: Annotated[int, Field(ge=1, le=3)] = 1
    execution: Literal["not_run", "completed", "failed"] = "not_run"
    actual: RuntimeObservation | None = None
    checks: dict[str, bool | None] = Field(default_factory=dict)
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    failure_code: Literal["execution_failed", "case_timeout", "budget_exhausted"] | None = None

    @model_validator(mode="after")
    def coherent_result(self):
        if self.execution == "completed" and (self.actual is None or not self.checks or self.failure_code):
            raise ValueError("Completed observation requires actual evidence and checks")
        if self.execution == "not_run" and (self.actual is not None or self.checks or self.failure_code):
            raise ValueError("Unexecuted scenario cannot claim an observation")
        if (self.execution == "failed") != (self.failure_code is not None):
            raise ValueError("Failed collection requires failure code")
        return self


class RuntimeReport(Report):
    schema_version: Literal[2] = 2
    scorer_version: Literal["runtime-contracts-v1"] = "runtime-contracts-v1"
    cases: list[RuntimeCaseResult]
    failure_code: Literal["case_execution_failed", "evaluation_failed", "interrupted", "budget_exhausted"] | None = None
