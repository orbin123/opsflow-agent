# Project Implementation Plan

## Active Agenda — resumed 2026-10-09

The user closed the rework agenda and resumed this plan for remaining project work.
Choose each next bounded slice here, discuss its contract and verification before
coding, and record outcomes in this file and `docs/agents_doc.md`. No additional
implementation is authorized by this handover.

### Current implementation baseline

This baseline supersedes older pending-integration statements and historical
slice descriptions below; those descriptions retain their original verification
limits and are not instructions to repeat completed work.

- Natural-language sentiment, keyword and FAQ workflows are integrated behind
  the classifier, with retained results and grounded presentation. Uncertain,
  contextual and compound requests use the agent.
- Durable SQLite chats, catalogue APIs, Rename/Delete, URL restoration, SSE live
  Activity and saved execution details are implemented. Settings provides Docs,
  saved Emails and read-only Reminders pages.
- Chat supports one-time reminder creation through the agent with turn-owned
  deduplication. The due-time delivery worker remains a separate process; chat
  never starts it. Drafting does not send email, and SMTP acceptance does not
  establish inbox arrival.
- Merged PR #48 adds the persistent fictional Sachin Tendulkar profile (EMP-001)
  and singleton workspace association for chats, saved drafts and reminders.
  Profile display, agent personalization and durable composer/last-selection
  restoration remain separately discussed future slices.
- Latest application verification: 1,161 tests pass, dependency/whitespace checks
  pass, and isolated local restart/refresh review preserves profile/chat/reminder
  records. Live SMTP/inbox, deployment and general model reliability remain
  unverified. See feature documentation and `docs/audit.md` for recorded limits.

### Remaining work

The remaining checklist covers observability/remaining endpoints, packaging,
README and deployment discussion, with complete notification/reminder delivery
verification still outstanding. Reconcile each proposed slice against the current
code before implementation. Employee workspace follow-ups require separate
agreement; the resumed plan does not make them the automatic next step.

### ✅ Monitoring and logging — implemented and reviewed, 2026-10-09

- **Decision:** User requested explicit API logging, error logging, request tracking,
  response time, API usage, error rates and task distribution, and selected local
  Prometheus + Grafana. The existing Operations note anticipated logs/metrics but
  did not define their implementation. User approved the bounded contract and
  verification on 2026-10-09; implementation and review are complete on
  `feature/monitoring-logging`, with the verification limits below.
- **Contract:** Sanitized structured JSON request/error logs with generated request
  IDs returned in response headers and correlated through backend execution.
  Record method, route template, HTTP status, duration and stable failure codes;
  exclude message bodies, drafts, tool arguments/results, credentials and raw
  exception text. Request IDs belong in logs, never metric labels.
- **Metrics:** Expose Prometheus `/metrics`; measure request counts/duration by
  bounded method/route/status labels, and actual newly executed tasks by intent,
  execution route and outcome, with execution duration and tool latency/failures.
  Separate HTTP errors from task failures: SSE HTTP 200 does not establish task
  success. Define response duration for streams explicitly; disconnected backend
  execution still reaches its own terminal metric. Catalogue reads, saved replay
  and recovery do not increment task/tool execution counts. Unsaved and unknown
  outcomes remain explicit rather than being reported as successful persistence.
- **Local stack:** Propose a monitoring-only Compose configuration with pinned
  compatible Prometheus/Grafana images, local persistent metrics/dashboard storage,
  and provisioned Prometheus data source/dashboard. Panels cover usage, latency,
  HTTP/task error rates, intent/route distribution and tool behavior. Browser
  control configures/verifies Grafana; the operational connection is backend
  metrics → Prometheus → Grafana. No cloud telemetry destination chosen.
- **Verification proposal:** Proportional offline tests for success, validation,
  server/task errors, sanitized log fields and bounded labels, request-ID
  correlation, SSE disconnect completion and replay without double counting.
  Run existing suite/dependency/whitespace checks, verify actual Prometheus
  scraping and Grafana panels, then exercise the changed chat flow in the inline
  browser and leave it open for user review before merge/direct main push.
  Provider/email test doubles prevent real sending during automated checks.
- **Implementation/verification:** API middleware, correlated runtime/tool and
  persistence logs, bounded metrics and preinitialized aggregate error counters
  are implemented. Monitoring-only Compose pins Prometheus 3.15.0 and Grafana
  13.2.2, with local volumes and a provisioned 12-panel dashboard. Browser review
  corrected distribution axes/table labels and a supported 30-second refresh.
  All 15 new tests pass; final monitoring/SSE checks pass (31 tests), along with
  dependency/whitespace and Prometheus configuration checks. Default full suite:
  1,172 passed/four existing 3-second AppTest timeouts. An uncommitted harness
  using 15-second AppTest allowance passed 1,175; its one fresh-process timeout
  passed separately in 10.76 seconds. No single default full-suite green run is
  claimed; assertions and repository test timeouts remain unchanged.
- **Live evidence:** Docker Desktop services run on localhost 9090/3000. Chrome
  verifies Grafana panels and supported auto-refresh; all 12 PromQL queries
  succeed. Isolated backend/UI on 8012/8502 use separate SQLite files and a local
  Prometheus config override; original 8011/8501 processes remain available.
  Synthetic sentiment completed/saved; a second turn was classified compound,
  used the agent and retained a successful sentiment tool before final model
  `invalid_output`/partial failure. Logs distinguish this from SSE HTTP 200.
  Refresh did not recount work. After the aggregate-counter fix/restart, saved
  restoration left counters at zero; one explicitly new synthetic turn produced
  exactly one completed task/tool/persistence count. No reminder worker or email
  sending ran. Existing model-output reliability limits remain separate.
