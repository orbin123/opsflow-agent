# Project Implementation Plan

## Objective

Build **OpsFlow-Agent**, an explainable operations copilot combining classical ML routing with LangChain tool calling. It should analyze communications, summarize text, retrieve company policies, extract keywords/action items, draft emails, and create reminders with email notifications to the user.

Develop slowly, one discussed and reviewable change at a time. The original three-day sprint is an ordering guide, not a deadline.

## Architecture & Context

Flow: Streamlit → FastAPI → intent router → deterministic tool or LangChain agent → session history + execution trace → response.

- **Dataset/router:** `data/tasks_benchmark.csv` contains 1,000 synthetic requests, exactly 125 per label: `sentiment_analysis`, `keyword_extraction`, `faq_retrieval`, `summarization`, `email_drafting`, `reminder_creation`, `compound_request`, and `out_of_scope`. The CSV has only `text,label` and one header. Eight separate label batches were generated using three reused sub-agents with user approval. Structure and cross-batch similarity were checked; `docs/dataset_validation_report.md` records methods, results, and one rejected/replaced template-like example. No labels were changed. The classifier receives only `text` and predicts `label`. `notebooks/train_evaluate_svm.ipynb` trains a word TF-IDF + sigmoid-calibrated `LinearSVC` against a deterministic stratified 80/20 development/test split and saves the evaluated pipeline under `artifacts/models/`. The selected unigram model achieved 0.8813 test macro F1. A 0.71 threshold selected from development-set out-of-fold predictions achieved 1.0 direct-route precision at 0.235 coverage on the untouched test set, with no reminder or compound request routed directly. These synthetic holdout results do not establish real-world performance or calibration. Route/tool metadata remains outside the CSV.
- **Direct path:** Only clearly single-purpose, self-contained deterministic requests qualify: sentiment, keyword extraction, and FAQ lookup. Extract the payload before tool execution. For `get the sentiment for this text "I am sad"`, analyze `I am sad`, not the surrounding instruction. Uncertain argument extraction falls back to the agent.
- **Agent path:** All reminder requests, compound requests, LLM-based summarization/email drafting, low-confidence requests, and context-dependent follow-ups use LangChain + ChatGroq. A reminder can retain the `reminder_creation` label while still requiring multiple execution steps; intent label and execution route are separate decisions.
- **Compound example:** “Analyze this complaint, find the SLA policy, draft an apology, and remind me tomorrow at 9 AM” runs the necessary tools in dependency order. Pass earlier results into later tools, record each outcome, and report partial failures accurately.
- **Tools:** `summarize_text`, `analyze_sentiment`, `draft_email`, `retrieve_faq`, `extract_keywords`, and `schedule_reminder` use validated arguments. Sentiment/FAQ/keywords are deterministic; summarization and email composition may use the LLM. Reminder storage and email delivery are deterministic side effects even though reminder orchestration uses the agent.
- **Agreed first tool slice:** English sentiment using local `vaderSentiment==3.3.2`, standard compound thresholds (+/-0.05), and structured label/scores. Direct extraction accepts a recognized sentiment instruction with one straight or curly double-quoted payload; unsupported formats, ambiguous boundaries, and outside actions defer to the agent. The sentiment route helper accepts upstream intent/confidence and an explicit threshold (saved model: 0.71); model/API/agent wiring comes later. English input is a caller precondition; language detection and translation are not included.
- **Email notifications in v1:** Send notifications to the configured user's own email address. Separate **Email draft** (recipient, subject, body) from **What you should do** (next steps). The user handles forwarding/sending the draft to its intended recipient. Add a delivery utility/tool with observable success/failure; generating a draft alone does not mean notification delivery succeeded.
- **Reminders in v1:** Resolve task, due time, and timezone through the agent; clarify missing or ambiguous details. Store reminders in SQLite. A background worker checks due records and emails the user when due. Persist delivery state to avoid duplicate notifications on retries/restarts. Agree on sender/provider, recipient configuration, and retry behavior before implementing delivery.
- **Memory:** Per-session `ChatMessageHistory` + `RunnableWithMessageHistory` preserve both direct and agent turns. Follow-ups such as “make that more formal” use prior context; ask when the reference is ambiguous. In-memory history resets on restart; reminders persist.
- **API/UI:** `/api/v1/chat`, `/api/v1/classify`, `/api/v1/reminders`, and `/health`. Chat returns reply, predicted intent/confidence, selected route, tool trace, and timing. Streamlit displays chat beside actual tool names, arguments, observations, and latency; the trace explains execution, not private model reasoning.
- **Development baseline:** Python 3.12.13 with a repository-local `.venv`. Direct FastAPI development dependencies are pinned in `requirements.txt`; add the remaining planned stack only with the implementation slice that uses it.
- **Operations:** Structured JSON logs and Prometheus `/metrics` capture request/tool latency and failures without logging credentials or full sensitive messages. Docker Compose runs backend, Streamlit, and reminder worker with shared persistent reminder storage. Choose deployment after local behavior is verified.

Exact dependency versions and available Groq models will be verified at implementation time. Audio/file inputs and production-scale memory are later work unless explicitly agreed.

## Execution Checklist

Status: ✅ completed; ⏳ current discussion/next step; empty = pending. Each implementation item can be split into smaller commits/PRs.

- [✅] Agree on hybrid routing, reminder agent routing, and user email notifications in the first version.
- [✅] Create the plan, brief change record, and root agent instructions.
- [✅] Decide to use CSV with `text,label` fields for classifier training rather than JSON.
- [✅] Generate and validate the 1,000-row, eight-label CSV; reviewed all rows, checked all 499,500 pairs for similarity, and documented the single replacement and review limitations.
- [✅] Initialize a minimal FastAPI foundation with a pinned Python 3.12 development environment and verified health endpoint.
- [✅] Review the dataset/report with the user and agree on a deterministic stratified 80/20 development/test split before training. Company-specific FAQ grounding remains part of the later FAQ-tool discussion.
- [✅] Train/save the calibrated linear-SVM router; evaluate per-label accuracy, confidence calibration, and direct-route precision, including compound requests and reminders.
- [⏳] Implement deterministic sentiment, keyword, and FAQ tools in separate small changes; verify payload extraction and fallback behavior.
- [✅] Implement local English sentiment scoring and conservative quoted-payload extraction with a confidence/intent gate; 53 tests pass including fallback non-execution. Model/API/agent integration remains pending.
- [⏳] Discuss the keyword-tool slice next; agree on company-specific FAQ grounding before the FAQ implementation.
- [ ] Implement and verify LLM summarization and email drafting with structured outputs.
- [ ] Agree on email/timezone settings; implement notification delivery with separated draft and instructions, testing success and failure without emailing real users in automated tests.
- [ ] Implement reminder persistence and due-time email worker; verify timezone handling, restart recovery, and duplicate prevention.
- [ ] Build the LangChain agent loop with tool dependencies, bounded execution, accurate traces, and partial-failure handling.
- [ ] Add session memory across both routes; verify follow-ups and session isolation.
- [ ] Add FastAPI endpoints, structured logs, and metrics; verify request validation and reported failures.
- [ ] Build the Streamlit chat/inspector; verify intent, route, outputs, and step timings against backend results.
- [ ] Add Docker/Compose, persistent storage, and README; verify the complete complaint → policy → draft → notification → due reminder flow.
- [ ] Discuss hosting, deploy the agreed setup, and verify persistence and email delivery there.

Update this file immediately when scope, architecture, order, or completion status changes. Record the brief reason in `docs/agents_doc.md`.
