"""Read the trained classifier's recorded results; never load or run its model."""

from datetime import date
import hashlib
from math import isclose
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_DIR = Path(__file__).resolve().parents[2] / "artifacts/models"
Intent = Literal["compound_request", "email_drafting", "faq_retrieval", "keyword_extraction",
                 "out_of_scope", "reminder_creation", "sentiment_analysis", "summarization"]
UnitScore = Annotated[float, Field(ge=0, le=1)]


class Record(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class ClassScores(Record):
    precision: UnitScore
    recall: UnitScore
    f1: UnitScore = Field(alias="f1-score")
    support: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def whole_examples(self):
        if not self.support.is_integer():
            raise ValueError("Support must count whole examples")
        return self


class Dataset(Record):
    labels: Annotated[list[Intent], Field(min_length=8, max_length=8)]
    row_count: Annotated[int, Field(gt=0)]


class Split(Record):
    development_rows: Annotated[int, Field(gt=0)]
    test_rows: Annotated[int, Field(gt=0)]
    strategy: str


class Pipeline(Record):
    classifier: str
    features: str


class TestMetrics(Record):
    accuracy: UnitScore
    macro_f1: UnitScore
    weighted_f1: UnitScore
    per_label: dict[Intent, ClassScores]


class ClassifierReport(Record):
    created_on: date
    dataset: Dataset
    split: Split
    pipeline: Pipeline
    test_metrics: TestMetrics

    @model_validator(mode="after")
    def consistent_results(self):
        labels = self.dataset.labels
        scores = self.test_metrics.per_label
        if (len(set(labels)) != 8 or set(labels) != set(scores)
                or self.dataset.row_count != self.split.development_rows + self.split.test_rows
                or sum(s.support for s in scores.values()) != self.split.test_rows):
            raise ValueError("Classifier labels, split and support must agree")
        macro, weighted = self.averages()
        if (not isclose(macro["F1"], self.test_metrics.macro_f1, abs_tol=1e-12)
                or not isclose(weighted["F1"], self.test_metrics.weighted_f1, abs_tol=1e-12)
                or not isclose(weighted["Recall"], self.test_metrics.accuracy, abs_tol=1e-12)):
            raise ValueError("Recorded averages must agree with per-class scores")
        return self

    def averages(self):
        scores = list(self.test_metrics.per_label.values())
        total = sum(s.support for s in scores)
        macro = {label: sum(getattr(s, field) for s in scores) / len(scores)
                 for label, field in (("Precision", "precision"), ("Recall", "recall"), ("F1", "f1"))}
        weighted = {label: sum(getattr(s, field) * s.support for s in scores) / total
                    for label, field in (("Precision", "precision"), ("Recall", "recall"), ("F1", "f1"))}
        return macro, weighted


class _ModelMetadata(ClassifierReport):
    model_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def read_classifier_report() -> ClassifierReport:
    metadata = _ModelMetadata.model_validate_json(
        (MODEL_DIR / "intent_router_svm_metadata.json").read_text(encoding="utf-8"))
    if hashlib.sha256((MODEL_DIR / "intent_router_svm.joblib").read_bytes()).hexdigest() != metadata.model_sha256:
        raise ValueError("Classifier model does not match recorded results")
    return ClassifierReport.model_validate(metadata.model_dump(by_alias=True))
