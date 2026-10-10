# Python package structure

Application modules are grouped by responsibility. `app/main.py` remains the
FastAPI entry point; `streamlit_app.py` remains the Streamlit entry point.

| Package | Responsibility | Modules |
| --- | --- | --- |
| `app/api/` | HTTP request/response contracts and endpoints | chat, FAQ, profile, reminders |
| `app/core/` | Classification and execution orchestration | agent, runtime, intent_router, model_wait, execution_events |
| `app/chat/` | Chat persistence, context, streaming and singleton workspace identity | chat_store, sessions, chat_stream, profile |
| `app/reminders/` | Chat scheduling, retained reminders and delivery worker | chat_reminders, reminder_catalogue, reminder_worker |
| `app/ui/` | Streamlit transport, components and saved draft presentation | ui_client, ui_stream, chat_menu, email_catalogue |
| `app/observability/` | Sanitized request/task/tool logs and process-scoped metrics | monitoring |
| `app/routes/` | Deterministic execution gates | sentiment_route, keyword_route, faq_route |
| `app/tools/` | Individual analysis, retrieval, writing, scheduling and email utilities | existing tool modules |
| `app/workflows/` | Fixed extraction/tool/presentation workflows | sentiment_workflow, keyword_workflow, faq_workflow |

Use explicit imports such as `from app.core.runtime import execute_request` and
`from app.chat.chat_store import ChatStore`. Packages do not re-export old flat
module names. The package move preserves API payloads and stored-record formats;
it does not introduce a database migration or change execution behavior.

Run the backend with `python -m uvicorn app.main:app` and the UI with
`streamlit run streamlit_app.py`. The worker's module command is now
`python -m app.reminders.reminder_worker`; it remains a separate explicitly
started process. `--help` is a read-only check. Do not start it merely to read
saved reminders or review the UI.

The repository-level `ui/` directory contains CSS/fonts; `app/ui/` contains Python
modules. Model artifacts, SQLite defaults and agent environment loading retain
their repository-relative locations after the move. Docker copies `app/`
recursively and includes all packages.
