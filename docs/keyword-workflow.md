# Natural-language keyword workflow

`app.keyword_workflow.run_keyword_workflow(request)` implements the fixed
LLM source extraction → local YAKE extraction → LLM presentation sequence.
REWORK step 3a supplies the standalone function; approved step 3b connects it to
chat behind intent/confidence gating using `llm_assisted`. The standalone function
does not classify, invoke the agent, or store history. The agent's registered
`extract_keywords` tool remains pure YAKE, with no recursive workflow calls.
FAQ is a separate later discussion.

## Input and execution

Supply one nonblank English request of at most 10,000 characters. Invalid Python
types raise `TypeError`; blank/oversized input raises `ValueError` before provider
initialization. English is a caller precondition, not an automatic language check.

```python
from app.keyword_workflow import run_keyword_workflow

outcome = run_keyword_workflow(
    "Find keywords in this The server failed after the deployment"
)
print(outcome.status)
print(outcome.source_text)
print(outcome.result)
print(outcome.reply)
```

This example makes real provider calls when configured; it is not an offline demo.
Quotes, colons, and command prefixes are optional.

1. The extraction prompt requests strict JSON with `status`, `source_text`, and a
   bounded reason code. Local validation checks field types/status consistency and
   requires a nonblank verbatim contiguous source excerpt from the original request.
   Preserve the complete source, including negation, punctuation and line breaks;
   application code does not strip, normalize, paraphrase, or stitch excerpts.
2. A `ready` extraction calls the unchanged `extract_keywords(source_text)` YAKE
   function exactly once. It returns up to five ranked one-to-three-word phrases
   and raw relevance scores. Lower scores mean greater relevance, not confidence.
   A nonblank source with no candidates returns an empty list successfully.
3. The presentation prompt receives the original request, selected source, and
   actual ordered result. It asks for a short reply preserving every returned phrase
   and its order, without inventing keywords or converting scores to confidence.
   Raw tool results remain authoritative and separate from generated prose.

Neither LLM stage binds tools. Source commands are treated as data. The workflow
never invokes the agent or performs extra operations on abstention.

## Outcomes and failures

| Status | Meaning |
| --- | --- |
| `completed` | Extraction, YAKE, and presentation completed; an empty keyword list is valid. |
| `needs_clarification` | Missing/ambiguous source; fixed clarification reply, no YAKE call. |
| `agent_required` | Context, compound operations, or another capability is needed; no agent is invoked here. |
| `error` | Extraction/configuration/provider/validation or YAKE failed; no later stage runs. |
| `partial_failure` | YAKE succeeded but presentation failed; retain results and supply a fixed factual fallback. |

Every outcome includes the original `request`, selected `source_text`, `result`,
`reply`, sanitized `reason`, `trace`, and total `elapsed_ms`. `result=None` means
no successful tool result; `result=[]` means YAKE completed without candidates.
Traces contain only attempted `extract_source`, `extract_keywords`, and
`explain_result` stages with status, reason, and actual duration.

Extraction failure retains no unvalidated source. Tool failure retains the
validated attempted input. Presentation failure retains the ranked phrases/scores;
its fallback lists those phrases in order, or states that no candidates were found,
and explicitly says the conversational explanation is unavailable. No retries,
re-extraction, or duplicate YAKE calls occur to repair presentation.

In chat, completed/clarification outcomes return HTTP 200. Extraction/tool errors
and retained-result presentation partial failures return HTTP 503. The classifier
runs once; high-confidence keyword predictions use this fixed workflow, including
quoted requests. Lower-confidence/other intents retain the existing agent routing.
Contextual/compound/unsupported extraction abstention hands the unchanged request
and prior history to the agent once. Missing/ambiguous source clarifies without a
tool call; extraction/tool/presentation failure does not hand off or retry.

API/client/process-local history preserve reply/result, the actual YAKE tool trace,
and `workflow_trace`. YAKE's duration appears in both traces for the same single
call. The existing inspector shows a **Keyword workflow stages** expander with
actual statuses/reasons/timings and LLM/local labels; readable replies appear in the assistant turn.
Raw keyword results remain visible as JSON under the existing rendering contract.
See [chat-api.md](chat-api.md) for response fields and history limitations.

## Configuration and limits

- Reuses `GROQ_API_KEY`, loaded lazily from the environment or root `.env` without
  overriding environment values. Optional `GROQ_KEYWORD_MODEL` defaults to
  `openai/gpt-oss-20b`; `openai/gpt-oss-120b` is also accepted. No silent fallback.
- Each call uses strict JSON Schema, temperature zero, low reasoning effort,
  an 8,192-token output cap, a 30-second SDK timeout, and zero automatic retries.
  The SDK timeout is not a hard deadline for the entire workflow. Truncation,
  refusal, malformed JSON, or local validation failure stops that stage.
- Provider schemas require all fields and forbid extras. Input/source bounds,
  outcome consistency, and the nonblank 1,500-character reply limit are enforced
  locally. Neither extraction nor presentation has a tool-selection loop.
- External LangSmith tracing is disabled. Raw provider responses, exception text,
  credentials, and private reasoning are not retained in outcome traces.
  Request/source/results are sent to Groq; these are private chat data.
- YAKE is the local deterministic stage. Schema/substring checks cannot prove the
  LLM selected the complete intended source. Reply schema checks cannot prove
  phrase fidelity, ordering, factual accuracy, or resistance to embedded commands.
  The presentation prompt requests these behaviors; it does not enforce semantics.
  Temperature zero does not guarantee identical LLM outputs.

## Verification

Offline provider doubles cover source preservation, abstention, exact tool counts,
invalid/non-verbatim extraction, provider/tool failures, result transport, and
retained-result fallback, including empty results. Fake SDK transport exercises
installed LangChain strict-schema serialization without contacting Groq.
Existing YAKE tests cover local extraction behavior. Chat checks additionally
cover classifier gating, original-history handoff, HTTP/API/client preservation,
clarification follow-up, and UI reply/stage rendering without resubmission. These
checks do not establish live language quality or general injection resistance.

Compatibility reference: [Groq structured outputs](https://console.groq.com/docs/structured-outputs).
The existing installed Groq/LangChain/YAKE dependencies are reused without changes.
