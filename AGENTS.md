# OpsFlow-Agent

An operations copilot using TF-IDF + Logistic Regression for intent routing, LangChain/Groq for conversational tool orchestration, FastAPI, Streamlit, and SQLite reminders.

## Read Before Working

- `docs/PLAN.md`: current scope, architecture, execution checklist, and pending decisions.
- `docs/agents_doc.md`: brief record of completed changes and the next step.
- `skills/karpathy-guidelines/SKILL.md`: follow the supplied Karpathy development guidelines. If missing, ask before development.

## Collaboration and Coding Rules

- Suggest and discuss each implementation step before coding. Explain the problem, proposed change, inputs/outputs, and how we will verify it. Once the user agrees, complete that bounded step without repeatedly requesting permission.
- Take the slow approach throughout this project so the user understands the code. Prefer one small, explainable step at a time. If asked to implement too much at once, remind the user of this agreement and propose a smaller first slice.
- Make each development change a logically scoped commit and PR with a clear purpose and relevant verification. Keep unrelated work separate; preserve existing user changes. Use logical job-based branch and PR names such as `fix/...` or `feature/...`, not `codex/...`. Agree on the slice before implementation and prepare its reviewable diff before publication.
- Do not add `Co-authored-by`, ChatGPT, Codex, or any other non-user author attribution to commits, merge commits, PR descriptions, or PR details. Authorship should remain only the user's GitHub account.
- Before opening or updating a PR, confirm the DCO check will pass for every commit. Use only the user's GitHub account details for any required `Signed-off-by` line.
- State assumptions and ask about material uncertainties before implementing. Do not silently change scope or choose external services.
- Write the simplest code that solves the agreed problem. Avoid speculative features, unnecessary abstractions, unrelated refactoring, and cosmetic changes outside the task.
- Verify behavior appropriate to the change. Report what was checked and what remains unverified; never claim delivery, execution, or testing that did not happen.
- Immediately update `docs/PLAN.md` when decisions, scope, architecture, or status change. Add a brief completed-change entry to `docs/agents_doc.md`. Update this file too if project facts or working rules change. Include those updates in the same logical change.
- Keep the plan and record concise and adaptable. Use ✅ only for verified completed work and ⏳ for the active discussion or step.

## Project Boundaries

- Direct execution requires a high-confidence, single-purpose deterministic request with safely extracted arguments. Sentiment analyzes the supplied text, not the instruction wrapper.
- Reminder requests always go through the agent, regardless of classifier confidence. Compound, uncertain, LLM-dependent, or context-dependent requests also use the agent.
- Version one includes emails to the configured user with separate draft content and action instructions, plus scheduled reminder emails. External-recipient email sending is a separate scope decision.
- A stored reminder requires a due-time delivery worker; a draft or scheduled record must not be reported as a sent email. Track side effects and failures accurately and prevent duplicate delivery.
- Preserve session history for both routes. Display observable tool execution traces and timings without exposing private model reasoning.
- Verify dependency/API/model compatibility before implementation. Keep credentials out of Git and logs; use controlled email test doubles for automated checks.
