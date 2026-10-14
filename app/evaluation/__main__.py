"""Run explicitly with python -m app.evaluation; quality misses remain visible."""

import argparse
from pathlib import Path

from app.evaluation.reports import load_report
from app.evaluation.catalogue import report_directory
from app.evaluation.runner import run_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline synthetic classifier and FAQ evaluation; no LLM or side effects.")
    parser.add_argument("--report-dir", type=Path, default=report_directory(),
                        help="Local generated-report directory (default: OPSFLOW_EVALUATIONS_DIR or repository var/evaluations).")
    args = parser.parse_args()
    try:
        path = run_baseline(args.report_dir)
        report = load_report(path)
    except (OSError, ValueError):
        print("Evaluation could not start or save a valid report. Check local data, model and report storage.")
        return 1
    print(f"Report: {path.resolve()}")
    print(f"Execution: {report.state}; quality: {report.quality_verdict}")
    print(f"Observed cases: {sum(item.execution == 'completed' for item in report.cases)}/{len(report.cases)}")
    for key in ("classifier.accuracy", "classifier.macro_f1", "faq.match_precision", "faq.match_recall"):
        metric = report.metrics.get(key)
        if metric is not None:
            print(f"{key}: {metric.value:.4f}" if metric.value is not None else f"{key}: not scored")
    print("Pilot references await human review. No agent, generation or reminder quality is evaluated.")
    # No task-quality gate has been agreed; nonzero means operational failure only.
    return 0 if report.state == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
