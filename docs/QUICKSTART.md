# Quick start

JobWatch expects every scheduled run before it is due, so a job that fails, runs late or never starts
is caught on time. This page gets a first job monitored in a few minutes.

## 1. Create an account
Sign up with your work email (or Google, GitHub or Microsoft if your installation offers them). If your
company already uses JobWatch with single sign-on, you join its workspace automatically.

## 2. Paste one crontab line
At sign-up (or **Jobs → Add job → From a crontab line**) paste the entry you would least like to find
out about in a week, as it appears in `crontab -l`:
```
15 2 * * *  /opt/jobs/pg-backup.sh
```
JobWatch takes the schedule from it, names the job after the command (`pg-backup`), uses your
browser's time zone (change it on the job page if the server runs in another), and gives the line
back with one curl appended. Replace the line in `crontab -e`:
```
15 2 * * *  /opt/jobs/pg-backup.sh && curl -fsS -m 10 --retry 5 https://ingest.example.com/ping/<token>
```
`&&` means a failing command never pings. So a failure and a run that never happened both show as
the job missing its 02:15 deadline (plus the 5-minute grace), and you are alerted at 02:20. The token
is shown once; JobWatch stores only a hash. Nothing is installed and nothing runs as root.

To tell failures from misses, report start and exit codes, or ping from pipelines and containers, see
[Pings and heartbeat API](pings).

## 3. Add the agent where a failure needs explaining
When "it didn't run" is not enough — you want exit codes, the stderr lines that matter, duration, and
what the host's disk, memory and load looked like during the run — install the agent on that server.
It discovers crontabs and systemd timers, wraps runs with `jobwatch-run`, and reports
start, finish, exit code, duration and output automatically. See [Linux agent](linux-agent). For
Kubernetes CronJobs, install the in-cluster agent with Helm: [Kubernetes](kubernetes).

## 4. Decide who hears about it
**Alerting → Add channel** (Slack, Microsoft Teams, Discord, Telegram, email, webhooks, PagerDuty,
Opsgenie, Datadog), then **Add rule** (for example "Job failed or missed, tag prod → #ops-alerts").
What an alert contains is described in [Alerts](alerts).

## 5. Catch runs that "succeed" but do the wrong thing
Add [run checks](run-checks) such as `metric.size_bytes > 0` so an empty backup counts as a failure.

## Moving from another tool?
Import from Healthchecks.io, Cronitor or Sentry Crons and keep your existing ping URLs: [Import](import).
