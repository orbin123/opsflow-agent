"""Native read-only presentation and one-shot GET transport for saved reports."""

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import TypeAdapter
import streamlit as st

from app.evaluation.catalogue import SavedReport, SavedRun
from app.ui.ui_client import ChatClientError


def _read(base_url: str, path: str, model):
    request = Request(base_url.rstrip("/") + path, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise ChatClientError("Saved evaluations are unavailable. Refresh to try again.")
            return TypeAdapter(model).validate_json(response.read())
    except HTTPError as exc:
        message = {404: "Saved evaluation is missing.", 422: "Saved evaluation is invalid."}.get(
            exc.code, "Saved evaluations are unavailable. Refresh to try again.")
        raise ChatClientError(message) from None
    except (URLError, OSError, ValueError):
        raise ChatClientError("Saved evaluations could not be loaded. Refresh to try again.") from None


def list_evaluations(base_url: str) -> list[SavedRun]:
    return _read(base_url, "/api/v1/evaluations", list[SavedRun])


def get_evaluation(base_url: str, run: SavedRun) -> SavedReport:
    saved = _read(base_url, f"/api/v1/evaluations/{run.run_id}?source={run.source}", SavedReport)
    if saved.report.run_id != run.run_id or saved.source != run.source:
        raise ChatClientError("Backend returned a different evaluation. Results were not displayed.")
    return saved


def show_evaluations(base_url: str) -> None:
    st.header("Evaluations")
    st.caption("Saved synthetic reports. Opening, refreshing and downloading never run an evaluation.")
    st.button("Refresh", key="refresh_evaluations", icon=":material/refresh:")
    with st.spinner("Loading saved evaluations…"):
        try:
            runs = list_evaluations(base_url)
        except ChatClientError as exc:
            st.error(str(exc))
            return
    if not any(run.source == "local" for run in runs):
        st.info("No local evaluation runs saved yet. Generate one explicitly with the evaluation CLI.")
    if not runs:
        return
    st.dataframe([{"Run": run.run_id, "Source": run.source, "Report": run.report_status,
                   "Started (recorded)": run.started_at, "Suites": ", ".join(run.suites),
                   "Execution": run.state, "Quality": run.quality_verdict,
                   "Observed / planned": f"{run.observed}/{run.planned}" if run.planned is not None else "Unavailable",
                   "App commit": run.source_commit, "Runtime model": run.runtime_model,
                   "Pilot fingerprint": run.dataset_version} for run in runs],
                 hide_index=True, alt="Saved evaluation runs, availability, execution, quality and versions")
    identities = {run.source + ":" + run.run_id: run for run in runs}
    selected = st.selectbox("Saved run", list(identities), key="evaluation_run",
                            format_func=lambda key: key + " · " + identities[key].report_status)
    if selected not in identities:
        st.error("Select an available catalogue entry.")
        return
    run = identities[selected]
    if run.report_status != "available":
        st.warning("Saved evaluation " + run.report_status + ". No results can be displayed. Refresh to check again.")
        return
    with st.spinner("Loading report…"):
        try:
            saved = get_evaluation(base_url, run)
        except ChatClientError as exc:
            st.error(str(exc))
            return
    report = saved.report
    runtime_report = report.schema_version == 2
    if saved.source == "bundled":
        st.warning("Bundled synthetic baseline — historical local execution, not a live hosted run. "
                   "The evaluated app version may differ from this app; do not treat it as current-version verification.")
    st.text(f"Evaluated commit: {report.provenance.get('source_commit', 'Unavailable')}\n"
            f"Started (recorded): {report.started_at}\nFinished (recorded): {report.finished_at or 'Not recorded'}\n"
            f"{'Harness execution' if runtime_report else 'Execution'}: {report.state}\nQuality verdict: {report.quality_verdict}\nScorer: {report.scorer_version}")
    if report.state == "running":
        st.warning("Incomplete saved snapshot. It may be active or interrupted; this page does not resume or monitor execution.")
    if report.failure_code:
        st.text("Execution failure: " + report.failure_code)
    st.caption("Quality verdict describes recorded criteria; no overall quality acceptance threshold is agreed.")
    if runtime_report:
        st.warning("Runtime contract evidence: " + str(report.provenance.get("execution_mode", "unavailable"))
                   + ". Scripted provider runs do not measure live model quality. Generated-answer semantics are not scored.")
    st.text("Reference status: " + str(report.provenance.get("reference_status", "Unavailable")))
    for limitation in report.limitations:
        st.text("• " + limitation)
    st.download_button("Download synthetic report JSON", data=report.model_dump_json(indent=2) + "\n",
                       file_name=f"evaluation-{report.run_id}.json", mime="application/json",
                       key="download_evaluation", on_click="ignore", icon=":material/download:")
    st.subheader("Category evidence")
    categories = []
    for suite in sorted({item.case.suite for item in report.cases}):
        cases = [item for item in report.cases if item.case.suite == suite]
        checks = [check for item in cases for check in item.checks.values()]
        categories.append({"Category": suite, "Planned": len(cases),
                           "Observed": sum(item.execution == "completed" for item in cases),
                           ("Failed collection" if runtime_report else "Failed execution"): sum(item.execution == "failed" for item in cases),
                           "Not run": sum(item.execution == "not_run" for item in cases),
                           "Scored checks": sum(check is not None for check in checks),
                           "Missing scores": sum(check is None for check in checks),
                           "Failed checks": sum(check is False for check in checks)})
    if categories:
        st.dataframe(categories, hide_index=True, alt="Case execution and recorded criterion counts by category")
    st.caption("Check counts cover recorded criteria; unexecuted cases have no check records. Classifier eligibility is not runtime routing.")
    if runtime_report:
        st.text("Extraction, trajectory and reminder/recovery: Observable contract checks below\n"
                "Generated-answer semantics and complete user goals: Not scored\n"
                "Live model quality/stability: Not evaluated in scripted mode")
    else:
        st.text("Extraction and tool use: Not evaluated\nGenerated answers: Not evaluated\n"
                "End-to-end agent goals: Not evaluated\nSide effects and recovery: Not evaluated\n"
                "Live reliability and efficiency: Not evaluated")
    st.subheader("Saved metrics")
    if not report.metrics:
        st.info("No saved metrics. Not scored.")
    else:
        st.dataframe([{"Metric": name, "Status": metric.status,
                       "Value": str(metric.value) if metric.value is not None else "Not scored",
                       "Numerator": metric.numerator, "Denominator": metric.denominator,
                       "95% interval": str(metric.interval_95) if metric.interval_95 is not None else "Unavailable"}
                      for name, metric in report.metrics.items()], hide_index=True,
                     alt="Saved metric values, scoring availability, explicit counts and confidence intervals")
        with st.expander("Metric definitions and limits"):
            st.caption("Scorer type: local deterministic comparisons and classifier statistics; no semantic judge.")
            for name, metric in report.metrics.items():
                st.text(name + "\n" + metric.note)
    with st.expander("Versions and provenance"):
        st.json(report.provenance)
    if not runtime_report:
        with st.expander("Classifier details"):
            st.json(report.classifier_details)
    st.subheader("Case evidence")
    if not report.cases:
        st.info("No planned cases in this saved report.")
        return
    cases = {item.case.case_id: item for item in report.cases}
    case_id = st.selectbox("Saved case", list(cases), key="evaluation_case",
                           format_func=lambda key: key + " · " + cases[key].execution)
    if case_id not in cases:
        return
    case = cases[case_id]
    st.text("Input")
    st.text(case.case.input)
    st.caption("Literal reference expectation")
    st.json(case.case.model_dump(mode="json", exclude={"input"}))
    st.text("Execution: " + case.execution)
    if case.failure_code:
        st.text("Failure: " + case.failure_code)
    st.caption("Actual saved observation")
    if case.actual is None:
        st.info("No observation recorded; not scored.")
    elif runtime_report:
        st.text(f"Model attempts: {case.actual.model_requests} · SMTP attempts: {case.actual.smtp_attempts}")
        for number, turn in enumerate(case.actual.turns, 1):
            with st.container(border=True):
                st.text(f"Turn {number}: {turn.status}")
                st.text(turn.input)
                if turn.http_status is not None:
                    st.text(f"HTTP transport: {turn.http_status} · Terminal outcome HTTP status: {turn.outcome_http_status or 'Not separate'}")
                if turn.execution:
                    st.text("Route: " + str(turn.execution.get("route")))
                    if turn.execution.get("reply"):
                        st.text(turn.execution["reply"])
                    with st.expander(f"Turn {number} saved execution and tool results"):
                        st.json(turn.execution)
                else:
                    st.info("No execution result recorded.")
                with st.expander(f"Turn {number} observable stage events"):
                    st.json(turn.events)
        with st.expander("Isolated reminder and recovery evidence"):
            st.json({"reminders": case.actual.reminder_records, "recovery": case.actual.recovery_evidence,
                     "storage_isolated": case.actual.storage_isolated, "worker_import_attempts": case.actual.worker_import_attempts,
                     "budget_exhausted": case.actual.budget_exhausted, "model_attempts": case.actual.request_records})
        with st.expander("Scorer supporting evidence"):
            st.json(case.evidence)
    else:
        st.json(case.actual.model_dump(mode="json"))
    st.caption("Criterion evidence")
    if case.checks:
        st.dataframe([{"Criterion": name, "Result": "Not scored" if check is None else "Pass" if check else "Fail"}
                      for name, check in case.checks.items()], hide_index=True,
                     alt="Selected case criterion pass, fail and missing-score evidence")
    else:
        st.info("No criterion scores recorded.")
    st.caption("Observable contracts are scored; prose faithfulness/relevance and live quality need separate review."
               if runtime_report else "This baseline records classifier/retrieval observations. Runtime routes, tool calls and generated answers were not evaluated.")
