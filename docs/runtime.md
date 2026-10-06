# Shared deterministic runtime

`app.runtime.execute_request(message)` is the stateless entry point for sentiment, keyword, and FAQ execution. It accepts a nonblank string up to 10,000 characters, classifies once using the trusted saved model and metadata threshold, and dispatches to the existing intent/confidence and payload gates. It adds no dependencies.

```python
from app.runtime import execute_request

execution = execute_request('Analyze the sentiment of "I am sad"')
print(execution.status, execution.result)
```

`ExecutionResult` contains `status`, `predicted_intent`, `confidence`, `route`, `reason`, `result`, `trace`, and `elapsed_ms`. The result is a sentiment dataclass, a list of keyword dataclasses, or a FAQ dataclass. An empty keyword list is a successful result. FAQ ambiguity and no match are successful retrieval outcomes, not tool failures.

A completed or failed tool attempt produces one trace with its actual tool name, extracted arguments, result, status, and tool duration. Total duration includes classification and lazy initialization, but excludes transport and serialization. Fallback produces `agent_required`, a null result, and no trace; no tool or agent runs. Reminders, compound requests, LLM-dependent requests, and unsupported intents always defer. Existing conservative extraction rules also reject unsupported or contextual forms.

Tool exceptions produce `error`, a null result, a tool-specific unavailable reason, and a failed trace. Classifier and routing exceptions raise `RuntimeUnavailable` with sanitized text; invalid inputs raise `TypeError` or `ValueError` before classification. Exception details are not exposed. Traces deliberately contain supplied tool arguments and results; they should not be logged wholesale as sensitive data.

`execute_request(message, faq_only=True)` serves the existing `/api/v1/faq` endpoint. It classifies once but permits only FAQ execution, preserving the endpoint's response fields, reasons, and HTTP status behavior. A sentiment prediction sent to that endpoint cannot execute sentiment. See [faq-api.md](faq-api.md) for its public contract.

This slice has no chat endpoint, session memory, reply composition, or agent invocation. Saved-model checks demonstrate sentiment execution, FAQ retrieval outcomes, and keyword low-confidence fallback. Controlled predictions verify keyword dispatch; these checks do not establish real-world routing quality or increase the saved model's direct coverage.