- **Review boundary:** Inline browser creation/attachment failed; Chrome review
  succeeded and the live dashboard/chat remain open. See `docs/monitoring.md`.
  User approved review and merge of [PR #49](https://github.com/orbin123/opsflow-agent/pull/49)
  on 2026-10-09; its commit carries the user's DCO sign-off. Alerting, Loki ingestion,
  distributed tracing, worker telemetry, cloud export and full deployment remain
  separate scopes. Metrics reset on backend restart; Prometheus retains scraped
  history, and logs are content-free stderr records without durable ingestion.


### ✅ Dockerization and hosting — protected temporary demo, 2026-10-09

- **Latest decision:** User reversed the persistence requirement and approved a
  protected temporary Render Free demo: one container with Streamlit and a
  loopback-only single-process API behind a password-protected nginx proxy.
  Cloud records are disposable; local records/SMTP credentials are excluded and
  no reminder worker runs. Add an explicit temporary-demo UI notice. Docker
  packaging, runtime supervision and free deployment are authorized. Verify Linux
  build/dependencies, password protection (including WebSockets), chat/SSE and
  saved replay, child-failure/shutdown handling, and container-backed browser flow
  before publication. Use Render's repository Docker builder to avoid a separate
  registry upload. CLI 2.28.0 is installed and authenticated; implementation is
  active. GitHub connection now permits the private repository build. Created
  `srv-db4gtd3tqb8s73f7mrrg` on Free in Singapore with automatic deploys disabled;
  hosted build is live at https://opsflow-temporary-demo.onrender.com.
  Paid hosting remains separate; PR #50 remains draft and main is unmerged.
- **Free shutdown limit:** Actual Blueprint validation rejects custom shutdown
  delays on Free services. Keep the platform's default 30-second window and record
  that longer in-flight turns can be interrupted; recovery never resubmits them.
- **Verification so far:** Focused demo/UI/stream/persistence/monitoring set:
  153 passed; full local suite: 1,190 passed with the existing LangChain history
  deprecation warning. Local dependency and whitespace checks pass. Linux image
  build and live access/browser checks remain in progress; no deployment claimed.
- **Container evidence:** Native Linux ARM64 build/dependency check succeeds;
  local emulated AMD64 download was cancelled and that architecture will be built
  on Render. Live HTTP/WebSocket checks reject missing/wrong credentials, allow
  authenticated UI and keep API/metrics paths inaccessible. Missing-password
  startup fails; an exited API child stops the service with exit 1 and no OOM.
  Corrected nginx's unprivileged temporary paths and verified proxy readiness
  before reporting startup. Idle runtime uses about 220 MiB within a 512 MiB cap.
  Initial Linux focused run: 150 passed, two 3-second AppTest timeouts and one
  existing no-warning assertion affected by the image's demo flag. Normal-UI
  rerun: 14 passed, one remaining timeout; that remaining assertion passes in a
  temporary 15-second harness without changing repository test timeouts. No
  single default Linux focused-suite green run is claimed.
  Inline browser verifies the explicit demo notice, a live sentiment workflow
  completed/saved with Activity, and refresh restoration with exactly one task
  execution. After-chat memory is about 382 MiB within the 512 MiB cap. Hosted
  Intel build succeeds on Render. Hosted HTTP/WebSocket checks pass with
  password rejection and hidden backend paths. Browser verifies classifier,
  live Groq-assisted sentiment and agent summarization with completed tools
  and saved Activity. Refresh restores both answers with only the same two
  task executions in hosted logs. Cloud data remains temporary; reminder emails
  are disabled. Hosted demo remains open for user review.
- **Earlier planning request:** Plan Docker packaging with Render for FastAPI and Streamlit
  Community Cloud for the UI, and compare alternatives. Planning is authorized;
  application/container implementation, paid provisioning and deployment await
  agreement on a bounded slice. Assume “Streamlit deploy” means Community Cloud.
- **Durable-hosting option (outside the approved temporary demo):** Paid, single-instance Render Docker
  web service with a persistent disk, plus GitHub-based Streamlit Community Cloud
  UI. Community Cloud manages its own runtime; our UI Docker image would support
  local verification and alternative hosts, not be deployed there. Keep the
  singleton fictional workspace; this does not introduce multiple users.
- **Current constraints:** One Uvicorn process owns the chat SQLite lock. Store
  both databases under a mounted path (proposed `/var/data`), selected through
  `OPSFLOW_CHATS_DB` and `OPSFLOW_REMINDERS_DB`. Only the reminder database is
  shared with the separately started worker. No replicas, network filesystem or
  automatic execution/retries during restoration. Preserve model artifacts,
  FAQ JSON, UI assets and the Docs guide. Streamlit imports backend schemas and
  modules today; a minimal UI dependency list needs import/build verification,
  not merely deleting backend packages from requirements.
- **Hosting constraints verified in official docs:** Render Free loses local
  SQLite files across restarts/redeploys, idles after 15 minutes and blocks SMTP
  ports including the existing Gmail port 465. Render disks belong to only one
  service instance, cannot be shared with a separate worker service, prevent
  horizontal scaling and require deployment downtime. Community Cloud deploys
  source/dependencies from GitHub and hibernates after 12 hours without traffic.
  A sleeping UI need not stop an independently running backend/worker, but
  browser-session drafts are not durable across UI process loss.
- **Worker decision:** For Render with current SQLite, propose explicitly
  starting one API process and one worker process under a tested process
  supervisor in the same service/container, sharing the disk. Chat must never
  launch the worker. Define worker failure visibility, termination propagation,
  shutdown draining and exclusive ownership before implementing this later slice.
  A separate Render worker plus shared SQLite disk is not supported. Postgres
  would permit a separate worker, but requires a separately agreed redesign of
  persistence, locks, recovery and delivery claims; it is not a Docker change.
- **Public access boundary:** Current docs explicitly prohibit exposing the
  unauthenticated backend publicly. Before hosted access, discuss a minimal
  configured service token on data/execution/metrics endpoints and server-side
  UI requests, with secret-safe errors/logs and negative tests. A private UI
  does not protect a separately public API. Public demo viewers would still
  share the same workspace and configured reminder recipient; decide private
  access versus intentional public demo behavior before enabling delivery.
- **Alternatives:** Hosting UI on Render as another Docker web service gives
  uniform deployment and a possible private API network path, at additional
  service cost; it does not solve separate-worker disk sharing. A single Linux
  VPS with Compose best preserves separate API/UI/worker containers and shared
  local reminder storage, but requires patching, TLS, backups and monitoring
  operations. Separate managed services with Postgres are a future scaling
  option, not the first packaging slice. No exact cost or instance sizing is
  promised before memory/build measurements and budget discussion.
- **Proposed sequence (each separately agreed):**
  1. Local Docker foundation: compatible pinned Python 3.12 Linux base, scoped
     dependency packaging, backend/worker and UI build targets, `.dockerignore`,
     and application Compose. One backend process, separate UI service and an
     opt-in worker profile; persistent local volumes and runtime-only secrets.
     Bind API to `0.0.0.0` and a configurable port; local UI uses the Compose
     API hostname. Keep monitoring Compose separate/optional. Exclude credentials,
     local databases, notebooks/test tooling and caches from runtime images;
     verify files needed by imports and the UI Docs page before excluding them.
  2. Hosted access boundary: agree token/access behavior, then implement and
     verify HTTP plus SSE protection without automatic resubmission.
  3. Selected hosting configuration: Render Docker blueprint/disk/environment,
     Community Cloud source/dependencies/Python 3.12/API URL, and explicit
     same-service worker supervision if selected. Configure shutdown allowance
     against the soft 120-second turn budget and SMTP operation bounds. Existing
     `/health` is liveness only; add or explicitly verify storage readiness.
     Define SQLite-consistent backup/restore and schema-aware rollback steps.
  4. Deployment review: hosted SSE progress/finalization, disconnect/read-only
     recovery, restart persistence, authentication, and worker delivery behavior.
     Use synthetic data; real SMTP/inbox testing requires explicit authorization.
     Keep cloud monitoring/export separate from the existing local dashboard.
- **Proposed first-slice verification:** Linux image builds and dependency checks;
  existing relevant chat/SSE/persistence/worker regression tests in Linux;
  container health/catalogue and deterministic local-tool smoke checks; restart
  retention and replay without new execution; second-process lock exclusion;
  graceful stop/disconnected completion and forced-stop interrupted recovery.
  Worker checks use isolated records and a controlled transport double, never
  real SMTP. Exercise container-backed Streamlit in the inline browser and leave
  it open for user review. Run broader existing checks as required and report
  timing/availability limits honestly. No new tests merely for static Docker text.
- **Sources checked 2026-10-09:** [Render Docker](https://render.com/docs/docker),
  [Free limits](https://render.com/docs/free),
  [disk limitations](https://render.com/docs/disks),
  [shutdown](https://render.com/docs/deploys),
  [Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
  [dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
  [hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app),
  [Compose in production](https://docs.docker.com/compose/how-tos/production/).
- **Earlier planning verification:** Reviewed current API/UI imports, persistence locks,
  worker/storage/SMTP contracts, dependency pins and hosted platform docs. No
  image build, runtime test, provider/email execution or deployment performed.

## Objective

Build **OpsFlow-Agent**, an explainable operations copilot combining classical ML routing with LangChain tool calling. It should analyze communications, summarize text, retrieve company policies, extract keywords/action items, draft emails, and create reminders with email notifications to the user.

Develop slowly, one discussed and reviewable change at a time. The original three-day sprint is an ordering guide, not a deadline.

Agree on test scope before coding each slice. Keep coverage proportional to behavior and risk, use representative equivalent inputs, and justify exhaustive cases that protect a real contract.

## Architecture & Context

Flow: Streamlit → FastAPI → intent router → deterministic tool or LangChain agent → session history + execution trace → response.

- **Dataset/router:** `data/tasks_benchmark.csv` contains 1,000 synthetic requests, exactly 125 per label: `sentiment_analysis`, `keyword_extraction`, `faq_retrieval`, `summarization`, `email_drafting`, `reminder_creation`, `compound_request`, and `out_of_scope`. The CSV has only `text,label` and one header. Eight separate label batches were generated using three reused sub-agents with user approval. Structure and cross-batch similarity were checked; `docs/dataset_validation_report.md` records methods, results, and one rejected/replaced template-like example. No labels were changed. The classifier receives only `text` and predicts `label`. `notebooks/train_evaluate_svm.ipynb` trains a word TF-IDF + sigmoid-calibrated `LinearSVC` against a deterministic stratified 80/20 development/test split and saves the evaluated pipeline under `artifacts/models/`. The selected unigram model achieved 0.8813 test macro F1. A 0.71 threshold selected from development-set out-of-fold predictions achieved 1.0 direct-route precision at 0.235 coverage on the untouched test set, with no reminder or compound request routed directly. These synthetic holdout results do not establish real-world performance or calibration. Route/tool metadata remains outside the CSV.
- **Shared runtime:** `app/runtime.py` classifies a validated message once and dispatches sentiment, keyword or FAQ execution through conservative gates. Deferred requests invoke the stateless five-tool agent once with the original message, retaining its reply, status, failure reason and actual traces; direct failures stop without agent retry. Total timing includes classification and handoff. FAQ-only mode preserves the existing endpoint contract without invoking the agent. The separate `app/sessions.py` entry point adds shared process-local conversation history across both routes and explicit clearing. All 631 tests pass, including offline history/loop integration, isolation and failure checks. No reminder creation or email submission in this path. See `docs/runtime.md`.
- **Code organization:** `app/routes/` contains execution-routing helpers (`keyword_route.py`, `sentiment_route.py`, and `faq_route.py`); `app/tools/` contains the underlying NLP tools. HTTP endpoint modules live separately in `app/api/`.
- **Direct path:** Only clearly single-purpose, self-contained deterministic requests qualify: sentiment, keyword extraction, and FAQ lookup. Extract the payload before tool execution. For `get the sentiment for this text "I am sad"`, analyze `I am sad`, not the surrounding instruction. Uncertain argument extraction falls back to the agent.
- **Agent path:** All reminder requests, compound requests, LLM-based summarization/email drafting, low-confidence requests, and context-dependent follow-ups use LangChain + ChatGroq. A reminder can retain the `reminder_creation` label while still requiring multiple execution steps; intent label and execution route are separate decisions.
- **Compound example:** “Analyze this complaint, find the SLA policy, draft an apology, and remind me tomorrow at 9 AM” runs the necessary tools in dependency order. Pass earlier results into later tools, record each outcome, and report partial failures accurately.
- **Tools:** `summarize_text`, `analyze_sentiment`, `draft_email`, `retrieve_faq`, `extract_keywords`, and `schedule_reminder` use validated arguments. Sentiment/FAQ/keywords are deterministic; summarization and email composition may use the LLM. Reminder storage and email delivery are deterministic side effects even though reminder orchestration uses the agent.
- **Agreed first tool slice:** English sentiment using local `vaderSentiment==3.3.2`, standard compound thresholds (+/-0.05), and structured label/scores. Direct extraction accepts a recognized sentiment instruction with one straight or curly double-quoted payload; unsupported formats, ambiguous boundaries, and outside actions defer to the agent. The sentiment route helper accepts upstream intent/confidence and an explicit threshold (saved model: 0.71); model/API/agent wiring comes later. English input is a caller precondition; language detection and translation are not included.
- **Verified keyword slice:** Local English `yake==0.7.3` extraction returns up to five ranked terms/phrases of one to three words with raw relevance scores (lower is better, not confidence). Follow the sentiment tool's conservative quoted-payload and intent/confidence gate. Verified dependency compatibility, relevant example phrases, empty inputs, repeatability without network connections, and fallback non-execution. Nonblank text without candidates returns an empty list; blank input is rejected. Example checks do not establish real-world extraction quality. Model/API/agent wiring remains later work.
- **Verified FAQ slice:** 25 fictional employee FAQs in `data/company_faq.json`, explicitly labeled demo policies, with policy IDs, categories, questions, alternate phrasings, and stored answers. `app/tools/faq.py` retrieves with local TF-IDF/cosine similarity using the existing scikit-learn dependency. Return an exact stored answer for a clear match, candidate questions for ambiguity, or `no_match`. Scores are lexical similarity, not probabilities. All 208 tests pass, covering all 75 stored phrasings, example paraphrases, unrelated/ambiguous questions, empty inputs, and offline repeatability. Matching uses the best phrasing score per policy, a 0.60 answer threshold, a 0.12 lead over the next policy, a 0.40 candidate threshold, and 60% query vocabulary coverage. These heuristics were adjusted using development examples, not independently calibrated. Lexical matching can miss valid paraphrases or misinterpret shared words; it does not establish policy applicability. Restart the process after JSON edits to reload the cached index. FAQ routing/API integration is implemented below; shared chat/agent integration remains pending.
- **Email notifications in v1:** Send notifications to the configured user's own email address. Separate **Email draft** (recipient, subject, body) from **What you should do** (next steps). The user handles forwarding/sending the draft to its intended recipient. Add a delivery utility/tool with observable success/failure; generating a draft alone does not mean notification delivery succeeded.
- **Reminders in v1:** Resolve task, due time, and timezone through the agent; clarify missing or ambiguous details. Store reminders in SQLite. A background worker checks due records and emails the user when due. Persist delivery state to avoid duplicate notifications on retries/restarts. Agree on sender/provider, recipient configuration, and retry behavior before implementing delivery.
- **Memory:** `app/sessions.py` uses per-session `InMemoryChatMessageHistory` + `RunnableWithMessageHistory` to preserve user turns and structured execution records from both routes. Agent follow-ups receive prior context and are prompted to clarify ambiguous references; model correctness is not guaranteed. Turns/clearing serialize per session. History resets on restart and has no automatic eviction/truncation; reminders persist separately. Both history APIs are deprecated in pinned LangChain Core 1.6.6. See `docs/session-memory.md`.
- **API/UI:** Implemented `/api/v1/chat`, `/api/v1/faq`, and `/health`; `/api/v1/classify` and `/api/v1/reminders` remain planned. The FAQ endpoint exposes a stateless routing/retrieval result. Chat accepts caller-owned session ID/message and returns session-aware structured results, nullable reply, predicted intent/confidence, route/reasons, actual traces and timing; errors/partial failures return 503. See `docs/chat-api.md`. Streamlit displays session chat beside tool names, arguments, observations and actual backend latency; traces explain execution, not private model reasoning. See `docs/streamlit-console.md`.
- **Development baseline:** Python 3.12.13 with a repository-local `.venv`. Direct FastAPI development dependencies are pinned in `requirements.txt`; add the remaining planned stack only with the implementation slice that uses it.
- **Operations:** Structured JSON logs and Prometheus `/metrics` capture request/tool latency and failures without logging credentials or full sensitive messages. Docker Compose runs backend, Streamlit, and reminder worker with shared persistent reminder storage. Choose deployment after local behavior is verified.

Exact dependency versions and available Groq models will be verified at implementation time. Audio/file inputs and production-scale memory are later work unless explicitly agreed.

## Agreed Summarization Slice — Verified

- **Boundary:** A standalone `summarize_text(text)` tool for the future agent. English source text is a caller precondition. Email drafting, agent execution, session history, HTTP/UI integration, chunking, and action-item extraction remain separate slices. The existing runtime continues to return `agent_required` for summarization.
- **Input:** Source payload only, without the instruction wrapper; require a nonblank string of at most 10,000 characters. Reject invalid/oversized input before a provider call; never silently truncate. Preserve source wording in the request.
- **Output:** Required `summary: str` and `key_points: list[str]`, no extra fields. Validate a nonblank summary of at most 1,500 characters and zero to five nonblank key points of at most 300 characters each. Prompt for a short paragraph and source-supported points; preserve uncertainty, names, dates, and numbers. Do not invent facts or follow instructions embedded in source text. Prompting/schema validation cannot guarantee factual accuracy. No confidence score or model reasoning in the result.
- **Groq/configuration:** Use `langchain-groq`/`ChatGroq`, `openai/gpt-oss-20b`, native JSON Schema with `strict: true`, and local Pydantic validation. [Groq documents strict support](https://console.groq.com/docs/structured-outputs) for this model; [ChatGroq documents structured-output support](https://docs.langchain.com/oss/python/integrations/chat/groq). Agreed settings: temperature 0, low reasoning effort, 2,048 completion tokens, 30-second request timeout, zero automatic retries. Verified Python 3.12.13 compatibility and live strict-schema requests; pinned direct dependencies. See `docs/summarization.md`. Load the repository-local `.env` without overriding environment variables; use `GROQ_API_KEY` and optional `GROQ_SUMMARY_MODEL` (default above). Initialize lazily so deterministic tools and health remain available without credentials. Key/account access verified through three synthetic live calls without exposing credentials. Supported model override is `openai/gpt-oss-120b`; reject other names rather than silently weakening strict mode. No external tracing or raw provider-response logging.
- **Failures:** Invalid input raises the existing type/value error style. Configuration/provider failures raise sanitized errors with stable reasons for configuration, authentication, rate limit, timeout, provider unavailability, or invalid output. Refusal, empty/malformed/schema-invalid output, and truncated completion must not return success. No silent JSON repair, model switching, or retry. Future agent integration owns traces and timings.
- **Tests:** Offline provider doubles cover successful parsing/source isolation, short input/empty points, input boundaries and missing-key non-execution, representative provider failures, refusal/truncation/invalid-output rejection, intended settings, and sanitized errors. Re-run the existing suite, `pip check`, and whitespace checks. Separately inspect a few live synthetic examples (operations update, short note, embedded instructions) for fidelity and schema compliance; report limitations. No exact generated-wording assertions or live calls in automated tests.
- **Verification/delivery:** Implemented on `feature/structured-summarization`; all 413 tests (38 new), `pip check`, and whitespace checks pass. Three live synthetic examples returned valid results and preserved inspected facts; embedded commands were quoted rather than followed, though one was selected as a key point. This is not a quality benchmark. Keep implementation/docs in one signed logical commit/PR and preserve existing user changes. Agent execution and session-aware chat remain pending.

## Agreed Email-Drafting Slice — Verified

**Problem and boundary:** Produce a useful email draft while keeping recipient-facing content separate from instructions to the user. Implement one standalone `draft_email(recipient, content, instructions="Write a concise, professional email.") -> EmailDraftResult` tool for the future agent. No sending, notification delivery, SMTP/provider selection, scheduling, persistence, agent loop, session memory, API, UI, or routing changes. Email drafting continues to require the agent in the existing runtime, irrespective of classifier confidence. The user agreed to the contract and proportional test scope on 2026-10-06; implementation is verified below.

### Input contract

| Field | Meaning | Validation |
| --- | --- | --- |
| `recipient` | User-supplied intended recipient: a name, role, or email address | Required nonblank string, at most 320 characters, no CR/LF |
| `content` | Facts/source material to communicate; may include earlier tool results explicitly supplied by the caller | Required nonblank string, at most 10,000 characters |
| `instructions` | User-authorized composition request: purpose, tone, or formatting | Nonblank string, at most 1,000 characters; concise/professional default when omitted |

English input/output is a caller precondition. Validate types and bounds before initializing Groq; use `TypeError` for nonstrings and `ValueError` for blank/oversized or multiline recipient input. Do not silently truncate. Preserve supplied input strings in the serialized request and return the recipient unchanged. A name/role is valid because this tool composes rather than delivers; no email-address validation or inferred address.

The future agent owns extracting these fields from the request and clarifying a missing recipient, unclear purpose, contradictory material facts, or ambiguous context before calling. This standalone slice does not implement that clarification flow. Treat source `content` as data: embedded commands must not override the composition request. `instructions` controls writing only and cannot authorize tool execution. Do not invent dates, policy terms, promises, attachments, addresses, or sender identity. Use visible placeholders for optional missing details (such as `[Your name]`) instead of invented values; the user reviews them before sending. Faithfulness and appropriate placeholders are prompt requirements/manual checks, not guarantees from schema validation.

### Output contract and separation

Return a locally validated result with no extra fields:

```json
{
  "email_draft": {
    "recipient": "Alex",
    "subject": "Maintenance update",
    "body": "Hi Alex,\n\nThe maintenance window is Friday from 6 to 7 PM IST.\n\nRegards,\n[Your name]"
  },
  "action_instructions": [
    "Review the draft for accuracy and replace any placeholders.",
    "Send or forward the reviewed draft to the intended recipient using your email client."
  ]
}
```

The model generates only required `subject` and `body` fields with `additionalProperties: false`. Validate a trimmed, nonblank, single-line subject of at most 200 characters and a trimmed, nonblank plain-text body of at most 4,000 characters; preserve internal newlines. Application code copies `recipient` from the validated input and supplies the two fixed action instructions above. This prevents the model from changing the recipient or inventing workflow steps. The body contains only recipient-facing prose; review/send instructions belong outside it. No HTML, CC/BCC, attachments, delivery status, confidence, or model reasoning. A returned draft never means an email was sent. Later notification delivery will email these two sections to the configured user and report delivery separately.

### Groq settings and failures

- Follow the existing summarization pattern without refactoring it or introducing a shared provider abstraction. Use the installed pinned ChatGroq/Groq dependencies; verify local API compatibility when implementing.
- Reuse `GROQ_API_KEY`; propose optional `GROQ_EMAIL_MODEL`, default `openai/gpt-oss-20b`, with only `openai/gpt-oss-120b` as the supported override. Both have documented strict-schema support in [Groq's current documentation](https://console.groq.com/docs/structured-outputs); [LangChain documents ChatGroq](https://docs.langchain.com/oss/python/integrations/chat/groq). A separate setting lets email configuration vary without changing summarization.
- Temperature 0, low reasoning effort, 2,048 completion tokens, 30-second timeout, zero automatic retries. Native JSON Schema with `strict: true`, followed by local Pydantic type/length validation. One nonstreaming call, no model tool execution. Lazy repository-root `.env` loading without overriding environment values; deterministic tools remain available without credentials. Disable external tracing; do not log source content, raw responses, credentials, or private reasoning.
- Propose `EmailDraftingError.reason`: `configuration`, `authentication`, `rate_limit`, `timeout`, `provider_unavailable`, or `invalid_output`, consistent with summarization. Unsupported model/missing key and provider request/schema HTTP 400 map to configuration; connection/server/unexpected integration failures map to provider unavailability. Expose sanitized messages and suppress raw exception chaining.
- Refusal, non-`stop` finish reason (including truncation), empty/nontext content, malformed JSON, missing/extra fields, wrong types, or output-bound violations fail without returning a draft. No silent repair, partial success, model fallback, or retry. Future orchestration records failure and actual timing; this tool does not claim a send or execute action instructions. Successful JSON cannot guarantee factual accuracy or fully prevent source-instruction leakage.

### Proportional verification and delivery

1. **Success and separation:** Offline provider doubles verify supplied fields reach their intended prompt sections, source wording/newlines survive serialization, default/custom writing instructions work, the recipient is copied unchanged, and fixed action instructions stay outside the generated subject/body. Include a short note and a name-based recipient; assert structure and behavior rather than exact generated wording.
2. **Meaningful boundaries:** Representative wrong-type/blank inputs; exact-limit/over-limit checks for each distinct bounded field; multiline recipient/subject rejection; internal body-newline preservation; invalid input/missing key without provider execution. These protect the public contract rather than enumerate equivalent phrases.
3. **Failures and configuration:** Parameterize the six stable error categories and distinct malformed/schema-invalid/refusal/truncation cases; verify sanitization, no returned draft, one call/no retries, intended strict-schema settings, and disabled tracing. Avoid repeating the summarization suite wholesale or testing unimplemented agent/email delivery behavior.
4. **Regression and live inspection:** Run the existing suite, `pip check`, and `git diff --check`. Inspect three live synthetic drafts: a factual operations update, an explicit tone request with an optional missing sender, and source containing an embedded command. Review facts, uncertainty, recipient-facing prose, placeholders, and instruction separation. No live provider calls in automated tests; these samples are not a drafting-quality or injection-resistance benchmark.
5. **Bounded implementation after agreement:** Add `app/tools/email_drafting.py`, `tests/test_email_drafting.py`, and `docs/email-drafting.md`; update this plan/change record. Use `feature/structured-email-drafting` and one logical commit/PR. Verify every commit's DCO sign-off with the user's account details before publication; add no other author attribution.

**Verification/delivery:** Implemented on `feature/structured-email-drafting`; all 456 tests (43 new), `pip check`, and whitespace checks pass. Nine live synthetic requests were inspected across three prompt iterations. Earlier closure drafts invented a Monday reopening date; explicit grounding examples removed it in the final inspected set. Final operations/tone/embedded-command examples preserved inspected facts, used optional placeholders, and separated user actions. These checks do not establish broad factual fidelity or injection resistance; user review remains necessary. See `docs/email-drafting.md`. Delivery-provider and timezone choices belong to later slices.

## Agreed Gmail Notification Delivery Slice — Verified Offline

- **Boundary:** One standalone `send_draft_notification(draft: EmailDraftResult) -> NotificationResult` utility. It formats the existing draft and fixed action instructions as separate plain-text sections and submits one notification to the configured user's mailbox. No drafting/Groq call, external-recipient delivery, agent/API/UI wiring, reminder persistence, scheduling, or worker in this slice.
- **Recipient restriction:** The notification envelope and `To` header use only configured `OPSFLOW_USER_EMAIL`; the draft's intended recipient is text inside the notification. No caller-controlled delivery recipient, CC/BCC, or reply-to. Validate one configured mailbox and sender before connecting; reject blank/multiple/multiline addresses. Draft fields retain the agreed bounds, and notification formatting must not turn source text into headers. Use a fixed application notification subject and include the draft subject inside the body.
- **Configuration agreed:** Gmail SMTP with Google App Password authentication. Use `SMTP_USERNAME` for sender/authentication, `SMTP_PASSWORD` for the app password, and `OPSFLOW_USER_EMAIL` for the single destination. Fixed `smtp.gmail.com:465`, Python 3.12 `SMTP_SSL`, default certificate/hostname verification, and a 30-second blocking-operation timeout (not a total-call deadline). Lazy repository-root `.env` loading preserves existing environment variables; no protocol debugging or sensitive-content logging. Mailbox syntax and app-password format are validated before connection; grouped app-password spaces are removed. No new dependencies or credentials in Git/logs.
- **Result:** Return `status` (`accepted`, `failed`, or `unknown`), optional stable `reason`, and locally generated `message_id`. `accepted` means the transport acknowledged submission, not verified inbox arrival. `failed` means submission was not accepted (configuration/authentication/connection failure or explicit rejection). `unknown` means timeout/disconnection after submission may have begun, so acceptance cannot be determined. Missing/invalid input fails before network use. Do not let a connection-cleanup failure overwrite an already observed acceptance. Provider exception text/content must not escape in results or logs. Stable reasons are `configuration`, `authentication`, `rejected`, `timeout`, and `provider_unavailable`. Invalid draft types raise `TypeError`; invalid/mutated draft fields or nonstandard action instructions raise sanitized `ValueError` before connection. Submission-stage transport errors conservatively return `unknown`; explicit SMTP rejection is `failed`.
- **Retry behavior:** One submission attempt and zero automatic retries in this slice. An uncertain outcome must not be blindly retried; a message ID alone does not guarantee deduplication. Durable attempt tracking, provider-specific idempotency/reconciliation, reminder retry policy, and restart/crash handling need their own persistence/worker discussion. This utility does not claim duplicate prevention across repeated calls.
- **Timezone agreed:** The user confirmed Asia/Kolkata; use `OPSFLOW_TIMEZONE=Asia/Kolkata` as the future reminder default. Explicit request timezones override the default; future reminder storage uses aware UTC due timestamps plus the original IANA zone for display. Ambiguous/nonexistent local times require clarification; never infer from the machine timezone. This drafting-notification utility needs no due time or timezone conversion, so implementation of reminder time resolution remains later work.
- **Proportional tests:** Controlled transport doubles verify (1) both body sections and configured-user-only delivery even when the draft names an external recipient; (2) invalid configuration/input prevents any connection and source/header injection cannot alter envelope recipients; (3) transport settings and acknowledgement-based status; (4) representative authentication, connection, explicit rejection, timeout/disconnect uncertainty, and post-acceptance cleanup failures; (5) one attempt, sanitized errors, and no drafting call. Run the existing suite, dependency checks, and whitespace checks. No automated messages to real mailboxes. A single manual test to the configured user requires explicit authorization for that send and should distinguish acknowledgement from observed arrival.
- **Verification/delivery:** User agreed to the Gmail implementation/test slice. Implemented on `feature/gmail-draft-notifications`, prepared separately from the drafting change; dependency PR #11 was merged first, and the notification PR now targets `main`. All 492 tests (36 new notification cases), `pip check`, and whitespace checks pass. Local configuration format is valid without exposing values; no live SMTP authentication or email submission was performed. See `docs/email-notifications.md`. Next: agree on reminder persistence, due-time resolution/worker, retries, and unknown-outcome handling before implementation.

## Reminder Slices — Persistence and Worker Verified

**Problem:** A saved reminder must survive restarts, become eligible at the correct instant, and report SMTP outcomes accurately. SQLite persistence and Gmail submission cannot form one atomic transaction: a crash after acceptance but before recording it leaves an uncertain outcome. The proposal prioritizes avoiding automatic duplicate submissions; uncertain reminders may require review rather than guaranteed delivery. Message-ID is a trace identifier, not provider deduplication.

**Existing decisions:** Gmail/App Password transport, configured-user-only delivery, and `Asia/Kolkata` as the default are already agreed. Reminders always use the future agent. The user approved both slices, their verification, and merging on 2026-10-06. Both are verified locally as separately signed logical changes. Persistence PR #13 is merged; worker PR #14 now targets `main`.

### Slice 1: Timezone validation and SQLite scheduling

- **Input:** A nonblank task (maximum 1,000 characters), an explicitly resolved local calendar date/time, an IANA timezone (explicit request zone or configured default), and a caller-supplied opaque creation key (maximum 128 characters). No natural-language parsing, agent, API, UI, SMTP, recurrence, editing, or cancellation in this slice. The future agent resolves “tomorrow” against an explicit current instant and clarifies missing/ambiguous details before scheduling.
- **Time contract:** Use Python `zoneinfo`; validate timezone availability, reject nonexistent local times, and require explicit offset/occurrence selection for ambiguous local times. Verify that any supplied offset matches the zone. Reject new reminders due at or before the current instant; overdue reminders already stored remain eligible after downtime. Never use the machine timezone as a fallback. Convert once to UTC and preserve the original IANA zone for display. Validate actual local time through UTC round trips; attaching a zone alone is insufficient validation.
- **Persistence/output:** Store a UUID reminder ID, unique creation key, task, UTC due/creation timestamps, original zone, and `pending` state in a configurable SQLite file outside Git. Return the persisted record as `scheduled`, never `sent`. Repeating the same key and normalized payload returns the existing record; the same key with different payload fails. Distinct keys allow intentional identical reminders. The caller must reuse its key for retries; text matching cannot reliably detect duplicated user intent. Check for an existing identical record before rejecting a retried creation whose due time has since passed.
- **Verification:** Temporary file databases and a controlled clock cover one valid Kolkata conversion, an explicit zone override, invalid/unavailable zone, past-time rejection, representative DST gap/fold handling, close/reopen recovery, identical/conflicting creation retries, and concurrent creation with the same key. Invalid input must leave no record. Run regression tests, dependency checks, and whitespace checks. Check the installed Python/SQLite APIs and timezone data before coding; no new dependency unless that check establishes a need.
- **Review boundary:** Proposed branch `feature/reminder-persistence`. Include usage/contract documentation and plan/change-record updates. Scheduling alone is not the completed reminder feature; delivery remains the next slice.
- **Verified implementation:** `app/tools/reminders.py` now provides structured `schedule_reminder` with UTC storage, preserved IANA zone, confirmed-offset DST handling, unique creation keys, serialized lookup/insertion, and commit-before-success reporting. Default file is `var/reminders.sqlite3`; `OPSFLOW_REMINDERS_DB` or an explicit path overrides it. Python 3.12.13, SQLite 3.53.4, and local Kolkata/New York timezone data were checked; no dependencies added. All 538 tests (46 new reminder cases), `pip check`, and whitespace checks pass. Concurrent creation, fresh-process recovery after the due time, and simulated commit rollback passed. See `docs/reminders.md`. No SMTP submission, worker execution, agent/API/UI integration, or delivery guarantee in this slice.

### Slice 2: Due-time Gmail worker and recovery

- **Execution:** A separate local worker polls due `pending` records every 5 seconds, including overdue records after restart. Acquire exclusive worker ownership before recovering unfinished attempts; a second worker must fail safely. Use a Unix advisory file lock beside the canonical database path on a local filesystem (current macOS and planned Linux setup); Windows/network filesystem support remains outside this local slice. Claim one record and commit its attempt marker before SMTP, then submit outside the database transaction. Use conditional state transitions and durable attempt records containing attempt ID, Message-ID, start/end timestamps, and sanitized outcome/reason. Failure to persist a claim prevents submission. A normal SIGINT/SIGTERM shutdown finishes its current attempt and persists the outcome.
- **Message:** One plain-text reminder email to the configured user containing the task, original-zone due time, and reminder ID; overdue submissions identify the original due time. Reuse the verified Gmail transport behavior with a narrowly scoped adaptation, preserving existing draft-notification behavior. No Groq call or external-recipient input. Acceptance means SMTP acceptance, not inbox arrival.
- **Agreed retry policy:** At most three total attempts, retrying after 1 minute and then 5 minutes only for definite transient pre-submission connection/timeout failures. Authentication, configuration, explicit rejection, TLS validation errors, and unexpected integration errors require intervention and become `failed`. Persist retry eligibility and attempt counts so restarts do not reset the budget. The reminder must never be reported as accepted on these failures.
- **Unknown policy:** An uncertain SMTP result becomes `unknown`, with no automatic retry. On restart, unfinished attempt markers become `unknown` only after exclusive worker ownership establishes that the prior worker is no longer running. Do not reclaim attempts merely because a timeout elapsed. This includes a crash before submission or after acceptance but before its database update: safety can cost delivery. An outcome-write failure stops further processing and preserves the durable attempt marker. Previously recorded `accepted` records are never resubmitted. Manual reconciliation/retry is a later explicit action, not a fabricated success or an automatic reset.
- **Verification:** Controlled transport and clock doubles cover before-due non-execution, due/overdue submission, accepted/failed/unknown outcomes, retry timing/exhaustion across restart, second-worker exclusion, and no resubmission after acceptance. Inject crashes/database failures at claim, submission, and outcome-write boundaries; verify conservative recovery and accurate stored state. Re-run existing notification regressions and the full suite; no real email in automated tests. Live submission requires separate explicit authorization.
- **Review boundary:** Proposed branch `feature/reminder-email-worker`. Agent orchestration, HTTP/UI integration, Docker supervision, and deployment remain their existing later slices. Local polling implies delivery after the due instant, subject to worker uptime and SMTP latency; it does not promise exact-time inbox arrival.
- **Verified implementation:** `app/reminder_worker.py` provides a separate polling process and `--once` mode, exclusive local Unix ownership, committed attempt markers, persisted one/five-minute retry eligibility and three-attempt budget, terminal unknown recovery, and graceful SIGINT/SIGTERM shutdown. Reminder email uses the existing Gmail transport; additive `NotificationResult.retryable` metadata identifies safe pre-submission failures without transport-level retries. All 572 tests (34 new worker cases), `pip check`, and whitespace checks pass. Verified second-process exclusion, actual abrupt process exit, post-acceptance interruption, claim/outcome/recovery write failures, SMTP-stage classification, recipient/message content, and SIGTERM during submission. No dependencies added, real SMTP connection/message, inbox verification, Linux/Docker deployment, manual reconciliation command, or agent/API/UI integration.

**Implementation scope:** Slice 2 contract and proportional verification are agreed. Sources reviewed: [Python zoneinfo](https://docs.python.org/3.12/library/zoneinfo.html), [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [Python smtplib](https://docs.python.org/3.12/library/smtplib.html), [Unix file locks](https://docs.python.org/3.12/library/fcntl.html), and [Python signals](https://docs.python.org/3.12/library/signal.html).

## Execution Checklist

Status: ✅ completed; ⏳ current discussion/next step; empty = pending. Each implementation item can be split into smaller commits/PRs.

- [✅] Agree on hybrid routing, reminder agent routing, and user email notifications in the first version.
- [✅] Create the plan, brief change record, and root agent instructions.
- [✅] Decide to use CSV with `text,label` fields for classifier training rather than JSON.
- [✅] Generate and validate the 1,000-row, eight-label CSV; reviewed all rows, checked all 499,500 pairs for similarity, and documented the single replacement and review limitations.
- [✅] Initialize a minimal FastAPI foundation with a pinned Python 3.12 development environment and verified health endpoint.
- [✅] Review the dataset/report with the user and agree on a deterministic stratified 80/20 development/test split before training. Company-specific FAQ grounding remains part of the later FAQ-tool discussion.
- [✅] Train/save the calibrated linear-SVM router; evaluate per-label accuracy, confidence calibration, and direct-route precision, including compound requests and reminders.
- [✅] Implement deterministic sentiment, keyword, and FAQ tools in separate small changes; verify payload extraction and fallback behavior.
- [✅] Implement local English sentiment scoring and conservative quoted-payload extraction with a confidence/intent gate; 53 tests pass including fallback non-execution. Model/API/agent integration remains pending.
- [✅] Implement local English keyword extraction and conservative quoted-payload routing; all 105 tests pass, including existing sentiment and health checks.
- [✅] Implement the 25-policy demo FAQ dataset and local retrieval tool; all 208 tests pass.
- [✅] Implement FAQ execution routing and `POST /api/v1/faq`: trusted saved classifier with artifact hash check and metadata threshold, stored-question/limited policy-question extraction, result/trace/timing, and explicit `agent_required` fallback. All 347 tests, dependency checks, and diff checks pass. See `docs/faq-api.md` for syntax and response/error contracts.
- [✅] Implement the shared deterministic runtime with one classification, existing tool gates, structured results/traces/timings, and FAQ-only API compatibility; all 375 tests, dependency checks, and diff checks pass.
- [✅] Agree on and implement the standalone structured summarization tool with Groq configuration, sanitized failures, and proportional verification; all 413 tests and three live synthetic checks pass. See `docs/summarization.md`. Agent execution and session-aware chat remain pending.
- [✅] Agree on the standalone email-drafting contract, separated draft/actions, Groq settings, failures, and proportional test scope.
- [✅] Implement and verify standalone structured email drafting; all 456 tests and final live synthetic examples pass inspected checks. See `docs/email-drafting.md` for fidelity limitations.
- [✅] Agree on Gmail/App Password and Asia/Kolkata settings; implement standalone draft-notification submission with separated sections, accurate accepted/failed/unknown results, and offline doubles. All 492 tests pass; live authentication/inbox arrival remain unverified.
- [✅] Agree on and implement structured reminder timezone validation and SQLite persistence; verify creation-key deduplication, DST handling, concurrent creation, commit failures, and restart recovery. All 538 tests pass.
- [✅] Agree on and implement the due-time email worker with durable attempts, bounded definite-failure retries, exclusive recovery, and no automatic resubmission after accepted/unknown outcomes. All 572 tests pass; real SMTP/inbox behavior and deployment remain unverified.
- [✅] Agree on the first bounded standalone LangChain agent-loop slice and proportional verification scope.
- [✅] Implement and verify the standalone five-tool agent loop; all 608 tests pass, with actual traces, bounded execution and retained results on failure. Final synthetic live checks pass inspected behavior; model reliability/injection resistance remain limitations. See `docs/agent-loop.md`.
- [✅] Implement and verify the stateless runtime-to-agent handoff; all 614 tests pass, including direct/FAQ isolation, retained outcomes and total timing.
- [✅] Implement and verify shared process-local session memory; all 631 tests pass, with context, isolation, clearing/concurrency and failure history checked offline.
- [✅] Implement and verify bounded `POST /api/v1/chat` with validated caller-owned session IDs, existing session-runtime results and accurate failure responses; all 652 tests, dependency/whitespace checks and a local direct HTTP smoke pass. Structured logs, metrics and remaining endpoints follow separately.
- [x] Build the Streamlit chat/inspector; verify intent, route, outputs, and step timings against backend results.
  - ✅ Implemented the approved local chat/inspector with stable browser-session ID, one HTTP submission per turn, retained failures and backend output/timing preservation. All 670 tests (18 new), dependency and whitespace checks pass. Adapted documented light terminal styles from Figma Foundations; no live Groq/email or deployment verification. See `docs/streamlit-console.md`.
- [ ] Add Docker/Compose, persistent storage, and README; verify the complete complaint → policy → draft → notification → due reminder flow.
- [ ] Discuss hosting, deploy the agreed setup, and verify persistence and email delivery there.

Update this active checklist and `docs/agents_doc.md` as each agreed slice changes
scope, architecture, status or verification.

## Agreed First Agent-Loop Slice

User approved the standalone stateless five-tool loop on 2026-10-06. Expose sentiment, keywords, FAQ, summary and draft tools using existing ChatGroq APIs; defer routing integration, memory, reminder creation and sending. Validate inputs/calls/final replies locally, execute one tool at a time with prior observations, and stop on failure while preserving completed results. Limits: six orchestration calls, five tool attempts, soft 120-second elapsed budget; existing 30-second provider timeouts and zero retries. Trace actual arguments/results/failures/timings without reasoning or external tracing. Clarification and semantic dependencies remain model decisions. See `docs/agent-loop.md` for the agreed contract and tests. Implementation verification: all 608 tests (36 new), `pip check` and whitespace checks pass. Final live synthetic clarification, FAQ-to-draft and summary samples pass inspected behavior; earlier provider/prose/injection failures and the final embedded-command relevance limitation are documented. Application-rendered drafts retain fixed actions and demo qualification. General model reliability and injection resistance are unproven.

## Agreed Runtime-to-Agent Handoff

User approved this bounded slice on 2026-10-06. `execute_request(message)` keeps
classification and conservative direct gates, then invokes `run_agent` once with
the original validated message whenever routing defers. Direct errors stop without
agent retry. `faq_only=True` preserves the FAQ endpoint contract and never invokes
the agent. No model/dependency changes, memory, chat API/UI, reminder creation or
email submission.

Retain classification, confidence and routing `reason`. Carry agent status,
`reply`, separate `agent_reason` and actual traces unchanged, including partial
failures and successful observations. The existing `result` holds direct tool
output only; agent structured outputs remain in traces. Total runtime timing
includes classification, routing and agent execution. An unexpected agent exception
returns a sanitized error with `agent_unavailable` and no invented observations;
it cannot establish whether an unreturned tool ran. Normal agent failures retain
the agent's existing trace and reason. Traces remain private data, not logs.

Agreed tests cover exactly-once handoff, original-message preservation, no agent
on direct success/failure or FAQ-only requests, clarification/error/partial-failure
propagation, retained observations, total timing and an offline real-loop integration.
Run the existing suite, dependency and whitespace checks before delivery.

Verification: all 614 tests (six new), `pip check` and `git diff --check` pass.
Offline integration uses the real agent loop and sentiment tool with a provider
double. No new live Groq, SMTP/inbox, API/UI or deployment testing.

## Agreed Session-Memory Slice

User approved a separate `execute_session_request(session_id, message)` entry point
on 2026-10-06, plus explicit `clear_session_history(session_id)`. Keep stateless
runtime/agent calls and the FAQ-only API available. In one process, a per-session
lock serializes complete turns and clearing; different sessions can run independently.
Callers own session identity/authorization. Session IDs are exact nonblank strings
up to 128 characters. Validate message input before creating history.

Use installed LangChain Core 1.6.6 `InMemoryChatMessageHistory` and
`RunnableWithMessageHistory` without adding dependencies. Both APIs are deprecated
in this pinned version for removal in 2.0; adopting LangGraph is a future scope decision.
Save each user message and an application-generated assistant JSON execution record
with reply, status and actual structured outcomes. Failed/partial results remain
failures. Sanitized classifier/routing failures are remembered and still raise
`RuntimeUnavailable` to the caller. Invalid input creates no turn. Supply prior
user/assistant messages only to the agent; self-contained direct gates remain unchanged.
Historical demo-policy observations qualify subsequent rendered drafts conservatively,
even if an unrelated draft is requested later in that session.

Disable external tracing around the entire history runnable; never store provider
reasoning/raw orchestration messages. Memory is process-local and resets on restart;
there is no disk persistence, automatic eviction/truncation, token budget or public
history API in this slice. Explicit clearing releases message contents while keeping
the lock to avoid clear/execution races. Long histories can exhaust memory/provider
context; provider errors retain accurate outcomes without silent history truncation.
HTTP/UI, reminder creation and email execution remain separate slices.

Agreed proportional checks: direct-to-agent context, draft revision with fixed actions
and demo qualification, clarification answers, ambiguous references, session isolation,
clearing/concurrency, stateless/FAQ regression and accurate failure history. Use offline
provider doubles, then run the full suite, dependency and whitespace checks. No claim
of model reference-resolution reliability from scripted responses.

Verification: all 631 tests (17 new), `pip check` and whitespace checks pass.
Two expected LangChain history-API deprecation warnings remain visible. Offline
provider doubles exercise the actual loop and session wrapper; no live Groq/email,
HTTP/UI or deployment verification was performed. Runtime handoff PR #16 is merged; the session-memory PR now targets `main`.

## Agreed Session-Chat API Slice

On 2026-10-06 the user requested planning and implementation of one bounded
`POST /api/v1/chat` endpoint. Accept only exact nonblank `session_id` (at most
128 characters) and `message` (at most 10,000 characters), preserving whitespace.
Invoke `execute_session_request` once and return its existing execution fields
plus the session ID. Preserve nullable direct replies, structured direct results,
agent reasons and actual traces, including partial failures; do not invent prose
or execution observations. Use a synchronous handler for the blocking runtime.

HTTP 200 covers completed/clarification outcomes; 422 rejects invalid bodies
before history or execution; 503 covers error/partial-failure outcomes with their
execution payload, or sanitized `RuntimeUnavailable` detail. No automatic retries.
Session identity remains caller-owned and unauthenticated for local single-process
use; no durable/shared memory, new provider, clearing/history endpoint, reminder or
email execution, UI, structured logs or metrics in this slice.

Proportional tests cover direct-result and agent-trace JSON preservation, same-session
follow-up context and isolation through HTTP, request type/blank/length/extra-field
validation before execution, exact-limit preservation, clarification, sanitized
runtime/direct/provider errors and retained partial observations. Use offline
provider doubles and existing session concurrency coverage; run the full suite,
`pip check`, whitespace checks and an offline live-server direct-request smoke check.

Verification: all 652 tests (21 new), `pip check` and whitespace checks pass.
A local Uvicorn HTTP request returned 200 with the real classifier/direct sentiment
result; the server was stopped afterward. Existing two LangChain history-API
deprecation warnings remain. No live Groq, SMTP/inbox, UI or deployment verification.
