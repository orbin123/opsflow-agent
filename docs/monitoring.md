# Monitoring and logging

OpsFlow exposes content-free JSON logs and process-scoped Prometheus metrics.
Grafana reads Prometheus; browser access alone does not connect application data.
This local slice supports the existing single-backend boundary, not multiple
Uvicorn workers or distributed aggregation. Counters reset on backend restart;
Prometheus retains scraped history for 15 days in its Docker volume.

## Start locally

Start Docker Desktop, then start the backend in one terminal:

```sh
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --no-access-log
```

Start the monitoring services:

```sh
docker compose -f compose.monitoring.yaml up -d
```

The default target is `host.docker.internal:8011` on Docker Desktop. For another
backend port, copy `monitoring/prometheus.yml`, change its target, and set
`OPSFLOW_PROMETHEUS_CONFIG` to that file when running Compose. Linux networking
requires separately configuring a reachable backend target; it is not verified
by the Docker Desktop setup. Do not expose unauthenticated `/metrics` publicly.

Open [Prometheus](http://127.0.0.1:9090/targets) and confirm job `opsflow` is up.
Open [Grafana](http://127.0.0.1:3000/), sign in with the local initial `admin` /
`admin` credentials, and complete the password-change screen yourself or choose
Skip for local review. No credentials are committed. Open **OpsFlow → OpsFlow
monitoring**. The provisioned data source is **OpsFlow Prometheus**, querying
`http://prometheus:9090` over the Compose network. Dashboard and source definitions
live under `monitoring/grafana/`; edit those files rather than the provisioned UI.
The services bind only to localhost; authentication remains enabled in Grafana.

The monitoring stack does not start the backend, Streamlit or reminder worker.
It does not send notifications. `docker compose -f compose.monitoring.yaml down`
stops the services while preserving their named volumes. Backend and Streamlit
have their own process lifetimes.

## Monitor the deployed Render app from local Docker

The optional deployment route exposes only the existing metrics registry over
Render HTTPS. Set `OPSFLOW_METRICS_PASSWORD` on the Render service at runtime:
16–72 UTF-8 bytes, no line breaks or surrounding whitespace, and different from `OPSFLOW_DEMO_PASSWORD`.
Username is `opsflow-metrics`. The launcher hashes this separate credential and
removes it from API/UI child environments; nginx strips it before proxying.
Surrounding whitespace is rejected because Prometheus trims its secret file.
The UI credential cannot scrape metrics, and the metrics credential cannot open
the UI or its WebSocket. API/docs/schema paths stay blocked. With the variable
absent, `/metrics` stays 404; an explicitly empty/invalid value fails startup.
Do not add the secret to `render.yaml`, Git, build arguments or command arguments.

After the reviewed implementation is deployed, save the same metrics password
locally. Use a private ignored parent directory; the file must be readable by the
Prometheus container's unprivileged user. The parent prevents other local users
from traversing to the file; the file is mounted separately read-only in Docker.

```sh
mkdir -p var/monitoring-render
chmod 700 var/monitoring-render
python3 - <<'PYSECRET'
from getpass import getpass
from pathlib import Path
secret = getpass("Render metrics password: ")
if (not 16 <= len(secret.encode()) <= 72 or "\n" in secret or "\r" in secret
        or secret != secret.strip()):
    raise SystemExit("Use the same valid metrics password configured on Render")
path = Path("var/monitoring-render/password")
path.write_text(secret)
path.chmod(0o644)
PYSECRET
export OPSFLOW_METRICS_PASSWORD_FILE="$PWD/var/monitoring-render/password"
docker compose -f compose.monitoring.yaml -f compose.monitoring.render.yaml config
docker compose -f compose.monitoring.yaml -f compose.monitoring.render.yaml up -d
```

This reuses the existing local services/volumes. The override replaces only the
scrape configuration and adds the credential-file mount; a missing source file
fails instead of creating a directory. The default local config is unchanged.
The checked-in Render config uses HTTPS, certificate validation, a 60-second
scrape interval, a 15-second timeout, and the `environment="render"` label.
No inbound port or tunnel into the computer is needed. Local ports remain bound
to localhost, and Grafana still queries `http://prometheus:9090` inside Docker.

Open Prometheus Targets and confirm the Render hostname is **UP** with recent
samples. In **OpsFlow → OpsFlow monitoring**, select
`opsflow-temporary-demo.onrender.com:443` in **Backend**. Every panel filters this
instance so historical/local observations are not summed into Render results.
Use cumulative task/tool/persistence panels to compare samples before/after a new
synthetic deployed chat. Inspect the actual saved Activity, then refresh the chat
and confirm execution counters do not rise again. HTTP read counters may rise.
Rate/p95 panels need several scrapes and observations; empty panels are not zeroes.

The computer and Docker must stay running to collect samples. Render counters
reset on restart; the Prometheus volume retains collected history but cannot
recover work lost before a scrape. Cold starts can temporarily fail scrapes.
Scraping is inbound traffic and may affect Free idle sleep and instance-hour
usage. Stop collection when finished with
`docker compose -f compose.monitoring.yaml -f compose.monitoring.render.yaml stop prometheus`.
This is an operating-window setup, not continuous availability monitoring.

Rollback: stop the Render scrape, remove the Render metrics runtime variable,
and redeploy through the existing service procedure; verify `/metrics` returns
404. Return to the local backend with
`docker compose -f compose.monitoring.yaml up -d`, using the original local
configuration override if applicable. Preserve named volumes. Runtime and hosted
verification status is recorded in `docs/PLAN.md`; configuration alone is not proof
that a deployed action reached Prometheus/Grafana.

## Logging and request correlation

Every HTTP response gets a generated `X-Request-ID`. Caller-provided values are
ignored. UTC JSON records on stderr include `timestamp`, `event`, `request_id`,
and fixed metadata for requests, newly executed tasks, actual tool completions,
and chat persistence. FastAPI worker threads and disconnected SSE execution
inherit the original request context. Python calls outside HTTP have a null ID.
Concurrent requests have independent IDs.

The dedicated `opsflow.monitoring` logger excludes request/query bodies, raw URL
paths, chat/session/turn identifiers, titles, drafts, tool arguments/results,
credentials and exception text. It uses route templates and stable outcome codes.
Task/tool failures and persistence failures log at ERROR. HTTP validation/client
errors appear in request records; HTTP server errors log at ERROR. Unexpected
exceptions before response start produce a sanitized HTTP 500 with correlation.
Exceptions after response start cannot change the HTTP status and propagate
through the existing streaming transport. These guarantees concern the dedicated
logger, not third-party/server logging. Use `--no-access-log` to avoid Uvicorn's
raw path/query access logs; do not enable provider debugging. Logs are not shipped
to Grafana or stored durably by this slice; Loki ingestion is separate scope.

## Metric definitions

| Metric | Meaning / labels |
| --- | --- |
| `opsflow_http_requests_total` | HTTP responses by bounded method, route template and status |
| `opsflow_http_outcomes_total` | Preinitialized aggregate HTTP outcomes for first-error rate accuracy |
| `opsflow_http_request_duration_seconds` | Histogram of full HTTP lifetime by method/route |
| `opsflow_tasks_total` | New runtime executions by known intent, execution route and outcome |
| `opsflow_task_outcomes_total` | Preinitialized aggregate runtime outcomes for first-error rate accuracy |
| `opsflow_task_duration_seconds` | Runtime histogram by route, excluding SQLite finalization |
| `opsflow_tool_calls_total` | Actual tool completions/failures by known tool/outcome |
| `opsflow_tool_duration_seconds` | Recorded tool duration histogram by tool |
| `opsflow_turn_persistence_total` | Newly accepted chat finalization: saved, saved_failure, unsaved, unknown |

`/metrics` scrapes do not inflate API counts. Unmatched paths share `unmatched`;
unknown methods/intent/routes share bounded fallback labels. IDs/content are never
labels. Histograms expose count, sum and buckets for Prometheus p95 queries.

SSE HTTP 200 records transport acceptance, not successful work. Stream request
duration runs until the transport closes, including keep-alives; execution has a
separate duration and terminal outcome even after subscriber disconnect. Reads,
replay and recovery do not increment task/tool counters. Each new compound turn
counts as one task and each actual tool call counts separately. FAQ-only endpoint
runtime calls also count as tasks. Standalone workflow/agent tool calls count when
actual completion hooks run; direct FAQ calls are recorded from their runtime
trace. Reminder delivery by the separate worker is not instrumented in this API
slice. SMTP acceptance/inbox arrival remain separate states.

Task success does not prove successful persistence: check the persistence panel
for unsaved/unknown results. Classification/routing exceptions use unknown
intent/route and an error outcome. A new execution that fails is counted once;
replaying its saved failure does not count again. No storage replay is used to
rebuild counters on restart.

Dashboard refresh uses a supported 30-second interval. Rate panels use a five-minute window and require multiple scrapes;
no traffic or no observations may show no data, rather than invented zeroes.
Cumulative distribution panels show observed work since backend startup. The
HTTP error panel covers 5xx; task errors cover error/partial_failure, while
clarification remains its own outcome. Grafana/Prometheus use their standard UI;
no OpsFlow frontend design or component changes are included.

## Verification

Tests cover correlation and route labels, validation and unexpected HTTP errors,
content exclusion, outcome labels, actual tool calls without SSE, saved replay,
unsaved finalization, SSE task failure under HTTP 200 and disconnected completion.
Live browser/scrape evidence and remaining limitations are recorded in
`docs/PLAN.md` and `docs/agents_doc.md`. The optional Render scrape path is documented above. No alerting, distributed
tracing, cloud metric storage or durable log retention is included.

Implementation references: [Prometheus instrumentation guidance](https://prometheus.io/docs/practices/instrumentation/),
[Grafana Prometheus configuration](https://grafana.com/docs/grafana/latest/datasources/prometheus/configure/),
and [Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/).
