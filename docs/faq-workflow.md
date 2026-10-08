# Natural-language FAQ workflow

`app.faq_workflow.run_faq_workflow(request)` implements REWORK step 3c:
structured question extraction → unchanged local TF-IDF retrieval → grounded
LLM explanation. The function remains standalone: it does not classify, invoke
the agent, or store history. Approved step 3d connects it behind chat's existing
classifier/confidence gate using `llm_assisted`. The FAQ-only endpoint and the
agent's pure `retrieve_faq` tool retain their existing local behavior.

## Input and execution

Supply one nonblank English request of at most 10,000 characters. Invalid Python
types raise `TypeError`; blank/oversized input raises `ValueError` before provider
initialization. English is a caller precondition, not an automatic language check.
Quotes, colons, and command prefixes are optional.

```python
from app.faq_workflow import run_faq_workflow

outcome = run_faq_workflow("Please answer this FAQ: What is the remote-work policy?")
print(outcome.status)
print(outcome.question)
print(outcome.result)  # Exact local policy/candidates and similarity scores.
print(outcome.reply)   # Separate generated explanation or fixed clarification.
```

This example makes real Groq calls when configured; it is not an offline demo.

1. The extraction prompt requests strict JSON with `status`, nullable `question`,
   and a bounded `reason`. Local validation checks status/field consistency and
   requires a nonblank verbatim contiguous question from the original request.
   The prompt requests the complete question, preserving qualifiers, numbers,
   negation, case, punctuation, and line breaks. It also accepts self-contained
   requests to explain a policy. The application does not paraphrase or normalize
   the selected question. Missing/uncertain question boundaries clarify;
   contextual, compound, and other-capability requests return `agent_required`.
2. A valid question calls existing `retrieve_faq(question)` exactly once. It
   indexes 25 fictional policies with 75 question phrasings, using its own fitted
   TF-IDF vectorizer and cosine similarity. Ranking, thresholds, distinct-policy
   margin, vocabulary coverage, dataset, and exact answers are unchanged.
   Similarity measures lexical overlap, not confidence probability. `ambiguous`
   returns fixed clarification with stored candidate questions; `no_match`
   returns a fixed no-reliable-match reply. Neither calls the presenter.
3. For `matched`, a presentation call receives JSON containing the original
   request, full question, and actual FAQ result, including selected policy ID,
   canonical candidate question, similarity score, exact answer, and demo flag.
   It requests a concise explanation identifying the policy as fictional demo
   information, preserving conditions/limits and using only the stored answer.
   Its structured status is `completed` or `needs_clarification`. If a material
   detail is absent, it should acknowledge that gap without inventing a yes/no
   answer. The matched raw result is retained even when the reply clarifies.

For example, retrieval can match `Can contractors work from home?` with a score
of 1.0 while the stored answer says only that eligible roles may request up to
two days per week with manager approval. The presenter is instructed to state
that contractor eligibility is unspecified and needs confirmation. This is a
prompt requirement, not an enforced semantic guarantee. A strong retrieval match
does not establish that the policy answers every part of the question.

Neither LLM stage binds tools. Original requests, questions, and tool observations
are data, including any embedded commands. Abstention never invokes the agent or
performs additional operations in this standalone function.

## Outcomes and retained records

| Status | Meaning |
| --- | --- |
| `completed` | Question extraction, matched retrieval, and presentation completed. |
| `needs_clarification` | Missing/ambiguous question, ambiguous/no-match retrieval, or presenter-reported missing policy detail. |
| `agent_required` | Context, multiple operations, or another capability is needed; no agent is invoked here. |
| `error` | Extraction/provider/validation or retrieval failed; no later stage runs. |
| `partial_failure` | Retrieval matched but presentation failed; exact policy retained with a qualified fallback. |

Every outcome includes original `request`, validated `question` (or `None`),
`result` (an unchanged `FAQResult` or `None`), separate `reply`, bounded `reason`,
`trace`, and total `elapsed_ms`. `result=None` means no successful retrieval;
`result.status="no_match"` means retrieval succeeded but found no reliable match.
Workflow clarification does not mutate a raw matched result into ambiguity.

Traces contain only actual attempted `extract_question`, `retrieve_faq`, and
`explain_result` stages with completion/failure, sanitized reason, and elapsed
milliseconds. Reasons distinguish `faq_ambiguous`, `faq_no_match`, and
`policy_detail_missing`, alongside extraction/handoff/failure codes.

