"""Explicit bounded runtime evaluation in disposable subprocesses; never a UI job."""

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter
from uuid import uuid4

from app.evaluation.reports import ReportWriter
from app.evaluation.runtime_contracts import (RuntimeCase, RuntimeCaseResult, RuntimeObservation,
                                             RuntimePilot, RuntimeReport, RuntimeTurn)
from app.evaluation.runtime_scoring import score_runtime, summarize_runtime

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "data/evaluation/runtime_pilot.json"
SCRIPTS = ROOT / "data/evaluation/runtime_scripts.json"
LIMITATIONS = [
    "Synthetic development references are pending human review, not a held-out benchmark.",
    "Scripted providers verify application/evaluator contracts; they do not measure live model quality.",
    "Observable payload/trajectory/state checks do not score semantic faithfulness, relevance or complete user goals.",
    "Standalone workflow scenarios bypass classification; chat scenarios retain the real classifier/runtime.",
    "Reminders use disposable storage and a frozen clock. No worker or SMTP delivery is permitted.",
    "Application failures remain in overall denominators; latency from scripted runs is not live performance.",
]


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runtime_cases(path=PILOT):
    pilot = RuntimePilot.model_validate_json(path.read_text(encoding="utf-8"))
    if _hash(ROOT / "data/company_faq.json") != pilot.faq_sha256:
        raise ValueError("Runtime reference FAQ fingerprint changed")
    # Scenario questions are separate from indexed retrieval material.
    policies = json.loads((ROOT / "data/company_faq.json").read_text())["faqs"]
    indexed = {q.casefold().strip() for policy in policies for q in [policy["question"], *policy["alternate_phrasings"]]}
    policy_ids = {policy["policy_id"] for policy in policies}
    for case in pilot.cases:
        for turn in case.turns:
            for call in turn.calls:
                if call.tool == "retrieve_faq" and call.arguments.get("question", "").casefold().strip() in indexed:
                    raise ValueError("Runtime reference duplicates an indexed FAQ question")
                if call.result_fields.get("policy_id") is not None and call.result_fields["policy_id"] not in policy_ids:
                    raise ValueError("Unknown reference policy")
    return pilot


def _provenance(pilot, mode, repeats, max_cases, max_requests):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    paths = sorted(path for package in ("evaluation", "core", "workflows", "tools", "chat", "reminders")
                   for path in (ROOT / "app" / package).glob("*.py"))
    working_tree = git("status", "--porcelain")
    models = {}
    if mode == "live":
        from dotenv import dotenv_values
        settings = dotenv_values(ROOT / ".env")
        for key in ("AGENT", "SUMMARY", "EMAIL", "SENTIMENT", "KEYWORD", "FAQ"):
            name = os.environ.get("GROQ_" + key + "_MODEL", settings.get("GROQ_" + key + "_MODEL") or "openai/gpt-oss-20b")
            models[key.lower()] = name if name in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"} else "invalid_configuration"
    return {"source_commit": git("rev-parse", "HEAD"), "working_tree_dirty": bool(working_tree) if working_tree is not None else None,
            "configured_models": models, "provider_settings": {"temperature": 0, "reasoning_effort": "low", "sdk_retries": 0, "timeout_seconds": 30},
            "execution_mode": mode, "runtime_model": "scripted_provider_double" if mode == "scripted" else "configured_groq_models",
            "judge_model": "not_invoked", "reference_status": pilot.reference_status, "pilot_name": pilot.name,
            "pilot_sha256": _hash(PILOT), "scripts_sha256": _hash(SCRIPTS), "faq_sha256": pilot.faq_sha256,
            "classifier_model_sha256": _hash(ROOT / "artifacts/models/intent_router_svm.joblib"),
            "implementation_sha256": hashlib.sha256(b"".join(str(path.relative_to(ROOT)).encode() + path.read_bytes() for path in paths)).hexdigest(),
            "versions": {name: version(name) for name in ("pydantic", "langchain-core", "langchain-groq", "groq", "scikit-learn")},
            "repeats": repeats, "max_cases": max_cases, "max_model_requests": max_requests,
            "isolation": "fresh subprocess and disposable chat/reminder files per sample; SMTP and worker blocked"}


