"""Pure reference/trace checks; never execute or infer semantic faithfulness."""

from math import ceil
from collections import Counter
from datetime import UTC, datetime

from app.evaluation.contracts import Metric
from app.evaluation.runtime_contracts import RuntimeCase, RuntimeObservation
from app.evaluation.scoring import ratio


def match_calls(expected, actual):
    """Maximum one-to-one matching; repeated tool names cannot hide extra calls."""
    assigned = {}
    def assign(ref_index, visited):
        ref = expected[ref_index]
        for index, step in enumerate(actual):
            if (index in visited or step["tool"] != ref.tool
                    or any(step["arguments"].get(key) != value for key, value in ref.arguments.items())):
                continue
            visited.add(index)
            if index not in assigned or assign(assigned[index], visited):
                assigned[index] = ref_index
                return True
        return False
    for index in range(len(expected)):
        assign(index, set())
    return {ref_index: index for index, ref_index in assigned.items()}


def _instant(value):
    try:
        instant = datetime.fromisoformat(value)
        return instant.astimezone(UTC) if instant.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def score_runtime(case: RuntimeCase, actual: RuntimeObservation):
    checks = {"turn_count": len(actual.turns) == len(case.turns),
              "storage_isolated": actual.storage_isolated,
              "no_smtp": actual.smtp_attempts == 0,
              "no_worker": actual.worker_import_attempts == 0,
              "within_budget": not actual.budget_exhausted,
              "generated_answer_semantics": None}
    evidence = {"turns": []}
    for number, reference in enumerate(case.turns):
        prefix = f"turn_{number + 1}."
        if number >= len(actual.turns):
            checks[prefix + "outcome"] = False
            continue
        observed = actual.turns[number]
        execution = observed.execution or {}
        calls = execution.get("trace", [])
        mapping = match_calls(reference.calls, calls)
        matched = len(mapping)
        context_requests = [record for record in actual.request_records if record.get("component") == "agent" and record.get("turn") == number + 1]
        checks[prefix + "context_transport"] = all(record.get("user_inputs") == [turn.input for turn in case.turns[:number + 1]]
            for record in context_requests) if context_requests else None
        checks[prefix + "outcome"] = observed.status in reference.expected_statuses
        checks[prefix + "route"] = execution.get("route") in reference.allowed_routes if observed.status != "interrupted" else None
        checks[prefix + "transport_status"] = observed.http_status == reference.expected_http_status if reference.expected_http_status else None
        checks[prefix + "outcome_http_status"] = observed.outcome_http_status == reference.expected_outcome_http_status if reference.expected_outcome_http_status else None
        checks[prefix + "required_calls"] = matched == len(reference.calls)
        checks[prefix + "no_extra_calls"] = matched == len(calls)
        checks[prefix + "no_forbidden_calls"] = not any(step["tool"] in reference.forbidden_tools for step in calls)
        checks[prefix + "call_outcomes"] = all(index in mapping and calls[mapping[index]]["status"] == ref.status
            and (ref.status != "completed" or calls[mapping[index]].get("result") is not None)
            and (not ref.result_fields or isinstance(calls[mapping[index]].get("result"), dict)
                 and all(calls[mapping[index]]["result"].get(key) == value for key, value in ref.result_fields.items()))
                                              for index, ref in enumerate(reference.calls)) if reference.calls else None
        checks[prefix + "literal_arguments"] = matched == len(reference.calls) if reference.calls else None
        checks[prefix + "order"] = (matched == len(reference.calls) and list(mapping[index] for index in range(len(reference.calls)))
                                   == sorted(mapping.values())) if reference.calls and not reference.independent_order else None
        dependencies = []
        dependency_misses = 0
        reference_positions = {ref.call_id: index for index, ref in enumerate(reference.calls)}
        for index, ref in enumerate(reference.calls):
            if ref.dependency_call:
                parent = reference_positions[ref.dependency_call]
                source = calls[mapping[parent]].get("result") if parent in mapping else None
                valid = (parent in mapping and index in mapping and mapping[parent] < mapping[index]
                         and isinstance(source, dict) and ref.dependency_result_field in source
                         and calls[mapping[index]]["arguments"].get(ref.dependency_argument) == source[ref.dependency_result_field])
                dependencies.append(valid)
                dependency_misses += int(not valid and index in mapping)
        checks[prefix + "dependency_values"] = all(dependencies) if dependencies else None
        evidence["turns"].append({"turn": number + 1, "required": len(reference.calls), "actual": len(calls),
                                  "matched": matched - dependency_misses,
                                  "missing": len(reference.calls) - matched + dependency_misses,
                                  "extra": len(calls) - matched + dependency_misses,
                                  "matches": {reference.calls[index].call_id: position for index, position in mapping.items()}})
    expected = Counter((record.task, _instant(record.due_at), record.timezone, record.state) for record in case.expected_reminders)
    observed_records = Counter((str(record.get("task")), _instant(record.get("due_at")),
                               str(record.get("timezone")), str(record.get("state"))) for record in actual.reminder_records)
    checks["reminder_records_exact"] = expected == observed_records
    keys = [record.get("creation_key") for record in actual.reminder_records]
    checks["reminder_keys_unique"] = all(isinstance(key, str) and key for key in keys) and len(keys) == len(set(keys))
    # No creation is a valid no-side-effect observation, rather than a ratio score.
    if not keys:
        checks["reminder_keys_unique"] = True
    checks["reminder_frozen_clock"] = all(_instant(record.get("created_at")) == _instant(case.frozen_now) for record in actual.reminder_records)
    if case.recovery == "replay":
        for name in ("replay_equal", "zero_new_requests", "zero_new_tools", "records_unchanged"):
            checks["recovery." + name] = actual.recovery_evidence.get(name) is True
    elif case.recovery == "interrupted":
        for name in ("interrupted_state", "zero_new_requests", "zero_new_tools", "records_unchanged"):
            checks["recovery." + name] = actual.recovery_evidence.get(name) is True
    return checks, evidence


