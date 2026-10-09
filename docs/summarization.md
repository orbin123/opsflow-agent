# Structured Summarization Tool

`app/tools/summarization.py` provides `summarize_text(text) -> SummaryResult` for future agent orchestration. It accepts source text only, not an instruction wrapper or conversation history. English is a caller precondition. The deterministic runtime continues to return `agent_required` for summarization.

## Contract

- Require a nonblank string of at most 10,000 characters. Preserve the supplied source in the provider message. Invalid types raise `TypeError`; blank/oversized inputs raise `ValueError` before provider initialization.
- Return required `summary` and `key_points` fields, with no extras. Local strict Pydantic validation trims output whitespace and requires a nonblank summary of at most 1,500 characters and zero to five nonblank points of at most 300 characters each.
- Prompt for source-grounded English output, preserving attribution and uncertainty. Embedded source instructions are material to summarize, not commands to execute. Schema validation does not establish factual correctness or eliminate prompt-injection risk.

```python
from app.tools.summarization import summarize_text

result = summarize_text("The office is closed on Friday.")
print(result.model_dump())
```

## Configuration

The client initializes on each valid call. It loads the repository-root `.env` without overriding existing environment variables, using an absolute path independent of the working directory. Importing the module does not load credentials or initialize the client.

- `GROQ_API_KEY`: required, never logged.
- `GROQ_SUMMARY_MODEL`: optional; defaults to `openai/gpt-oss-20b`. The supported override is `openai/gpt-oss-120b`. Other model names fail configuration validation; no automatic fallback.
- Temperature 0, low reasoning effort, 2,048 completion tokens, 30-second request timeout, zero SDK retries, no streaming or tool calls.
- Standalone calls do not retry. In agent execution, an explicit rate-limit rejection
  can wait and retry the same model request once under the shared turn deadline;
  see [agent-loop.md](agent-loop.md). No completed tool is reexecuted.
- ChatGroq binds a native `json_schema` response format with `strict: true`, required fields, and `additionalProperties: false`. Length/blank constraints are validated locally to keep the provider schema simple. Raw content is parsed with `json.loads`, with no markdown stripping or partial JSON repair.
- External LangSmith tracing is explicitly disabled for the call even if enabled in the environment. No raw response or model reasoning is returned or logged.

Verified environment: Python 3.12.13, `langchain-groq==1.1.3`, `groq==0.37.1`, Pydantic 2.13.5, python-dotenv 1.2.4, and LangSmith 0.14.4. The latter provides the context used to disable tracing. [Groq's structured-output documentation](https://console.groq.com/docs/structured-outputs) describes model support; [ChatGroq documentation](https://docs.langchain.com/oss/python/integrations/chat/groq) describes the integration.

## Failures

`SummarizationError.reason` is one of `configuration`, `authentication`, `rate_limit`, `timeout`, `provider_unavailable`, or `invalid_output`. Messages contain only the safe reason, with provider exception chaining suppressed. Provider HTTP 400 maps to configuration (for example an unsupported request/schema); connection/server/unexpected integration errors map to provider unavailability.

Refusal, a finish reason other than `stop`, malformed JSON, empty output, missing/extra fields, incorrect types, and output-limit violations fail explicitly. No summary is returned on failure. Future agent integration will record actual execution traces and timings; this slice does not add runtime/API/UI wiring, history, email drafting, action extraction, or chunking.

## Verification

On 2026-10-06, all 413 tests passed, including 38 new offline cases covering payload preservation, input/output boundaries, missing credentials, strict request settings, sanitized provider errors, refusal/truncation, no repair/retry, and disabled tracing. `pip check` and whitespace checks passed.

Three live synthetic examples using the default model passed schema validation and manual fidelity review: an operations update preserved dates/counts/uncertainty; a short note returned empty key points; a quoted embedded command was summarized without being followed. The model included that command among its key points, so relevance selection still needs broader evaluation. These checks are not a quality benchmark or a general injection-resistance guarantee. Automated tests make no live Groq requests.
