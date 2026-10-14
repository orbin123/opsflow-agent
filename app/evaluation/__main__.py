"""Run explicitly with python -m app.evaluation; quality misses remain visible."""

import argparse
from pathlib import Path

from app.evaluation.reports import load_report
from app.evaluation.catalogue import report_directory
from app.evaluation.runner import run_baseline


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit saved evaluations: offline baseline or isolated scripted/live runtime contracts.")
    parser.add_argument("--suite", choices=("baseline", "runtime"), default="baseline")
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted",
                        help="Runtime only. Live explicitly invokes configured Groq models; never sends email.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Runtime scenario ID; repeat to select a subset.")
    parser.add_argument("--repeat", type=int, default=1, help="Runtime: 1–3 samples per selected scenario.")
    parser.add_argument("--max-cases", type=int, default=24, help="Runtime sample cap; all planned samples remain visible.")
    parser.add_argument("--max-model-requests", type=int, default=60, help="Runtime global attempt cap, at most 60.")
    parser.add_argument("--report-dir", type=Path, default=report_directory(),
                        help="Local generated-report directory (default: OPSFLOW_EVALUATIONS_DIR or repository var/evaluations).")
    args = parser.parse_args()
    try:
        if args.suite == "runtime":
            from app.evaluation.runtime_runner import run_runtime
            path = run_runtime(args.report_dir, mode=args.mode, case_ids=args.case_ids, repeats=args.repeat,
                               max_cases=args.max_cases, max_requests=args.max_model_requests)
        else:
            if args.mode != "scripted" or args.case_ids or args.repeat != 1 or args.max_cases != 24 or args.max_model_requests != 60:
                raise ValueError("Runtime options require --suite runtime")
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
    if args.suite == "baseline":
        print("Pilot references await human review. No agent, generation or reminder quality is evaluated.")
    else:
        print(f"Runtime mode: {args.mode}; model attempt cap: {args.max_model_requests}.")
        print("Synthetic contract evidence; reference human review and semantic scoring remain unavailable.")
    # No task-quality gate has been agreed; nonzero means operational failure only.
    return 0 if report.state == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
