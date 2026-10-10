# GitHub and Render CI/CD

Edit locally on a feature/fix branch, push it and open a pull request into `main`.
The `.github/workflows/ci.yml` workflow runs on every PR targeting `main` and
every push to `main`, without path filters or conditional skips. Its single `CI`
job uses Ubuntu 24.04 and Python 3.12.13, checks installed dependencies and commit
whitespace, runs the full offline pytest suite, builds the Linux AMD64 Docker
image and runs `scripts/ci_smoke.py` against that image. Actions are pinned to
verified release commit SHAs with read-only repository permissions.

The smoke check uses a generated test password and disposable containers. It
checks health, missing/wrong/correct UI and WebSocket authentication, hidden
backend routes and failure without a password. It makes no chat submissions,
starts no delivery worker and supplies no Groq/SMTP credentials. Existing tests
use provider/email doubles. Streamlit AppTest constructors explicitly allow 15
seconds per run for slower environments; assertions and application timeouts
are unchanged. A failed command fails the job; no automatic retries or ignored
test failures are configured.
The fresh-process profile test uses pytest's Python executable rather than
assuming a local `.venv` directory exists on the runner.

## Deployment connection

`render.yaml` targets `main` with `autoDeployTrigger: checksPass`. The existing
Render service must also have branch `main` and **After CI Checks Pass** selected;
editing YAML alone does not update this manually created service. Keep its
connected GitHub integration, Docker builder, Free/Singapore/single-instance
settings, `/health` check and existing runtime secrets. No Docker registry,
Render deploy hook or Render API credential is stored in GitHub Actions.

Require `CI` and the existing `DCO` check for PR merges on `main`. CI also runs
again on the merged commit, and Render waits for that commit's detected checks.
Render accepts successful, neutral and skipped conclusions, so the CI job must
remain unconditional; failed checks or zero detected checks prevent deployment.
PR branch changes do not deploy the service. GitHub permissions/protection and
Render deployment gating are separate controls.

Live configuration was verified on 2026-10-10: main protection requires current
CI/DCO results from GitHub Actions/DCO respectively, applies to admins and
requires a PR (no extra approving-review count). Render's API confirms
`main`/`checksPass`, Free, Singapore and one instance.
An intentional failing test in hosted run `38023780514` produced failed CI and
a blocked PR merge, with no new Render deployment. The temporary probe was
removed from the final diff. This verifies the PR gate; it does not directly
exercise failed checks on a new main commit.
Hosted run `38023988938` passes all 1,190 tests, dependency/whitespace checks,
the Linux AMD64 Docker build and actual container smoke checks. CI/DCO both pass.
Local full-suite, workflow lint and native ARM64 build/smoke verification also
pass; the container-backed UI remains available on port 8515 without model keys.

After merging, inspect GitHub Actions for the `main` commit and Render Events
for the automatic deploy. Confirm Render's deployed commit equals the merged
SHA, `/health` returns 200, authentication works, and browser chat/Activity plus
refresh restoration succeed. Health only proves UI liveness; it does not prove
model-provider availability or successful task execution.

## Completed deployment verification — 2026-10-10

User-approved PR #52 merged as `a3176c2b649c645bc16f666941383e9200105474`.
Main CI run `38051090755` passes all 1,190 tests, dependency/whitespace checks,
AMD64 Docker build and container smoke checks. Render automatically created
`dep-db52ogf40ujc73c2ec2g` with trigger `new_commit` after CI completed; it became
live on that exact SHA. No manual deploy command was used.

Hosted health, HTTP/WebSocket authentication and hidden backend routes pass.
Chrome completes a synthetic Groq-assisted sentiment request with saved workflow/
tool Activity. Refresh restores the same answer, while the new instance's logs
retain exactly one completed task. The hosted inline browser remained on Render's
loading page; Chrome review succeeds and stays open. No worker or email delivery
ran. Failed-main deployment gating, rollback and hosting capacity were not
experimentally tested. The verified documentation-only follow-up uses
`[skip render]` in its commit/merge message; CI still runs, but Render skips it.

## Recovery

For a bad release, open the service's Render Deploys page and roll back to a
recent successful deploy whose build is still retained. Dashboard rollback
disables automatic deployment. Fix/revert the code through a reviewed PR, then
restore **After CI Checks Pass** when ready. Rollback does not recover this Free
demo's disposable SQLite records. Redeployment can lose records and interrupt
turns beyond Render's default shutdown window; restoration never resubmits work.

References: [Render CI deployment gate](https://render.com/docs/deploys),
[Blueprint configuration](https://render.com/docs/blueprint-spec),
[rollback behavior](https://render.com/docs/rollbacks).
