# Standalone natural-language sentiment workflow

`app.sentiment_workflow.run_sentiment_workflow(request)` implements REWORK step 2a:
a fixed LLM extraction → VADER scoring → LLM explanation sequence. It is not yet
connected to chat, the intent classifier, the agent registry, or session history.
The existing application still classifies requests first and uses its current routes.
Step 2b will separately integrate this workflow behind that classifier.

## Input and execution

Supply one nonblank English request of at most 10,000 characters. Invalid Python
types raise `TypeError`; blank/oversized input raises `ValueError` before provider
initialization. English is a caller precondition, not an automatic language check.

```python
from app.sentiment_workflow import run_sentiment_workflow

outcome = run_sentiment_workflow("Just check the sentiment of this I am happy")
print(outcome.status)
print(outcome.source_text)
print(outcome.result)
print(outcome.reply)
```

This example makes real provider calls when configured; it is not an offline demo.

1. The extraction prompt requests a strict JSON object containing `status`,
   `source_text`, and a fixed reason code. Local validation checks field types,
   status/reason consistency, and a nonblank verbatim source excerpt within the
   original request. Source text is never stripped, normalized, or paraphrased by
   application code. The original request is retained directly, not regenerated.
2. A `ready` extraction invokes the existing `analyze_sentiment` VADER function
   exactly once. The extracted source alone goes to the scorer.
3. A successful score goes to a separate presentation prompt together with the
   original request and selected source. The model returns a bounded `reply`.
   The VADER result remains authoritative and separate from the generated prose.

No tools are bound to either LLM call. Commands embedded in source text are data.
The workflow does not call the agent or perform additional operations on abstention.

## Outcomes and failures

| Status | Meaning |
| --- | --- |
| `completed` | Extraction, scoring, and explanation completed. |
| `needs_clarification` | Source is missing or ambiguous; fixed clarification reply, no scoring. |
| `agent_required` | Context, multiple operations, or another capability is needed; no agent is invoked here. |
| `error` | Extraction/configuration/provider/validation or scoring failed; no later stage ran. |
| `partial_failure` | Scoring succeeded but explanation failed; retain the result and return a fixed label/compound-score reply. |

Every outcome includes `request`, `source_text`, `result`, `reply`, `reason`,
`trace`, and total `elapsed_ms`. The trace contains only attempted stages, each
with its name, status, sanitized reason, and elapsed time. Extraction failures
retain no unvalidated source. Scoring failures retain the validated source.
Presentation failures never trigger rescoring or automatic retries.

These statuses belong to the standalone function. Mapping them into the chat
HTTP response and choosing an LLM-assisted route value are step 2b decisions.

## Configuration and limits

- Reuses `GROQ_API_KEY`, loaded lazily from the environment or root `.env` without
  overriding environment values. Optional `GROQ_SENTIMENT_MODEL` defaults to
  `openai/gpt-oss-20b`; `openai/gpt-oss-120b` is also accepted. No silent model fallback.
- Each call uses strict JSON Schema, temperature zero, low reasoning effort,
  an 8,192-token output cap, 30-second SDK timeout, and zero automatic retries.
  The SDK timeout is not a hard deadline for the entire workflow. Truncated
  responses fail validation rather than being repaired or used as partial source.
- Source length and reply bounds are checked locally. Provider schemas use required
  fields and forbid extras. The reply is limited to 1,500 characters.
- External LangSmith tracing is disabled for both calls. Raw provider responses,
  errors, and reasoning are not retained in the returned trace. Request/source/result
  data are sent to Groq and returned to the caller; handle these as private chat data.
- Only VADER scoring is deterministic. Verbatim checks cannot establish that the
  model selected the complete intended source. JSON validation cannot prove the
  explanation is faithful. Natural-language quality and injection resistance require
  separate evaluation; temperature zero does not guarantee identical outputs.

## Verification

Offline tests use provider doubles for input preservation, abstention, execution
counts, malformed extraction, provider/scorer failures, and retained-result fallback.
A fake SDK completion transport exercises the installed LangChain request/response
adapter and strict schema settings without contacting Groq. Existing VADER tests
cover the scoring behavior. These checks do not establish live language quality.

Compatibility reference: [Groq structured outputs](https://console.groq.com/docs/structured-outputs).
Installed versions checked for this slice: langchain-groq 1.1.3, groq 0.37.1,
Pydantic 2.13.5, and vaderSentiment 3.3.2. No dependencies were added or upgraded.
