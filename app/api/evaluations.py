"""GET-only evaluation catalogue; these endpoints never run or resume work."""

from fastapi import APIRouter, HTTPException

from app.evaluation.catalogue import (CatalogueError, RunID, SavedReport, SavedRun,
                                      Source, list_saved_runs, read_saved_report)

router = APIRouter(prefix="/api/v1/evaluations")


@router.get("", response_model=list[SavedRun])
def get_evaluations():
    try:
        return list_saved_runs()
    except CatalogueError:
        raise HTTPException(503, detail="Saved evaluations are unavailable") from None


@router.get("/{run_id}", response_model=SavedReport)
def get_evaluation(run_id: RunID, source: Source = "local"):
    try:
        return read_saved_report(run_id, source)
    except CatalogueError as exc:
        status = {"missing": 404, "invalid": 422, "invalid_id": 422, "unavailable": 503}[exc.code]
        raise HTTPException(status, detail="Saved evaluation " + exc.code) from None
