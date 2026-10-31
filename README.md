# Argus

**Know the moment a scheduled job doesn't run.** Cron, systemd timers, Kubernetes CronJobs, backups,
pipelines: Argus expects every run before it is due, turns silence into an alert on time, and
delivers failures with the output and the host state that explain them.

Hosted at [jobwatch.wecrew.in](https://jobwatch.wecrew.in) (5 jobs free, no card) or self-hosted with
the Helm chart in this repository. Server: AGPL-3.0. Agents: Apache-2.0. See [Licence](#licence).

## 60 seconds, nothing to install

1. Sign up, create a job, copy its ping URL.
2. Append one line to the crontab entry you most worry about:

```cron
# before
15 2 * * *  /opt/jobs/pg-backup.sh
# after — Argus learns the schedule from the first few pings and alerts when one is missing or late
15 2 * * *  /opt/jobs/pg-backup.sh && curl -fsS -m 10 --retry 5 https://ingest.jobwatch.wecrew.in/ping/<token>
```

That is the whole integration. `&&` means a non-zero exit is a failure; a run that never pings is a
missed run; both alert through email, Slack, Teams, PagerDuty, Opsgenie, Discord, Telegram or a
webhook. Already on Healthchecks.io or Cronitor? [Import and keep your ping URLs](docs/IMPORT.md).

Want exit codes, duration, stdout/stderr and the host's disk, memory and load next to each failure?
Install the agent later, on the servers where it earns its place:

```bash
curl -fsSL https://jobwatch.wecrew.in/install.sh | sudo bash -s -- --server https://jobwatch.wecrew.in --token <bootstrap token>
# then wrap a job:   15 2 * * *  jobwatch-run -- /opt/jobs/pg-backup.sh
```

The agent is read-only on your crontabs, stdlib-only Go, and queues on disk when the network is down.
[docs/AGENT.md](docs/AGENT.md) · [docs/PINGS.md](docs/PINGS.md) · [docs/QUICKSTART.md](docs/QUICKSTART.md)

## Why another one

- **Expected before due.** Slots are generated from the schedule ahead of time, so "it didn't run"
  is detected at the deadline, not at the next successful run.
- **Honest about its own outages.** Runs that fell inside a Argus outage are *unobserved*, not
  *missed*; you are not paged for our downtime, and the dashboard says it happened.
- **Failures come with evidence.** Exit code meaning, the matching stderr lines, and what the host
  looked like during the run (disk, memory, load, I/O wait). See [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).
- **Built to pass a security review.** Row-level tenant isolation in Postgres, hashed tokens,
  encrypted integration secrets, redacted output, SAML/OIDC + SCIM + MFA, audit log streaming.
  [docs/SECURITY.md](docs/SECURITY.md)
- **It monitors itself.** The reconciler, generator and scorer are Argus jobs in our own org.
  [docs/SELF_MONITORING.md](docs/SELF_MONITORING.md)

## Self-host

```bash
cp .env.example .env
sed -i "s|^SECRET_ENCRYPTION_KEY=.*|SECRET_ENCRYPTION_KEY=$(openssl rand -base64 48)|" .env
docker compose --env-file .env -f infra/docker/docker-compose.yml up -d --build          # add --profile ai for Ollama
docker compose --env-file .env -f infra/docker/docker-compose.yml exec api alembic upgrade head
docker compose --env-file .env -f infra/docker/docker-compose.yml exec api python -m cronsentinel.cli bootstrap --org acme --email you@example.com
open http://localhost:3000/welcome
```

Production is a Helm chart: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), with the release process in
[docs/DEPLOY.md](docs/DEPLOY.md). Everything stays in your network; the copilot can use a model you host.

## Repository

```
apps/api            FastAPI + SQLAlchemy + Alembic + Celery · workers: exec_processor, reconciler, schedule_generator, rule_engine, scorer
apps/web            Next.js 15 dashboard, landing, onboarding, status pages
agents/linux-agent  Go, stdlib only · agents/k8s-agent  Go, client-go
infra/docker · infra/helm/{cronsentinel,cronsentinel-agent} · infra/keycloak-realm.json
integrations/       Terraform provider, Datadog, Sentry
deploy/             release scripts, smoke test, self-hosted runner setup
docs/               design, architecture, security, API, every feature
```

| Doc | What |
|---|---|
| [docs/CRONSENTINEL_PLATFORM.md](docs/CRONSENTINEL_PLATFORM.md) | Product + platform design, decision log |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Services, data flow, request paths |
| [docs/API.md](docs/API.md) | REST surface, auth, conventions |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Running the test suites, known stubs |
| [CHANGELOG.md](CHANGELOG.md) | Release notes, R1–R74 |

Tests: 1,060+ API integration tests, Go unit tests, 134 Playwright end-to-end tests, run on every push
(`.github/workflows/ci.yml`). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md). Security reports:
[SECURITY.md](SECURITY.md).

## Licence

The server (`apps/`, `infra/`, `integrations/`, `deploy/`) is **AGPL-3.0**: run it, change it,
self-host it for your company freely; if you offer a modified version as a service, publish your
changes. The agents (`agents/`) are **Apache-2.0**, because they run on your production servers and a
copyleft licence has no business there. Commercial licences for the server are available for
organisations that cannot use the AGPL: contact@wecrew.in.

Argus is built by [WeCrew](https://wecrew.in), Chennai.
