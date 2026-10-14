"""Read saved reports without importing runners or repairing report storage."""

import os
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import StringConstraints

from app.evaluation.contracts import Record
from app.evaluation.reports import ReportType, load_report

ROOT = Path(__file__).resolve().parents[2]
BUNDLED_ID = "89c111c7f91d4382b6ca872b62dbada4"
RunID = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
Source = Literal["local", "bundled"]


def report_directory() -> Path:
    configured = os.environ.get("OPSFLOW_EVALUATIONS_DIR")
    return Path(configured).expanduser().resolve() if configured else ROOT / "var/evaluations"


class CatalogueError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SavedRun(Record):
    run_id: RunID
    source: Source
    report_status: Literal["available", "missing", "invalid", "unavailable"]
    suites: list[str] = []
    started_at: str | None = None
    source_commit: str | None = None
    runtime_model: str | None = None
    dataset_version: str | None = None
    state: str | None = None
    quality_verdict: str | None = None
    planned: int | None = None
    observed: int | None = None


class SavedReport(Record):
    source: Source
    report: ReportType


def read_saved_report(run_id: str, source: Source = "local") -> SavedReport:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id) or source not in {"local", "bundled"}:
        raise CatalogueError("invalid_id")
    if source == "bundled":
        if run_id != BUNDLED_ID:
            raise CatalogueError("missing")
        path = ROOT / "data/evaluation/baseline.json"
    else:
        path = report_directory() / run_id / "report.json"
    # Never follow run/report symlinks, even when they point inside the root.
    if path.parent.is_symlink() or path.is_symlink():
        raise CatalogueError("invalid")
    try:
        report = load_report(path)
        if report.run_id != run_id:
            raise ValueError("Report identity mismatch")
    except FileNotFoundError:
        raise CatalogueError("missing") from None
    except (ValueError, UnicodeError):
        raise CatalogueError("invalid") from None
    except OSError:
        raise CatalogueError("unavailable") from None
    return SavedReport(source=source, report=report)


def _summary(run_id: str, source: Source) -> SavedRun:
    try:
        report = read_saved_report(run_id, source).report
    except CatalogueError as exc:
        return SavedRun(run_id=run_id, source=source, report_status=exc.code)
    provenance = report.provenance
    return SavedRun(run_id=run_id, source=source, report_status="available",
                    suites=sorted({item.case.suite for item in report.cases}),
                    started_at=report.started_at,
                    source_commit=provenance.get("source_commit") if isinstance(provenance.get("source_commit"), str) else None,
                    runtime_model=provenance.get("runtime_model") if isinstance(provenance.get("runtime_model"), str) else None,
                    dataset_version=provenance.get("pilot_sha256") if isinstance(provenance.get("pilot_sha256"), str) else None,
                    state=report.state, quality_verdict=report.quality_verdict,
                    planned=len(report.cases), observed=sum(item.actual.output is not None for item in report.cases)
                    if report.schema_version == 3 else sum(item.actual is not None for item in report.cases))


def list_saved_runs() -> list[SavedRun]:
    root = report_directory()
    try:
        entries = list(root.iterdir()) if root.exists() else []
    except OSError:
        raise CatalogueError("unavailable") from None
    # Run-owned directories may lack a snapshot after a failed first write.
    runs = [_summary(entry.name, "local") for entry in entries
            if re.fullmatch(r"[a-f0-9]{32}", entry.name)]
    runs.sort(key=lambda run: (run.started_at or "", run.run_id), reverse=True)
    # The selected tracked baseline is separate from disposable generated records.
    if (ROOT / "data/evaluation/baseline.json").exists():
        runs.append(_summary(BUNDLED_ID, "bundled"))
    return runs
