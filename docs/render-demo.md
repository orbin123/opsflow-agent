# Temporary Render Free demo

This deployment is a password-protected demonstration of the existing singleton
fictional workspace. Use synthetic data. Every viewer with the password shares
the same chats, drafts and reminder records. This does not introduce user accounts.

Render Free deletes local filesystem changes on sleep, restart and redeployment.
The cloud SQLite files are separate from local development records. No persistent
disk, reminder worker, SMTP credentials or email delivery is included. Drafting
still produces draft content; creating a reminder stores a temporary record only.
The app displays these limitations whenever `OPSFLOW_TEMPORARY_DEMO=1`.

## Container contract

The pinned Python 3.12 Linux image contains runtime dependencies, the trusted
classifier artifact/metadata, fictional FAQ data, UI/fonts/config and the Docs
guide. The allowlisted Docker context excludes `.env`, local databases, Git,
notebooks, tests and caches. All processes run as the unprivileged `opsflow` user.

`deploy/run_demo.py` starts one Uvicorn process on loopback port 8000, checks the
read-only chat catalogue for storage readiness, starts Streamlit on loopback
8501, and then starts nginx on `0.0.0.0:$PORT` (default 10000). Only nginx is
public. API, metrics and OpenAPI paths are not routed to the backend. The public
`/health` exposes only UI liveness; child failure stops the whole service.

The proxy requires HTTP Basic authentication for UI resources and WebSocket
handshakes. Username: `opsflow`. Supply `OPSFLOW_DEMO_PASSWORD` at runtime;
startup fails without a 16–72-byte password without line breaks. The password
is hashed using bcrypt through stdin, removed from child environments and never
forwarded to Streamlit. Passwords and Groq keys must never be committed or used
as Docker build arguments. Render supplies HTTPS for browser connections.

SIGTERM/interrupt stops the proxy/UI and asks the API to drain execution before
exit, allowing up to 140 seconds locally before forcing termination. Render Free
does not support a custom shutdown delay; its default 30-second window can cut
off longer in-flight turns. Forced termination remains subject to
the existing interrupted/unsaved recovery contract and never repeats work.

## Local review

Build `docker build --platform linux/amd64 -t opsflow-demo:review .`.
Run the container with port 10000 mapped to a free localhost port and a runtime
environment file kept outside Git. Include only the demo password,
`GROQ_API_KEY` and optionally existing `GROQ_*_MODEL` settings. Do not pass the
development `.env` wholesale. No volume containing local chat/reminder data
should be mounted into this demo.

Missing model credentials retain the application's explicit provider-unavailable
behavior. The runtime launcher removes SMTP settings even if supplied accidentally
and forces the UI API address to loopback. It never starts the delivery worker.

## Render deployment

Use a Docker web service built from the reviewed feature branch, with the Free
compute plan, a single instance, `/health` and no attached disk. Disable automatic
deploys so later branch changes require an explicit deployment. Select Singapore
for the India-based demo. Set the demo password and Groq configuration only as
runtime secrets. No Docker Hub publication is needed for Render's repository
Docker builder. Deployment does not authorize merging the feature branch.

Verify unauthenticated/wrong-password access is rejected, API paths are not
exposed, authenticated UI/WebSockets load, and a synthetic chat shows actual
Activity plus a saved final outcome. Refresh/restoration must not submit another
turn. Confirm the selected service is Free; do not upgrade automatically if
memory or platform limits prevent it from running.

Official references: [Render Free](https://render.com/docs/free),
[Docker](https://render.com/docs/docker), [CLI](https://render.com/docs/cli),
[nginx authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html),
[WebSocket proxying](https://nginx.org/en/docs/http/websocket.html).

## Recorded verification

Local full suite: 1,190 passed. Focused local checks: 153 passed; final supervisor
checks: 12 passed. Native Linux ARM64 image build and dependency check pass.
Linux focused checks pass across runs; two existing 3-second AppTest timeouts
and a normal-mode assertion affected by the demo flag required reruns. The last
timeout passes with a temporary 15-second allowance; repository timeouts are
unchanged. This is not a single default Linux focused-suite green result.

Actual local HTTP/WebSocket authentication, hidden backend paths, missing-password
startup and child-failure propagation pass. Inline browser verifies the demo notice,
successful sentiment, saved Activity and refresh with exactly one task execution.
Memory after chat is about 382 MiB within a 512 MiB cap; this is a single-session
smoke measurement, not a concurrency capacity claim. The emulated local AMD64
download was cancelled; hosted Intel build/runtime verification remains pending.
