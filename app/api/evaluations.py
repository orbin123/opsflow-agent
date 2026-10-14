"""Read-only classifier results for the two-section evaluation page."""

from fastapi import APIRouter, HTTPException

from app.evaluation.classifier_report import ClassifierReport, read_classifier_report
from app.evaluation.generation_quality import GenerationReview, read_generation_review

router = APIRouter(prefix="/api/v1/evaluations")


@router.get("", response_model=ClassifierReport)
def get_evaluations():
    try:
        return read_classifier_report()
    except (OSError, ValueError):
        raise HTTPException(503, detail="Classifier results are unavailable") from None


@router.get("/generation", response_model=GenerationReview)
def get_generation_quality():
    try:
        return read_generation_review()
    except (OSError, ValueError):
        raise HTTPException(503, detail="Generation review is unavailable") from None
