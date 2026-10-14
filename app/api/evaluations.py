"""Read-only classifier results for the two-section evaluation page."""

from fastapi import APIRouter, HTTPException

from app.evaluation.classifier_report import ClassifierReport, read_classifier_report

router = APIRouter(prefix="/api/v1/evaluations")


@router.get("", response_model=ClassifierReport)
def get_evaluations():
    try:
        return read_classifier_report()
    except (OSError, ValueError):
        raise HTTPException(503, detail="Classifier results are unavailable") from None
