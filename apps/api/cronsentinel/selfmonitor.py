"""R74 — Argus monitors its own scheduled work.

The platform already records worker heartbeats internally (workers/platform_health.py) so that its
own outages are not counted against customers' jobs. That is invisible to the operator. This module
makes the platform's recurring passes ordinary Argus jobs in one organisation — the operator's —
so they appear on the dashboard, carry history and uptime, and alert through the same Slack /
PagerDuty / email rules as everything else. The honest answer to "do you use it yourself?".

Set SELF_MONITOR_ORG_ID to the organisation that should own the jobs, then run
    python -m cronsentinel.cli selfmonitor --org <org_id>
once (idempotent) to create them. Each worker pass then calls report(); a pass that raised is a
failed run with the error as stderr.

Limits, stated plainly: the reconciler is what turns silence into "missed". If the reconciler itself
is down, its own job is marked missed only when it comes back (the slot is then settled late and the
alert still fires, with the gap visible). For a real-time signal that the whole platform is down,
point an external monitor at /healthz.

report() never raises: a self-monitoring bug must not take the worker down with it.
"""
from __future__ import annotations

import socket
import time
import traceback
from datetime import UTC, datetime

import structlog
from sqlalchemy import text

from .config import settings

log = structlog.get_logger()

# service → (job name, cron, grace seconds, description). Cron has minute resolution, so the 30 s
# reconciler and 60 s generator are "every minute" jobs and report at most once a minute (THROTTLE).
SERVICES: dict[str, tuple[str, str, int, str]] = {
    "reconciler": ("jobwatch/reconciler", "* * * * *", 120,
                   "Settles expected runs: late, missed, unobserved, timed out. Every 30 s."),
    "schedule-generator": ("jobwatch/schedule-generator", "* * * * *", 180,
                           "Materialises the next expected runs for every job with a schedule. Every 60 s."),
    "scorer": ("jobwatch/scorer", "0 * * * *", 900,
               "Hourly: health scores, partitions, retention, usage totals."),
}
THROTTLE_S = 55            # a minute-resolution slot gets one success report, not two
_last_report: dict[str, float] = {}
_job_cache: dict[str, tuple[str, str] | None] = {}   # service → (org_id, job_id) or None when absent
_HOST = socket.gethostname()


def enabled() -> bool:
    return bool(settings.self_monitor_org_id)


def _job(s, service: str) -> tuple[str, str] | None:
    if service in _job_cache:
        return _job_cache[service]
    name = SERVICES[service][0]
    row = s.execute(text("SELECT org_id, id FROM jobs WHERE org_id = CAST(:o AS uuid) AND name = :n AND paused = false"),
                    {"o": settings.self_monitor_org_id, "n": name}).first()
    _job_cache[service] = (str(row.org_id), str(row.id)) if row else None
    return _job_cache[service]


def forget_cache() -> None:
    """Tests, and `selfmonitor` after creating jobs in a long-lived process."""
    _job_cache.clear(); _last_report.clear()


def report(s, service: str, *, ok: bool = True, duration_ms: int | None = None, error: str | None = None,
           force: bool = False) -> bool:
    """Record one pass of `service` as a run of its self-monitoring job. Returns True if recorded.
    Successes are throttled to one per THROTTLE_S; failures are always recorded."""
    if not enabled() or service not in SERVICES:
        return False
    now = time.monotonic()
    if ok and not force and now - _last_report.get(service, 0) < THROTTLE_S:
        return False
    try:
        target = _job(s, service)
        if not target:
            return False
        org, job_id = target
        from .processor import process   # late import: processor pulls in alerting
        ev = {"org_id": org, "job_id": job_id, "kind": "success" if ok else "fail", "execution_id": None, "sequence": 0,
              "agent_ts": None, "server_ts": datetime.now(UTC).isoformat(), "duration_ms": duration_ms,
              "exit_code": 0 if ok else 1, "host": _HOST, "stdout_tail": None,
              "stderr_tail": (error or "")[:4000] or None, "meta": {"self_monitor": True, "service": service}, "metrics": None}
        process(s, ev)
        _last_report[service] = now
        return True
    except Exception as e:   # noqa: BLE001 — see module docstring
        log.warning("self-monitor report failed", service=service, error=str(e)[:200])
        return False


class timed:
    """`with selfmonitor.timed(s, "scorer"):` — reports success with the elapsed time, or failure
    with the traceback, and re-raises so the worker's own error handling still runs."""
    def __init__(self, session_factory, service: str):
        self.sf, self.service, self.t0 = session_factory, service, 0.0

    def __enter__(self):
        self.t0 = time.monotonic(); return self

    def __exit__(self, et, ev, tb):
        if not enabled():
            return False
        ms = int((time.monotonic() - self.t0) * 1000)
        try:
            with self.sf() as s:
                if et is None:
                    report(s, self.service, ok=True, duration_ms=ms)
                else:
                    report(s, self.service, ok=False, duration_ms=ms, error="".join(traceback.format_exception(et, ev, tb))[-4000:])
        except Exception as e:   # noqa: BLE001
            log.warning("self-monitor session failed", service=self.service, error=str(e)[:200])
        return False


def ensure_jobs(s, org_id: str) -> list[dict]:
    """Create (or leave in place) the self-monitoring jobs in `org_id`'s first workspace. Idempotent
    on job name. Returns one row per service with `created`."""
    from . import pingtokens, schedule
    ws = s.execute(text("SELECT id FROM workspaces WHERE org_id = CAST(:o AS uuid) ORDER BY created_at LIMIT 1"), {"o": org_id}).first()
    if not ws:
        raise ValueError(f"organisation {org_id} has no workspace")
    out = []
    for service, (name, expr, grace, desc) in SERVICES.items():
        existing = s.execute(text("SELECT id FROM jobs WHERE org_id = CAST(:o AS uuid) AND name = :n"), {"o": org_id, "n": name}).first()
        if existing:
            out.append({"service": service, "job_id": str(existing.id), "created": False}); continue
        _, tok_hash, tok_hint = pingtokens.new_token()   # the plaintext is dropped: these jobs are reported in-process
        r = s.execute(text(
            "INSERT INTO jobs (org_id, workspace_id, name, description, kind, heartbeat_token_hash, heartbeat_token_hint, schedule_expr, tz, "
            "grace_s, tags, status, next_expected_at) VALUES (CAST(:o AS uuid), :ws, :n, :d, 'heartbeat', :th, :hint, :expr, 'UTC', :g, "
            "ARRAY['jobwatch','self-monitor'], 'healthy', :nxt) RETURNING id"),
            {"o": org_id, "ws": ws.id, "n": name, "d": desc, "th": tok_hash, "hint": tok_hint, "expr": expr, "g": grace,
             "nxt": schedule.next_run(expr, "UTC")}).first()
        out.append({"service": service, "job_id": str(r.id), "created": True})
    forget_cache()
    return out
