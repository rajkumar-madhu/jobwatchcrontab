# Argus monitoring itself (R74)

"Do you use it yourself?" — yes. The platform's own recurring work runs as ordinary Argus jobs in
the operator's organisation, so it shows on the dashboard, keeps history and uptime, and alerts
through the same rules and channels as any customer job.

| Job | What it covers | Schedule | Grace |
|---|---|---|---|
| `jobwatch/reconciler` | each settlement pass (late, missed, unobserved, timed out) | every minute (runs every 30 s; one report a minute) | 2 min |
| `jobwatch/schedule-generator` | each pass that materialises expected runs | every minute | 3 min |
| `jobwatch/scorer` | the hourly health-score / partition / retention / usage pass | hourly | 15 min |

A pass that raises is a **failed run** with the traceback as its stderr, so the failure summary on the
job page says what broke.

## Turn it on

1. Pick the organisation that should own the jobs — usually your own company's org, created at
   bootstrap. Its id is printed by `cli bootstrap` and shown in Settings → Organization.
2. Create the jobs once (idempotent; safe to re-run after upgrades):
   ```bash
   python -m cronsentinel.cli selfmonitor --org <org_id>
   # Helm:  kubectl -n jobwatch exec deploy/jobwatch-api -- python -m cronsentinel.cli selfmonitor --org <org_id>
   ```
3. Set `SELF_MONITOR_ORG_ID=<org_id>` on the reconciler, schedule-generator and scorer and restart
   them. With Helm that is `env.SELF_MONITOR_ORG_ID` in values (`.env` for docker-compose).
4. Add an alert rule in that org, e.g. *any job tagged `self-monitor` failed or missed → PagerDuty*.

The three jobs count against the org's plan limit like any other (3 of the 5 free ones, so give the
operator org a paid or custom plan).

## What it cannot tell you

The reconciler is the component that turns silence into "missed". If the reconciler itself stops,
its own job is marked missed only when it comes back: the slot is settled late and the alert fires
then, with the monitoring gap visible on the job page. The platform's internal heartbeat table
(`platform_heartbeats`, R25) still protects customers — slots inside an outage are *unobserved*, not
missed — but for a real-time "the whole platform is down" page you need something outside the
platform: an external uptime check on `GET /healthz` of the API and the ingest host.

## Implementation

`apps/api/cronsentinel/selfmonitor.py`. Reports are written in-process through the same
`processor.process()` the ping URL uses — no HTTP to the ingest tier, no token in the environment
(the jobs' ping tokens are generated and discarded; they can only be reported by the workers).
`report()` never raises and is throttled to one success per minute per service; failures always
land. Identification is by `(org_id, name)`, so there is no migration and no new table.
