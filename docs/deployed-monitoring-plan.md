# Deployed application monitoring plan

Status: 2026-10-18. Plan PR #59 merged as `95d0f12`. Implementation is verified
locally and awaits its separate PR/release; the deployed connection is pending.

## Goal and hosting choice

Connect the Render application to the existing **local Docker Prometheus and
Grafana stack**. An action submitted through the deployed UI must produce
observable application metrics in local Prometheus and the Grafana panels.

The user clarified that monitoring is local on 2026-10-18. Reuse
`compose.monitoring.yaml`. Collection runs while the computer and Docker are
running; deploying monitoring to a separate host is deferred. This slice requires
no new hosting service.

## Current evidence

- `app/observability/monitoring.py` already records HTTP requests, new tasks,
  actual tools, durations and chat finalization, with bounded, content-free labels.
- `monitoring/prometheus.yml` targets `host.docker.internal:8011`, the local
  backend. Grafana queries `http://prometheus:9090` inside the Compose network.
- `deploy/nginx.conf.template` returns 404 for public `/metrics`. Render's backend
  listens on loopback inside its container, so the local stack cannot scrape it.
- Dashboard queries select `job="opsflow"` without an environment selector.
  Render observations must be distinguishable from any local target.
- Local read-only checks found the configured Docker daemon unavailable
  (`~/.docker/run/docker.sock` missing) and no reachable Prometheus/Grafana
  services at localhost ports 9090/3000. Running configuration and volume contents
  could not be inspected. This does not establish a configuration failure.

This is source/configuration evidence, not verification of a working connection.

## Proposed connection and bounded changes

The path is deployed UI action → backend instrumentation → protected HTTPS
metrics endpoint on Render → local Docker Prometheus → local Docker Grafana.
The computer initiates outbound HTTPS requests. No public local ports or tunnel
are needed; local Prometheus/Grafana remain bound to localhost.

| Area | Proposed change | Observable result |
| --- | --- | --- |
| Render nginx and launcher | Opt-in metrics-only route with a separate runtime credential, disabled when unconfigured | Authorized scrape returns existing backend metrics; absent/wrong credentials expose no samples |
| Local Prometheus/Compose | Add a Render scrape config and read-only secret-file mount, selected through the existing config override or a small Compose override | Render target is healthy, with `up=1` and recent samples |
| Local Grafana | Reuse the provisioned data source and adapt existing panels to select Render explicitly | Task, tool and persistence panels display deployed observations without mixing local traffic |
| Deployment checks/docs | Cover enabled/disabled metrics access, configuration, setup, verification and rollback | Repeatable setup with recorded evidence and limitations |

Use a metrics credential separate from the UI password, with access only to the
metrics route. Set the Render secret at runtime; keep the local password file in
an ignored location and mount it read-only. Keep TLS verification enabled.
Preserve the default local backend configuration and existing Docker volumes.

Existing instrumentation covers the proposed slice. Add metrics only if a
specific demonstrated gap prevents the agreed verification. This slice excludes
new hosting, paid services, alerting, log shipping, reminder delivery metrics and
application feature changes. Saved reads can increase HTTP counters; task/tool
counters represent actual execution. Reminder delivery stays disabled on Render.

## Verification contract

1. **Configuration/access:** Validate the Render scrape config with the matching
   Prometheus tooling. Add focused launcher/proxy checks and real container HTTP
   checks for disabled metrics, missing/wrong/correct credentials, isolation of UI
   and metrics credentials, response format, and continued blocking of API/docs/
   schema paths. Keep credentials out of Git/logs and unnecessary child environments.
   Extend the existing CI container smoke check for enabled metrics access.
2. **Regression:** Run existing monitoring tests for execution, persistence and
   replay, relevant deployment checks, dependency/whitespace checks and required
   CI suite/image build. New tests focus on the changed deployment boundary and
   any changed dashboard filters.
3. **Local review:** Start Docker and the existing monitoring stack, inspect its
   actual target/data source and verify the protected route using the built app
   container. Check UI authentication. If chat/Streamlit behavior changes, exercise
   that flow in the inline browser and leave it open before merge per `AGENTS.md`.
4. **Render connection:** Following implementation agreement, merge/deployment
   approval and secret setup, identify the deployed commit and actual target.
   Confirm authenticated scraping, `up=1` and recent samples from multiple scrapes
   in local Prometheus. A reachable Grafana login page is insufficient.
5. **Action evidence:** During a quiet window, record baseline task/tool/persistence
   samples, submit one synthetic sentiment request through the deployed UI, and
   inspect its saved Activity/outcome. After subsequent scrapes, confirm one new
   task, its actual tool completion and matching saved finalization in Prometheus,
   then the same observations in Grafana. Record actual failures if they occur;
   HTTP/SSE 200 alone never proves task success.
6. **Refresh evidence:** Refresh/reopen the saved chat. After another scrape,
   task/tool/persistence counters must stay unchanged; HTTP reads may increase.
   Record concurrent traffic or a backend restart that prevents exact attribution.

Use cumulative counter differences for the single-action demonstration. Rate/p95
panels need multiple scrapes and enough observations. A first sample may already
contain a completed task, so `increase()` alone cannot prove that first action.
No-data panels must not be presented as invented zeroes.

## Limits, rollout and rollback

Render counters reset on backend restart. Local Prometheus retains collected
history in its volume, but cannot recover activity completed between scrapes if
Render restarts before collection, or collect while the computer is off. Render
Free can sleep/restart and lose local app records; cold starts may fail scrapes.
Regular scrapes are inbound traffic and may affect idle sleep behavior and Free
instance-hour usage. Document the chosen scrape interval and operating window;
this setup provides no continuous availability guarantee.

The planning PR merged with CI/DCO passing and `[skip render]`, preserving the
existing deployed release. The implementation adds the opt-in metrics route,
Render Compose/scrape configuration and an instance selector in every Grafana
panel. Prepare its separate PR for review before merge or changing live settings.
Final completion requires actual Render action evidence through both tools.

Local implementation checks pass: 1,242 offline tests, dependencies/whitespace,
native ARM64 image build, enabled/disabled container HTTP/WebSocket authentication,
Prometheus config validation and merged Compose mount/bind inspection. An isolated
review stack scrapes the new container successfully, Grafana's data-source health
is OK, every panel query parses and the inline dashboard shows the selected review
backend with availability 1. No local model/chat/worker/SMTP execution was used;
task/tool/persistence behavior is covered by existing offline regressions. Real
Render task/tool/persistence deltas remain unverified. The latest live check still
returns `/metrics` 404 on the existing release; no live secret/settings changed.

Rollback: stop the Render scrape configuration and remove the metrics runtime
configuration, then verify the public route is disabled. Preserve the local
Prometheus/Grafana volumes and default local configuration. Use the existing
Render/CI procedure if a code rollback is required and record its deployed commit.

## Official references checked

- [Prometheus scraping/authentication](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [nginx HTTP Basic authentication](https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html)
- [Grafana Prometheus variables](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/)
- [Render Free service limits](https://render.com/docs/free)
