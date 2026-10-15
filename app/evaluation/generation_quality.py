"""Validated arithmetic over a single AI-reviewed sample; no generation on reads."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REVIEW_PATH = Path(__file__).resolve().parents[2] / "data/evaluation/generation_quality.json"
DIMENSIONS = ("faithfulness", "coverage", "relevance", "instruction_compliance", "status_accuracy", "context_relevance")
Dimension = Literal["faithfulness", "coverage", "relevance", "instruction_compliance", "status_accuracy", "context_relevance"]


class Record(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, allow_inf_nan=False)


class Rating(Record):
    score: Annotated[int, Field(ge=0, le=3)] | None
    applicable: bool
    reason: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def valid_rating(self):
        if not self.reason.strip() or (not self.applicable and self.score is not None):
            raise ValueError("Ratings require applicable evidence")
        return self


class ReviewedAnswer(Record):
    case_id: Annotated[str, Field(min_length=1)]
    input: Annotated[str, Field(min_length=1)]
    source: Annotated[str, Field(min_length=1)]
    required_facts: list[str]
    answer: str | None
    application_status: str
    ratings: dict[Dimension, Rating]
    critical_findings: list[str]

    @model_validator(mode="after")
    def complete_dimensions(self):
        if set(self.ratings) != set(DIMENSIONS):
            raise ValueError("Every planned dimension must be retained")
        if not self.answer or not self.answer.strip():
            if any(r.score is not None for r in self.ratings.values()):
                raise ValueError("Missing answers cannot receive quality ratings")
        return self


class GenerationReview(Record):
    schema_version: Literal[1]
    reviewer_type: Literal["ai_subagent"]
    reviewed_at: datetime
    source_commit: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    models: dict[str, str]
    provider_attempts: Annotated[int, Field(ge=0, le=20)]
    collection_note: str = ""
    cases: Annotated[list[ReviewedAnswer], Field(min_length=1, max_length=8)]
    limitations: list[str]

    @model_validator(mode="after")
    def review_identity(self):
        if self.reviewed_at.tzinfo is None or len({c.case_id for c in self.cases}) != len(self.cases):
            raise ValueError("Review requires an aware date and unique cases")
        return self

    def dimension_scores(self):
        results = {}
        for name in DIMENSIONS:
            applicable = [c.ratings[name] for c in self.cases if c.ratings[name].applicable]
            scores = [r.score for r in applicable if r.score is not None]
            results[name] = {"mean": sum(scores) / len(scores) if scores else None,
                             "scored": len(scores), "applicable": len(applicable), "planned": len(self.cases)}
        return results


def read_generation_review() -> GenerationReview:
    return GenerationReview.model_validate_json(REVIEW_PATH.read_text(encoding="utf-8"))
