"""One owner per run directory; atomic snapshots never resume evaluation."""

import os
from pathlib import Path
import tempfile

from app.evaluation.contracts import Report


def load_report(path: Path) -> Report:
    return Report.model_validate_json(path.read_text(encoding="utf-8"))


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

    def save(self, report: Report) -> None:
        # Revalidate after runner mutations and before publishing any snapshot.
        report = Report.model_validate_json(report.model_dump_json())
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
