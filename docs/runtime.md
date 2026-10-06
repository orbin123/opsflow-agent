# Shared stateless runtime

`app.runtime.execute_request(message)` is the stateless entry point for direct sentiment, keyword and FAQ execution plus bounded agent handoff. It accepts a nonblank string up to 10,000 characters, classifies once using the trusted saved model and metadata threshold, and dispatches to the existing intent/confidence and payload gates. It adds no dependencies.

```python
from app.runtime import execute_request

execution = execute_request('Analyze the sentiment of "I am sad"')
print(execution.status, execution.result)
```

`ExecutionResult` contains `status`, `predicted_intent`, `confidence`, `route`, `reason`, `result`, `trace`, `elapsed_ms`, `reply` and `agent_reason`. The result is a sentiment dataclass, a list of keyword dataclasses, or a FAQ dataclass. An empty keyword list is a successful result. FAQ ambiguity and no match are successful retrieval outcomes, not tool failures.

A completed or failed tool attempt produces one trace with its actual tool name, extracted arguments, result, status, and tool duration. Total duration includes classification and lazy initialization, but excludes transport and serialization. When routing defers, the runtime calls `run_agent(message)` once with the original
validated message. This includes reminders, compound/LLM-dependent requests,
unsupported intents and requests rejected by confidence or extraction gates.
The current agent only exposes five analysis/composition tools; it can clarify
unavailable reminder/email actions but cannot schedule or send. See [agent-loop.md](agent-loop.md).

Agent status (`completed`, `needs_clarification`, `partial_failure`, `error`), reply
and actual traces pass through unchanged. `reason` retains the routing decision;
`agent_reason` holds the agent failure reason or null. Agent structured outputs
remain in traces, with `result` null. Direct replies and agent reasons are null.
Total timing includes the full handoff, not just tool durations. Direct tool failure
does not invoke the agent. An unexpected exception escaping the agent returns
`error`, sanitized reply, `agent_reason="agent_unavailable"` and no fabricated
trace; missing observations do not establish that no tool ran.

Tool exceptions produce `error`, a null result, a tool-specific unavailable reason, and a failed trace. Classifier and routing exceptions raise `RuntimeUnavailable` with sanitized text; invalid inputs raise `TypeError` or `ValueError` before classification. Exception details are not exposed. Traces deliberately contain supplied tool arguments and results; they should not be logged wholesale as sensitive data.

`execute_request(message, faq_only=True)` serves the existing `/api/v1/faq` endpoint. It classifies once but permits only FAQ execution, preserving the endpoint's response fields, reasons, and HTTP status behavior. Fallback in this mode still produces `agent_required`, null result and no trace. No agent runs. A sentiment prediction sent to that endpoint cannot execute sentiment. See [faq-api.md](faq-api.md) for its public contract.

This slice has no chat endpoint, session memory or direct-route reply composition. Saved-model checks demonstrate sentiment execution, FAQ retrieval outcomes, and keyword low-confidence fallback. Controlled predictions verify keyword dispatch; these checks do not establish real-world routing quality or increase the saved model's direct coverage.

Verification on 2026-10-06: all 614 tests, `pip check` and whitespace checks pass.
Handoff tests cover original input, exactly-once execution, direct/FAQ isolation,
retained clarification/failure outcomes and total timing. Offline integration runs
the actual agent loop with a provider double; no new live provider calls were made.