Extraction failure retains no unvalidated question. Retrieval failure retains
its validated attempted question. Presentation failure retains the full matched
result and returns `partial_failure`/`presentation_failed`. Its fixed reply says
that the explanation is unavailable, identifies the retrieved policy as fictional,
warns that it may not resolve every detail, and appends the exact answer unchanged.
No retries, re-extraction, duplicate lookup, or fallback agent call occur.
Chat maps these outcomes to the existing HTTP status contract below.

## App chat integration

The runtime classifies once. FAQ predictions at or above the saved threshold use
this fixed workflow, including ordinary phrasing and quoted forms. Lower-confidence
or other-intent requests retain existing agent routing; the threshold is unchanged.
Missing/ambiguous question clarifies without lookup. Contextual/compound/unsupported
extraction abstention hands the unchanged request and prior history to the agent
once, retaining the extraction stage. Errors and partial failures stop without
agent fallback or repeated execution.

Completed and clarification outcomes return HTTP 200. Extraction/retrieval errors
and retained-result presentation partial failure return HTTP 503. API/client/
process-local history retain reply, raw result, exact question in the tool arguments,
and actual tool/workflow traces. The lookup duration in both traces describes the
same single call. Assistant turns show the readable reply without a separate
demo-policy warning caption. The inspector retains exact policy JSON/demo metadata
and a **FAQ workflow stages** expander.
Question extraction/presentation are labeled LLM stages, retrieval a local stage.
Rerendering does not submit another request.

For a high-confidence sample, try `Please answer this FAQ: What is the remote-work
policy?` in app chat. The saved classifier predicts FAQ at about 0.881 against
0.71. `Please answer this FAQ: Can contractors work from home?` predicts FAQ at
about 0.669 and uses the existing agent. Its prompt now limits recipient questions
to requested email drafts, treats independent policy questions separately from
prior drafting context, and requires acknowledging absent eligibility/details.
This is a prompt requirement, not a guaranteed factual validator. The agent still
uses the pure retriever; it does not recursively invoke this workflow.

The separate `POST /api/v1/faq` keeps its existing direct/agent-required schema and
local syntax/confidence gating, with no new LLM presentation or session history.

## Configuration and limits

- Reuses `GROQ_API_KEY`, loaded lazily from environment or root `.env` without
  overriding environment values. Optional `GROQ_FAQ_MODEL` defaults to
  `openai/gpt-oss-20b`; `openai/gpt-oss-120b` is also accepted. No silent fallback.
- Each LLM call uses strict JSON Schema, temperature zero, low reasoning effort,
  an 8,192-token output cap, a 30-second SDK timeout, and zero automatic retries.
  The timeout is not a hard deadline for the whole workflow. A matched success
  uses two LLM calls and one local lookup; unresolved retrieval uses one LLM call
  and one local lookup; extraction abstention uses only the extraction call.
- All provider-schema fields are required and extra properties forbidden. Local
  validation enforces question bounds/status consistency and a nonblank reply of
  at most 1,500 characters. Refusal, truncation, malformed JSON, or failed local
  validation stops the corresponding stage.
- External LangSmith tracing is disabled. Raw responses, exception text,
  credentials, and private reasoning are not retained in outcome traces.
  Request/question/matched policy are sent to Groq. This adds provider dependence
  to the workflow; the pure retrieval tool remains local.
- Schema/substring checks do not establish complete extraction, correct abstention,
  answer coverage, faithful prose, or resistance to embedded instructions. In
  particular, a shortened question can still be a valid substring. These semantic
  decisions require language-quality review; the raw stored answer is authoritative.
  Temperature zero does not guarantee identical model outputs.

## Verification

Offline doubles verify exact question/result transport, qualifiers and embedded
commands as data, abstention, execution counts, retrieval ambiguity/no-match,
presenter-reported missing details, malformed/non-verbatim outputs, provider/tool
failures, and qualified exact-answer fallback. Installed LangChain serialization
is exercised using a fake Groq SDK completion transport for both supported models.
Existing retrieval tests continue to cover the dataset and lexical behavior.
These checks do not establish live extraction/grounding quality or general
injection resistance; no live provider call was part of step 3c verification.
Step 3d additionally checks classifier gating, original-context handoff, status/
history/API/client preservation, low-confidence pure-agent lookup, and non-executing
UI rerenders. Its limited synthetic live HTTP review is recorded in `REWORK.md`.

Compatibility reference: [Groq structured outputs](https://console.groq.com/docs/structured-outputs).
Current Groq/LangChain/Pydantic/scikit-learn dependencies are reused unchanged.
