# Shared stateless runtime

`app.runtime.execute_request(message)` is the stateless entry point for direct
keyword/FAQ execution, the fixed LLM-assisted sentiment workflow, and bounded agent
handoff. It accepts a nonblank string up to 10,000 characters and classifies once
using the trusted saved model and unchanged metadata threshold. It adds no dependencies.

```python
from app.runtime import execute_request

execution = execute_request('Check the sentiment of this I am sad')
print(execution.status, execution.result)
```

`ExecutionResult` contains `status`, `predicted_intent`, `confidence`, `route`,
`reason`, `result`, `trace`, `elapsed_ms`, `reply`, `agent_reason`, and
`workflow_trace`. The result is a sentiment dataclass, a list of keyword
dataclasses, or a FAQ dataclass. An empty keyword list is successful. FAQ ambiguity
and no match are successful retrieval outcomes, not tool failures.

High-confidence sentiment requests use `route="llm_assisted"`: structured source
extraction, one unchanged VADER scoring call, and bounded explanation. The runtime
returns the actual result and reply with the VADER tool arguments/result/timing in
`trace` and attempted stage statuses/reasons/timings in `workflow_trace`. Stage
and tool scoring durations describe the same call and should not be added twice.
Quoted syntax also uses this workflow; Groq configuration is now required for
high-confidence chat sentiment. See [sentiment-workflow.md](sentiment-workflow.md).

Missing/ambiguous source returns `needs_clarification` without scoring. Contextual,
compound, and unsupported extraction outcomes hand off once with the original
request/history; `workflow_trace` retains the extraction stage and `route="agent"`.
Low-confidence/invalid-confidence sentiment retains the existing agent fallback
without starting the fixed workflow. Thresholds and the classifier are unchanged.
Extraction/scoring failures return `error` without further execution. Explanation
failure returns `partial_failure` and a fixed factual reply with the successful
result and failed stage retained; there is no rescoring, retry, or agent repair.

A completed or failed tool attempt produces one trace with its actual tool name, extracted arguments, result, status, and tool duration. Total duration includes classification and lazy initialization, but excludes transport and serialization. When routing defers, the runtime calls `run_agent(message)` once with the original
validated message. This includes reminders, compound/LLM-dependent requests,
unsupported intents and requests rejected by confidence or extraction gates.
The current agent only exposes five analysis/composition tools; it can clarify
unavailable reminder/email actions but cannot schedule or send. See [agent-loop.md](agent-loop.md).

Agent status (`completed`, `needs_clarification`, `partial_failure`, `error`), reply
and actual traces pass through unchanged. `reason` retains the routing decision;
`agent_reason` holds the agent failure reason or null. Agent structured outputs
remain in traces, with `result` null. Wholly local direct replies and agent reasons
are null; LLM-assisted outcomes have a reply and null agent reason.
Total timing includes the full handoff, not just tool durations. Direct tool failure
does not invoke the agent. An unexpected exception escaping the agent returns
`error`, sanitized reply, `agent_reason="agent_unavailable"` and no fabricated
trace; missing observations do not establish that no tool ran.

Tool exceptions produce `error`, a null result, a tool-specific unavailable reason, and a failed trace. Classifier and routing exceptions raise `RuntimeUnavailable` with sanitized text; invalid inputs raise `TypeError` or `ValueError` before classification. Exception details are not exposed. Traces deliberately contain supplied tool arguments and results; they should not be logged wholesale as sensitive data.

`execute_request(message, faq_only=True)` serves the existing `/api/v1/faq` endpoint. It classifies once but permits only FAQ execution, preserving the endpoint's response fields, reasons, and HTTP status behavior. Fallback in this mode still produces `agent_required`, null result and no trace. No agent runs. A sentiment prediction sent to that endpoint cannot execute sentiment. See [faq-api.md](faq-api.md) for its public contract.

This entry point does not store history. The separate
`app.sessions.execute_session_request(session_id, message)` wrapper saves outcomes
from all three routes and supplies prior conversation to the agent; see
[session-memory.md](session-memory.md) and [chat-api.md](chat-api.md). Saved-model
sentiment checks use provider doubles for language stages; classifier evaluation
is separate from source/explanation fidelity. These checks do not establish
real-world routing quality or increase the saved model's direct coverage.

Earlier handoff verification on 2026-10-06: all 614 tests, `pip check` and whitespace checks pass.
Handoff tests cover original input, exactly-once execution, direct/FAQ isolation,
retained clarification/failure outcomes and total timing. Offline integration runs
the actual agent loop with a provider double; no new live provider calls were made.

REWORK step 2b verification on 2026-10-07: all 721 tests, `pip check`, and
whitespace checks pass. Workflow integration uses offline provider doubles and
the real saved classifier in representative API/UI examples. Live extraction/
explanation quality remains unverified. Existing LangChain history warnings remain.
