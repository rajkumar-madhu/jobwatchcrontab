# Unusual runs

A job can exit 0 and still be wrong: a backup that finished in 3 seconds instead of 20 minutes, an
export that ran four times longer than ever before, a dump of 1.2 KB where it is usually 4 GB.
[Run checks](run-checks) catch these if you write the rule. **Unusual runs** catch them without a
rule: Argus learns what is normal for each job from its own history.

It is on for every job at **Normal** sensitivity. It only warns: nothing reaches anyone until you
add an alert rule for it, so turning it on changed no one's alerts.

## What counts as unusual
Each successful run is compared with the job's last 50 successful runs. Runs already flagged as
unusual are left out, so a broken job never becomes the new normal. Nothing is judged before
10 runs.

| Finding | Flagged when the run… | Example message |
|---|---|---|
| Slow | took far longer than usual: at least 1.5× and 30 s longer | ran 1 h 10 min; usually 20 min 00 s (3.5× longer) |
| Fast | finished in a quarter of the usual time or less (jobs that usually take 20 s or more) | finished in 3.0 s; usually 20 min 00 s — it may have done nothing |
| Low metric | reported half the usual value or less | size_bytes was 1.2 KB; usually 4.2 GB — suspiciously small |
| High metric | reported at least twice the usual value, or any value where it is usually 0 | error_count was 3; usually 0 |

Metrics are the numbers a run reports, as for run checks: the heartbeat body's `metrics`, `metric=`
on Cronitor-style URLs, or `$JOBWATCH_METRICS_FILE` under `jobwatch-run`. Duration is judged for every job
that reports one.

"Usual" is the **median**, and the distance is measured in units of the **median absolute
deviation**, so one strange run in the history does not shift the baseline. A run must also be
far outside the job's normal variation:

| Sensitivity | Distance from usual |
|---|---|
| Low | only extreme changes (6 deviations) |
| Normal | 4.5 deviations (default) |
| High | smaller changes too (3 deviations) |
| Off | nothing is judged |

In a simulation of 100,000 ordinary runs at Normal, runtimes varying by ±10 % were never flagged; with
±30 % variation, about 1 run in 7,000 was.

## What happens
Set it per job (job page → **Unusual runs**) or through the API (`anomaly_sensitivity`, `anomaly_action`):

- **Keep it successful and warn** (default). The run stays a success and shows **Unusual for this
  job**. Alert rules with the condition **Unusual run** notify, with the reason in the subject:
  `◆ [MEDIUM] UNUSUAL RUN · nightly-backup on db-01 — unusual run: finished in 3.0 s; usually 20 min 00 s …`.
  Each unusual run notifies once. No incident is opened.
- **Count it as a failure.** The run is recorded as failed, the job's status changes, and your
  normal failure rules, incidents and escalations take over.

> [!NOTE]
> If a run breaks one of its [run checks](run-checks), that is the reason it failed and it is not
> also judged for being unusual.

Maintenance windows silence unusual-run alerts like any other.
