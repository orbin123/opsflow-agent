# Standalone agent loop

`app.agent.run_agent(message, history=None)` runs one English request using LangChain
ChatGroq local tool calling. `execute_request` now invokes it when direct routing defers; the FAQ-only API
and classifier gates retain their contracts. Session history is supplied by `app.sessions`; standalone calls remain stateless. HTTP/UI wiring, reminder scheduling and
email submission remain separate slices. No external tracing or source logging.

## Contract

Input is a nonblank string of at most 10,000 characters. Optional history is a list of user/assistant messages, inserted after the system prompt and before the current message. System/tool messages supplied as history are rejected before model initialization. The loop never saves or mutates prior history; see [session-memory.md](session-memory.md). Invalid input raises
TypeError/ValueError before configuration or provider initialization. Lazy
repository-root `.env` loading does not override environment values. Configure
`GROQ_API_KEY` and optionally `GROQ_AGENT_MODEL` (default
`openai/gpt-oss-20b`; supported override `openai/gpt-oss-120b`). Temperature 0,
low reasoning effort, 2,048 completion tokens, 30-second request timeout and
zero retries. Existing installed LangChain Core/ChatGroq APIs are used; the now directly
imported langchain-core is pinned to its installed 1.6.6 version. No new framework
dependency. Tool calling does not use strict provider JSON output;
application code validates arguments and the final JSON reply locally.

`AgentResult` contains status, reply, reason, trace and elapsed_ms. Status is
completed, needs_clarification, partial_failure or error. Final model output must
contain only status (completed/needs_clarification) and a nonblank reply of at
most 10,000 characters. Malformed output, refusal and nonexpected finish reasons
fail. Source-instruction isolation, clarification decisions, factual fidelity and
correct dependency selection remain model/prompt limitations, not guarantees.

## Tools, dependencies and bounds

The allowlist is analyze_sentiment, extract_keywords, retrieve_faq,
summarize_text and draft_email. Arguments have strict types, no extra fields and
nonblank text bounds; draft inputs retain existing recipient/content/instructions
limits. Tool implementation validation remains in place. The model sees descriptions
and JSON schemas. Calls execute sequentially; every completed observation is
serialized into a ToolMessage linked to its call ID before the next model call.
A FAQ result retains its demo flag, stored answer and ambiguity/no-match outcome.
The prompt directs self-contained policy questions to FAQ lookup without asking
for a recipient or department; recipient clarification applies to requested email
drafts. Independent questions do not inherit unrelated drafting intent from history.
For matched policies, the prompt requires preserving conditions and acknowledging
material details absent from the answer, including unspecified group eligibility.
These are language instructions, not an enforced semantic validator.
Application code renders successful drafts from their structured tool results,
appends the fixed user actions, and qualifies any accompanying or historical demo FAQ result;
the final model cannot rewrite these drafts or omit those sections. The prompt asks for clarification on missing source/recipient, unavailable
capabilities, context-dependent references, and unclear policy results. It requires
using the summary/draft tools and preserving draft/action separation.

Six orchestration model calls and five tool attempts are allowed. Calls made
inside summarize_text/draft_email are additional provider calls bounded by their
existing settings. At most one tool call per model response; unknown tools,
invalid arguments, absent/reused IDs and simultaneous calls stop before execution.
A 120-second elapsed-time budget is checked before each operation and after an
orchestration provider call. In-flight tools/provider operations cannot be forcibly
cancelled, so this is a soft budget; retained results can exceed it. No retry,
JSON repair, fallback model or speculative continuation after failures.

## Observability and failures

Each actually attempted tool has name, validated arguments, completed/failed
status, structured result or sanitized reason, and elapsed_ms. Invalid proposals
are rejected without an execution trace entry. Total timing includes orchestration.
No raw model response, reasoning tokens or provider exception text is returned.
Traces contain source content and should be treated as private application data,
not logged. There is no external tracing even if tracing environment variables
are enabled.

Stop on the first execution failure. Preserve earlier successful results in the
trace and return partial_failure; failures before any success return error.
Application-generated failure replies list successful tool names and the stable
reason; callers can render retained results from traces without another LLM call.
FAQ no_match/ambiguous is a completed retrieval, not an infrastructure failure.
No record is scheduled and no email is sent by this loop.

## Verification

Offline tests cover a dependency chain with observations, FAQ-to-draft argument
flow and separated output, clarification, input/schema boundaries, malformed and
multiple calls, duplicate IDs, provider/tool failure before/after success,
retained results, tool/model budgets, time overrun, intended configuration and
disabled tracing. Deterministic doubles verify protocol behavior; they do not
prove the model will choose correct dependencies for arbitrary requests.

Verification on 2026-10-06: all 608 tests (36 new), pip check and whitespace
checks pass. Installed Python 3.12/LangChain Core 1.6.6/ChatGroq 1.1.3 APIs
were checked. Final live synthetic samples passed missing-recipient clarification
without execution, matched FAQ-to-draft dependencies with preserved facts and
application-rendered demo/actions sections, and simple summarization. An earlier
live sentiment-to-keywords chain and FAQ no-match clarification also worked.
Prompt iterations exposed invented `json` tool calls and omission of actions/demo
qualification; invalid calls now fail accurately and draft rendering is owned by
the application. An earlier embedded-command source affected summarization and
led to an irrelevant clarification. The final adversarial inspection retained the
operational facts and described the embedded command without executing it, but
selected that command as summary content. These few samples establish neither
general reliability nor injection resistance. No reminder was created, email
submitted, alternate model tested, or API/UI/deployment integration verified.