def summarize_runtime(results):
    observed = [item for item in results if item.actual is not None]
    metrics = {
        "runtime.observation_coverage": ratio(len(observed), len(results), "Collected scenarios / all planned samples; includes retained application errors."),
        "runtime.application_availability": ratio(sum(len(item.actual.turns) == len(item.case.turns)
            and all(turn.status not in {"error", "partial_failure"} for turn in item.actual.turns) for item in observed),
            len(results), "Scenarios without application error/partial failure / all planned samples, including unavailable/not-run."),
        "runtime.contract_success": ratio(sum(item.execution == "completed" and all(value for value in item.checks.values() if value is not None)
            for item in results), len(results), "All applicable observable reference checks passed / all planned samples. Scripted evidence is not live model quality or semantic goal success."),
    }
    matched = sum(turn["matched"] for item in observed for turn in item.evidence.get("turns", []))
    calls = sum(len(turn.execution.get("trace", [])) for item in observed for turn in item.actual.turns if turn.execution)
    required = sum(len(turn.calls) for item in results for turn in item.case.turns)
    metrics["runtime.tool_precision"] = ratio(matched, calls, "One-to-one name/literal-argument/dependency-value matches / recorded calls; workflow/event duplicates are not counted.")
    metrics["runtime.required_tool_coverage"] = ratio(matched, required, "Matched calls / all planned required calls, including scenarios not executed; no-tool cases use explicit constraints.")
    for key in sorted({key for item in results for key in item.checks}):
        values = [item.checks[key] for item in observed if item.checks.get(key) is not None]
        metrics["runtime." + key] = ratio(sum(values), len(values), "Applicable recorded criteria only; missing/unavailable observations remain explicit and in overall coverage.")
    for name, value in (("model_requests", sum(item.actual.model_requests for item in observed)), ("tool_calls", calls),
                        ("smtp_attempts", sum(item.actual.smtp_attempts for item in observed))):
        metrics["runtime." + name] = Metric(value=float(value), status="scored", note="Observed count, not a probability; scripted requests incur no provider calls.")
    durations = sorted(item.actual.elapsed_ms for item in observed)
    for percentile in (.5, .95):
        metrics[f"runtime.p{int(percentile * 100)}_scenario_ms"] = Metric(
            value=durations[max(0, ceil(percentile * len(durations)) - 1)] if durations else None,
            status="scored" if durations else "not_scored", note="Nearest-rank scenario latency; excludes subprocess startup. Scripted latency is not live provider performance.")
    return metrics
