"""One owner per run directory; atomic snapshots never resume evaluation."""

import os
from pathlib import Path
import tempfile
from typing import Annotated

from pydantic import Field, TypeAdapter

from app.evaluation.contracts import Report
from app.evaluation.runtime_contracts import RuntimeReport

ReportType = Annotated[Report | RuntimeReport, Field(discriminator="schema_version")]
_REPORT = TypeAdapter(ReportType)


def load_report(path: Path) -> Report | RuntimeReport:
    return parse_report(path.read_text(encoding="utf-8"))


def parse_report(data: str) -> Report | RuntimeReport:
    return _REPORT.validate_json(data)


class ReportWriter:
    def __init__(self, root: Path, run_id: str):
        # Exclusive directory creation prevents a second writer for the same run.
        if len(run_id) != 32 or any(char not in "0123456789abcdef" for char in run_id):
            raise ValueError("Invalid run ID")
        directory = root / run_id
        directory.mkdir(parents=True, exist_ok=False)
        self.path = directory / "report.json"
        self.run_id = run_id
        self.finished = False

    def save(self, report: Report | RuntimeReport) -> None:
        # Revalidate after runner mutations and before publishing any snapshot.
        report = parse_report(report.model_dump_json())
        if self.finished or report.run_id != self.run_id:
            raise ValueError("Cannot replace a finished or different run")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".report-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(report.model_dump_json(indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.finished = report.state != "running"
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
