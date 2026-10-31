# Import from Healthchecks.io, Cronitor or Sentry Crons

**Jobs → Import** brings your checks over. Preview first, then import. Keys are used for the request
only and never stored. Re-running an import creates nothing twice; your plan's job limit applies.

## Healthchecks.io (or self-hosted Healthchecks)
Use a project **API key** (Project → Settings → API Access).
- With the **read-write** key, every job keeps its check UUID as its ping token. In your scripts, change
  only the host: `hc-ping.com/` → `<ingest>/hc/`. Paths such as `/start`, `/fail` and exit codes keep working.
- A **read-only** key works too, but every job gets a new ping URL (shown once).

| Healthchecks check | Argus job |
|---|---|
| cron schedule with time zone and grace | same schedule, time zone and grace |
| interval ("every hour") | a cron that fires every interval, flagged for review |
| interval with no cron equivalent (e.g. 90 minutes) | imported without a schedule, flagged |
| systemd `OnCalendar` schedule | translated to cron when exact, otherwise reported |
| paused, tags, description | carried over |

## Cronitor
Use an API key with the `monitor:read` scope, and optionally your **telemetry key** (the key inside
your `cronitor.link` URLs).
- With the telemetry key, jobs keep their Cronitor URLs: change `cronitor.link/` → `<ingest>/cronitor/`.
  `state=`, `series=` and `metric=` keep working. Without it, every job gets a new ping URL.
- `job` and `heartbeat` monitors are imported; `check` and `site` monitors (HTTP uptime) are listed but
  not imported.
- Cron schedules are kept; "every 5 minutes" and "at 09:30" are converted; extra schedules are reported.
- `metric.duration < X` becomes the job's expected runtime; other per-run assertions become
  [run checks](run-checks); aggregate assertions are reported.

## Sentry Crons
Use a Sentry **auth token** with `org:read` (or `alerts:read`) and `project:read`: a personal token
(User settings → Personal Tokens) or an internal integration's token. Organization tokens cannot read
monitors. Enter your **organization slug** and, for EU organizations, `https://de.sentry.io`.
Self-hosted Sentry works too.
- With `project:read`, every job keeps Sentry's check-in credential (project ID, client key and monitor
  slug). Your code changes only the host:
  - **SDKs** (`sentry_sdk.crons.monitor`, `Sentry.withMonitor`, `capture_checkin`): use a DSN whose host
    points at Argus, `https://<key>@o1.ingest.sentry.io/<project id>` →
    `https://<key>@ingest.example.com/sentry/<project id>`.
  - **HTTP check-ins**: `https://o1.ingest.sentry.io/api/<project id>/cron/<slug>/<key>/` →
    `https://ingest.example.com/sentry/api/<project id>/cron/<slug>/<key>/`.
- Without `project:read`, every job gets a new Argus ping URL (shown once).

| Sentry monitor | Argus job |
|---|---|
| crontab schedule and time zone | same schedule and time zone |
| interval (`every 5 minutes`, `every 1 day`) | a cron that fires every interval, with one period of extra grace, flagged for review |
| interval of 1 month or 1 year | first of the month or year at midnight, flagged |
| other intervals (e.g. 90 minutes) | imported without a schedule, flagged |
| check-in margin (minutes) | grace |
| max runtime (minutes) | expected runtime; Sentry's defaults (1 and 30 minutes) apply when unset |
| disabled | paused |
| muted, failure threshold above 1, several environments | listed in the import notes |

> [!WARNING]
> Argus reads only check-ins from a Sentry envelope. Errors, transactions and sessions sent to that
> DSN are dropped. Point only your cron jobs at Argus: give them a separate DSN, or use HTTP check-ins.
> Leave your application's error-reporting DSN on Sentry.

If a project has several active client keys, check-ins must use the first one (the import lists it).
Monitors that Sentry would create from a check-in's `monitor_config` are not created here: import them
or create them in Argus first.