def run_runtime(report_root: Path, *, mode="scripted", case_ids=None, repeats=1, max_cases=24, max_requests=60):
    if mode not in {"scripted", "live"} or not 1 <= repeats <= 3 or not 1 <= max_cases <= 72 or not 1 <= max_requests <= 60:
        raise ValueError("Invalid mode or evaluation budget")
    pilot = load_runtime_cases()
    selected = [case for case in pilot.cases if case_ids is None or case.case_id in case_ids]
    if not selected or case_ids is not None and set(case_ids) != {case.case_id for case in selected}:
        raise ValueError("Unknown or empty scenario selection")
    results = [RuntimeCaseResult(case=case.model_copy(update={"case_id": f"{case.case_id}-r{sample}"}),
               reference_case_id=case.case_id, sample=sample) for sample in range(1, repeats + 1) for case in selected]
    report = RuntimeReport(run_id=uuid4().hex, started_at=datetime.now(UTC).isoformat(), cases=results,
                           provenance=_provenance(pilot, mode, repeats, max_cases, max_requests), limitations=LIMITATIONS)
    writer = ReportWriter(report_root, report.run_id)
    writer.save(report)
    used = 0
    try:
        with tempfile.TemporaryDirectory(prefix="opsflow-evaluation-") as temporary:
            for index, item in enumerate(report.cases):
                if index >= max_cases or used >= max_requests:
                    report.failure_code = "budget_exhausted"
                    break
                root = Path(temporary) / item.case.case_id
                root.mkdir()
                job = root / "job.json"
                job.write_text(json.dumps({"case": item.case.model_dump(mode="json"), "scenario_id": item.reference_case_id,
                                           "mode": mode, "max_requests": max_requests - used}))
                try:
                    process = subprocess.run([sys.executable, "-m", "app.evaluation.runtime_runner", "--worker", str(job)],
                                             cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
                    if process.returncode != 0:
                        raise ValueError("Worker failed")
                    item.actual = RuntimeObservation.model_validate_json((root / "observation.json").read_text())
                    used += item.actual.model_requests
                    item.checks, item.evidence = score_runtime(item.case, item.actual)
                    item.execution = "failed" if item.actual.budget_exhausted else "completed"
                    item.failure_code = "budget_exhausted" if item.actual.budget_exhausted else None
                except subprocess.TimeoutExpired:
                    item.execution, item.failure_code = "failed", "case_timeout"
                    # Unknown in-flight completion must never release an unmeasured call budget.
                    report.failure_code = "case_execution_failed"
                    break
                except (OSError, ValueError):
                    item.execution, item.failure_code = "failed", "execution_failed"
                    report.failure_code = "case_execution_failed"
                    break
                report.quality_verdict = "has_failures" if any(False in result.checks.values() for result in results) else "passed"
                report.metrics = summarize_runtime(results)
                writer.save(report)  # Checkpoint each observation; reads never resume it.
                print(f"{item.case.case_id}: {item.execution}; model attempts {item.actual.model_requests}", flush=True)
                if item.actual.budget_exhausted:
                    report.failure_code = "budget_exhausted"
                    break
    except KeyboardInterrupt:
        report.failure_code = "interrupted"
    except (OSError, ValueError):
        report.failure_code = "evaluation_failed"
    report.finished_at = datetime.now(UTC).isoformat()
    report.state = "interrupted" if report.failure_code == "interrupted" else "failed" if report.failure_code else "completed"
    scored = [check for result in results for check in result.checks.values() if check is not None]
    report.quality_verdict = "has_failures" if False in scored else "passed" if scored else "not_scored"
    report.metrics = summarize_runtime(results)
    writer.save(report)
    return writer.path


def _worker(job_path: Path):
    """All application imports occur after disposable storage and delivery guards."""
    from contextlib import ExitStack
    import importlib.abc
    import smtplib
    import socket
    import sqlite3
    from unittest.mock import patch

    job = json.loads(job_path.read_text())
    case = RuntimeCase.model_validate_json(json.dumps(job["case"]))
    root = job_path.parent.resolve()
    if not root.parent.name.startswith("opsflow-evaluation-") or root.is_symlink():
        raise ValueError("Worker requires disposable evaluation storage")
    paths = {root / "chats.sqlite3", root / "reminders.sqlite3"}
    if any(path.exists() for path in paths) or job["mode"] not in {"scripted", "live"} or not 0 <= job["max_requests"] <= 60:
        raise ValueError("Worker storage must be fresh")
    if job["mode"] == "live":
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    for key, value in {"OPSFLOW_CHATS_DB": str(root / "chats.sqlite3"), "OPSFLOW_REMINDERS_DB": str(root / "reminders.sqlite3"),
                       "OPSFLOW_TIMEZONE": "Asia/Kolkata", "SMTP_USERNAME": "", "SMTP_PASSWORD": "",
                       "OPSFLOW_USER_EMAIL": "nobody@example.invalid", "LANGCHAIN_TRACING_V2": "false"}.items():
        os.environ[key] = value
    requests = []
    counters = {"smtp": 0, "worker": 0, "storage": True, "exhausted": False, "scheduled": 0, "turn": 0}
    class WorkerGuard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *args):
            if fullname == "app.reminders.reminder_worker":
                counters["worker"] += 1
                raise ImportError("Evaluation never starts the worker")
    guard = WorkerGuard()
    sys.meta_path.insert(0, guard)
    real_connect = sqlite3.connect
    def isolated_connect(database, *args, **kwargs):
        if Path(database).resolve() not in paths:
            counters["storage"] = False
            raise ValueError("Storage outside evaluation is forbidden")
        return real_connect(database, *args, **kwargs)
    def no_smtp(*args, **kwargs):
        counters["smtp"] += 1
        raise RuntimeError("SMTP blocked by evaluation")
    def no_network(*args, **kwargs):
        raise RuntimeError("Scripted evaluation blocks network")
    with ExitStack() as patches:
        patches.enter_context(patch.object(sqlite3, "connect", isolated_connect))
        patches.enter_context(patch.object(smtplib, "SMTP", no_smtp))
        patches.enter_context(patch.object(smtplib, "SMTP_SSL", no_smtp))
        if job["mode"] == "scripted":
            patches.enter_context(patch.object(socket.socket, "connect", no_network))
            patches.enter_context(patch.object(socket, "create_connection", no_network))
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from fastapi.encoders import jsonable_encoder
        from app.core import agent, execution_events
        from app.chat import sessions
        from app.workflows import sentiment_workflow, keyword_workflow, faq_workflow
        from app.tools import summarization, email_drafting, reminders
        from app.reminders import chat_reminders
        from app.observability import monitoring
        monitoring.logger.disabled = True  # Child-only metrics/logs never reach the running backend.
        frozen = datetime.fromisoformat(case.frozen_now)
        real_turn, real_schedule = chat_reminders.reminder_turn, reminders.schedule_reminder
        patches.enter_context(patch.object(sessions, "reminder_turn", lambda ident: real_turn(ident, now=frozen)))
        def schedule(*args, **kwargs):
            if reminders._database_path(None).resolve() not in paths or sessions.database_path() not in paths:
                counters["storage"] = False
                raise ValueError("Storage isolation failed before scheduling")
            result = real_schedule(*args, **kwargs, now=frozen)
            counters["scheduled"] += 1
            return result
        patches.enter_context(patch.object(chat_reminders, "schedule_reminder", schedule))
        scripts = json.loads(SCRIPTS.read_text())["scenarios"][job["scenario_id"]] if job["mode"] == "scripted" else {}
        queues = {module: iter(responses) for module, responses in scripts.items()}
        class Model:
            def __init__(self, label, underlying=None):
                self.label, self.underlying = label, underlying
            def invoke(self, messages):
                if len(requests) >= job["max_requests"]:
                    counters["exhausted"] = True
                    raise RuntimeError("Evaluation model-request budget exhausted")
                started = perf_counter()
                record = {"component": self.label, "turn": counters["turn"], "outcome": "failed", "provider_invoked": False, "elapsed_ms": 0.0,
                          "user_inputs": [message.content for message in messages if isinstance(message, HumanMessage)] if self.label == "agent" else []}
                requests.append(record)
                try:
                    if (case.fault == "summary_provider_failure" and self.label == "summary"
                            or case.fault == "provider_after_schedule" and self.label == "agent" and counters["scheduled"]):
                        record["controlled_failure"] = case.fault
                        raise RuntimeError("Controlled evaluation provider failure")
                    if self.underlying is not None:
                        record["provider_invoked"] = True
                        response = self.underlying.invoke(messages)
                    else:
                        scripted = next(queues.get(self.label, iter([])))
                        if scripted["kind"] == "error":
                            raise RuntimeError("Scripted provider failure")
                        if scripted["kind"] == "tool":
                            arguments = dict(scripted["arguments"])
                            for key, value in arguments.items():
                                if isinstance(value, dict) and set(value) == {"$result"}:
                                    observation = next(message for message in reversed(messages) if isinstance(message, ToolMessage))
                                    arguments[key] = json.loads(observation.content)[value["$result"]]
                            response = AIMessage(content="", tool_calls=[{"name": scripted["name"], "args": arguments,
                                                  "id": "evaluation-call-" + str(len(requests))}], response_metadata={"finish_reason": "tool_calls"})
                        else:
                            response = AIMessage(content=json.dumps(scripted["value"]), response_metadata={"finish_reason": "stop"})
                    record["outcome"] = "completed"
                    return response
                finally:
                    record["elapsed_ms"] = (perf_counter() - started) * 1000
        for label, module in (("agent", agent), ("sentiment", sentiment_workflow), ("keyword", keyword_workflow),
                              ("faq", faq_workflow), ("summary", summarization), ("email", email_drafting)):
            original = module._create_model
            def factory(*args, label=label, original=original, **kwargs):
                return Model(label, original(*args, **kwargs) if job["mode"] == "live" else None)
            patches.enter_context(patch.object(module, "_create_model", factory))
        started = perf_counter()
        turns = []
        session_id = "evaluation-" + job["scenario_id"]
        def records():
            path = root / "reminders.sqlite3"
            if not path.exists():
                return []
            with sqlite3.connect(path) as connection:
                connection.row_factory = sqlite3.Row
                return [dict(row) for row in connection.execute("SELECT * FROM reminders ORDER BY due_at, task")]
        def execute(reference, turn_id):
            events = []
            http_status, outcome_status, failure = None, None, None
            with execution_events.observe_events(execution_events.EventEmitter(session_id, turn_id, events.append)):
                if case.entry_point != "chat":
                    function = {"sentiment_workflow": sentiment_workflow.run_sentiment_workflow,
                                "keyword_workflow": keyword_workflow.run_keyword_workflow,
                                "faq_workflow": faq_workflow.run_faq_workflow}[case.entry_point]
                    result = function(reference.input)
                    tool_name = {"sentiment_workflow": "analyze_sentiment", "keyword_workflow": "extract_keywords", "faq_workflow": "retrieve_faq"}[case.entry_point]
                    trace = [dict(tool=tool_name, arguments=event.get("arguments", {}), status=event["status"],
                                  result=event.get("result"), elapsed_ms=event["elapsed_ms"])
                             for event in events if event["event"] == "step_finished" and event.get("stage") == tool_name]
                    execution = jsonable_encoder({"status": result.status, "route": "llm_assisted", "reason": result.reason,
                                                  "result": result.result, "reply": result.reply, "trace": trace,
                                                  "workflow_trace": result.trace, "elapsed_ms": result.elapsed_ms})
                elif reference.transport == "python":
                    execution = jsonable_encoder(asdict(sessions.execute_session_request(session_id, reference.input, turn_id=turn_id)))
                else:
                    from fastapi.testclient import TestClient
                    from app.main import app
                    with TestClient(app) as client:
                        response = client.post("/api/v1/chat" + ("/stream" if reference.transport == "sse" else ""),
                                               json={"session_id": session_id, "message": reference.input, "turn_id": turn_id})
                        http_status = response.status_code
                        if reference.transport == "sse":
                            sse = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                            events = sse
                            terminal = sse[-1]
                            outcome_status = terminal.get("http_status", 503)
                            execution = terminal.get("execution")
                        else:
                            saved = sessions.get_chat(session_id)
                            execution = saved["turns"][-1]["execution"]
                        failure = None if execution is not None else "runtime_unavailable"
            return RuntimeTurn(input=reference.input, status=execution["status"] if execution else "error",
                               execution=execution, events=events, http_status=http_status, outcome_http_status=outcome_status, failure_code=failure)
        recovery = {}
        try:
            if case.recovery == "interrupted":
                store = sessions._get_store()
                store.begin(session_id, case.input, "interrupted-turn")
                sessions.close_chat_store()
                saved = sessions.get_chat(session_id)
                turns.append(RuntimeTurn(input=case.input, status="interrupted", execution=None))
                recovery = {"interrupted_state": saved["turns"][0]["state"] == "interrupted",
                            "zero_new_requests": len(requests) == 0, "zero_new_tools": counters["scheduled"] == 0,
                            "records_unchanged": records() == []}
            else:
                for index, reference in enumerate(case.turns):
                    counters["turn"] = index + 1
                    turns.append(execute(reference, f"{case.case_id}-turn-{index}"))
                    if counters["exhausted"]:
                        break
                if case.recovery == "replay":
                    before, request_count = records(), len(requests)
                    saved_before = sessions.get_chat(session_id)
                    sessions.close_chat_store()
                    sessions._sessions.clear()
                    replay = execute(case.turns[0], f"{case.case_id}-turn-0")
                    saved_after = sessions.get_chat(session_id)
                    recovery = {"replay_equal": replay.execution == turns[0].execution and saved_before == saved_after,
                                "zero_new_requests": len(requests) == request_count,
                                "zero_new_tools": not any(event.get("kind") == "tool" and event["event"] == "step_started" for event in replay.events),
                                "records_unchanged": records() == before}
        finally:
            sessions.close_chat_store()
        observation = RuntimeObservation(turns=turns, reminder_records=records(), recovery_evidence=recovery,
            model_requests=len(requests), request_records=requests, smtp_attempts=counters["smtp"],
            worker_import_attempts=counters["worker"], storage_isolated=counters["storage"], budget_exhausted=counters["exhausted"],
            elapsed_ms=(perf_counter() - started) * 1000)
        (root / "observation.json").write_text(observation.model_dump_json())


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit("Use python -m app.evaluation --suite runtime to run explicitly.")
    try:
        _worker(Path(sys.argv[2]))
    except Exception:
        raise SystemExit(1) from None
