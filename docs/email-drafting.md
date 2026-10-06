# Structured Email-Drafting Tool

`app/tools/email_drafting.py` provides `draft_email(recipient, content, instructions="Write a concise, professional email.") -> EmailDraftResult` for future agent orchestration. It composes English plain-text emails and never sends them. The existing deterministic runtime continues to require the agent for email drafting.

## Input contract

- `recipient`: required nonblank string, at most 320 characters, without CR/LF. A name, role, or email address is accepted; it is returned unchanged and never inferred or validated as a delivery address.
- `content`: required nonblank source string, at most 10,000 characters.
- `instructions`: nonblank writing-purpose/tone/formatting string, at most 1,000 characters; defaults to a concise professional email.

Invalid types raise `TypeError`; blank/oversized inputs and multiline recipients raise `ValueError` before provider initialization. Inputs are preserved in separately named JSON fields, without truncation. English is a caller precondition. The future agent must extract inputs and clarify missing recipients, unclear purposes, conflicting material facts, and ambiguous context; this tool does not implement clarification or history.

## Output contract

The provider generates only required `subject` and `body` fields, without extras. Local strict Pydantic validation trims outer whitespace and requires a nonblank single-line subject of at most 200 characters and a nonblank body of at most 4,000 characters. Internal body newlines are preserved. Code copies the input recipient and supplies fixed user actions:

```python
from app.tools.email_drafting import draft_email

result = draft_email(
    "Alex",
    "The maintenance window is Friday from 6 to 7 PM IST.",
    "Write a concise professional update.",
)
draft = result.email_draft  # recipient, subject, body
print(result.action_instructions)
# Review the draft for accuracy and replace any placeholders.
# Send or forward the reviewed draft to the intended recipient using your email client.
```

The body is recipient-facing prose; review/send instructions are separate. Optional missing details use visible placeholders such as `[Your name]`. Prompt rules prohibit invented facts, dates, commitments, attachments, addresses, or identities, and distinguish embedded source commands from writing instructions. Schema validation cannot establish fidelity, prose suitability, or injection resistance. No HTML, CC/BCC, attachments, delivery status, confidence, or private reasoning is returned. Later notification delivery will email the separate sections to the configured user and track its own outcome.

## Configuration and failures

Uses the existing pinned ChatGroq/Groq dependencies, independently of summarization configuration:

- `GROQ_API_KEY`: required.
- `GROQ_EMAIL_MODEL`: optional, default `openai/gpt-oss-20b`; only supported override is `openai/gpt-oss-120b`. Unsupported names fail configuration validation.
- Temperature 0, low reasoning effort, 2,048 completion tokens, 30-second request timeout, zero automatic retries. One nonstreaming call with native strict JSON Schema and no model tool execution; type/length limits are validated locally.
- Lazy repository-root `.env` loading without overriding environment values; no provider initialization on import. External tracing is explicitly disabled. No logging of credentials, input content, raw responses, or private reasoning.

[Groq documents strict-schema support](https://console.groq.com/docs/structured-outputs) for both supported models; [LangChain documents ChatGroq](https://docs.langchain.com/oss/python/integrations/chat/groq).

`EmailDraftingError.reason` is `configuration`, `authentication`, `rate_limit`, `timeout`, `provider_unavailable`, or `invalid_output`. Missing credentials, unsupported models, and provider HTTP 400 map to configuration. Connection/server/unexpected integration errors map to provider unavailability. Errors contain only sanitized reasons, with raw exception chaining suppressed.

Refusal, a finish reason other than `stop`, nontext/empty content, malformed JSON, missing/extra fields, incorrect types, multiline subjects, or output-limit violations fail without a draft. No partial success, silent JSON repair, retries, or model switching. Agent traces/timings and email delivery remain later work.

## Verification

On 2026-10-06, all 456 tests passed, including 43 new offline cases for source/writing separation, fixed user actions, input/output bounds, unchanged recipients, newline handling, strict provider settings, sanitized failures, refusal/truncation, and disabled tracing. `pip check` and whitespace checks passed. No dependencies were added.

Nine live synthetic requests were inspected across three prompt iterations. Initial office-closure drafts invented a Monday reopening date; appreciative drafts also added unsupported causal praise. Explicit grounding examples corrected the final inspected set: the operations draft preserved date/time/count/uncertainty; the warm-tone draft thanked the team and used a sender placeholder; the closure draft excluded an embedded malicious command and added no reopening date. These samples are not a quality benchmark or proof of factual fidelity/injection resistance. Users must review each draft before sending; automated tests make no live provider or email-delivery calls.
