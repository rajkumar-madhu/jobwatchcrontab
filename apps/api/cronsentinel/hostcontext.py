"""R70 — host context: what the server a job runs on looks like, for the job, run and agent pages.

Three readers share this module so they agree on the shape:
  GET /api/v1/jobs/{id}/host       the job's server, its agent, the latest sample, a 24 h series
  GET /api/v1/agents/{id}          the same for an agent, plus the jobs on its server
  GET /api/v1/executions/{id}      the samples taken while that run was going (`host.metrics_during`)

Facts come from the agent's heartbeat (`host` object) and are whitelisted here — the agent is a
machine credential, so nothing it sends is stored unfiltered.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

FACT_KEYS: dict[str, type] = {
    "os": str, "kernel": str, "arch": str, "cpus": int, "mem_total_mb": int, "disk_total_gb": float,
    "uptime_s": int, "load5": float, "load15": float, "timezone": str, "virt": str,
}
_MAX_STR = 120

# What a process exit code usually means, in the words an engineer would say. Codes 128+n are
# "killed by signal n" — the ones a scheduler meets most are named; the rest fall back to the rule.
EXIT_MEANING: dict[int, str] = {
    0: "Completed normally.",
    1: "General failure — the program reported an error; the last stderr lines usually say which.",
    2: "Misuse of a shell builtin or a bad command-line argument (also psql/pg_dump: connection or query error).",
    3: "Tool-specific failure (rsync: input/output or usage error).",
    124: "Killed by `timeout` — the command ran longer than its time limit.",
    125: "The container runtime (docker/podman) failed before the command started.",
    126: "Command found but not executable — check the file's mode and interpreter line.",
    127: "Command not found — PATH under cron is minimal; use the full path to the binary.",
    128: "Invalid exit argument.",
    130: "Interrupted (SIGINT, Ctrl-C).",
    134: "Aborted (SIGABRT) — an assertion failed or the runtime panicked.",
    137: "Killed (SIGKILL) — usually the kernel OOM killer; check memory on the host at that time.",
    139: "Segmentation fault (SIGSEGV).",
    141: "Broken pipe (SIGPIPE) — the process writing to a closed pipe, e.g. `| head`.",
    143: "Terminated (SIGTERM) — stopped by a supervisor, a deploy or the host shutting down.",
    255: "Exit status out of range, or ssh could not connect.",
}


def exit_meaning(code: int | None) -> str | None:
    if code is None:
        return None
    if code in EXIT_MEANING:
        return EXIT_MEANING[code]
    if 128 < code < 160:
        return f"Killed by signal {code - 128}."
    return "Program-specific exit code; see the output."


def clean_facts(raw: Any) -> dict[str, Any] | None:
    """Keep only known keys with the right type; None when nothing usable was sent."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    for k, typ in FACT_KEYS.items():
        v = raw.get(k)
        if v is None:
            continue
        if typ is str:
            if isinstance(v, str) and v.strip():
                out[k] = v.strip()[:_MAX_STR]
        elif isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v < 1e15:
            # R72: Python's JSON parser accepts NaN/Infinity; int(inf) raises and json.dumps(inf) is
            # not valid JSON for Postgres, and either one would fail the whole heartbeat
            out[k] = int(v) if typ is int else round(float(v), 2)
    return out or None


def agent_state(last_seen: datetime | None, interval_s: int | None, revoked: datetime | None, now: datetime) -> str:
    if revoked:
        return "revoked"
    if not last_seen:
        return "never"
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    return "online" if now - last_seen < timedelta(seconds=(interval_s or 60) * 3) else "offline"


def _point(r) -> dict[str, Any]:
    return {"ts": r.ts, "cpu_pct": r.cpu_pct, "mem_pct": r.mem_pct, "load1": r.load1, "disk_pct": r.disk_pct,
            "inode_pct": r.inode_pct, "io_wait_pct": r.io_wait_ms}   # the column is misnamed (0001); the agent sends a percentage


def series(s, server_id, since: datetime, until: datetime | None = None, points: int = 96) -> list[dict[str, Any]]:
    """Samples for one server in [since, until], thinned to about `points` by time bucket."""
    until = until or datetime.now(UTC)
    span = max((until - since).total_seconds(), 60)
    bucket = max(int(span / points), 60)
    rows = s.execute(text("""
        SELECT to_timestamp(floor(extract(epoch FROM ts) / :b) * :b) AS ts,
               round(avg(cpu_pct)::numeric, 1) AS cpu_pct, round(avg(mem_pct)::numeric, 1) AS mem_pct,
               round(avg(load1)::numeric, 2) AS load1, round(max(disk_pct)::numeric, 1) AS disk_pct,
               round(max(inode_pct)::numeric, 1) AS inode_pct, round(avg(io_wait_ms)::numeric, 1) AS io_wait_ms
        FROM host_metrics WHERE server_id=:sid AND ts >= :since AND ts <= :until
        GROUP BY 1 ORDER BY 1"""), {"sid": str(server_id), "since": since, "until": until, "b": bucket}).all()
    return [_point(r) for r in rows]


def host_context(s, server_id, hours: int = 24, with_jobs: bool = True) -> dict[str, Any] | None:
    """Everything the UI shows about one server. None when the server does not exist (or RLS hides it)."""
    srv = s.execute(text("""
        SELECT sv.id, sv.hostname, sv.labels, sv.facts, sv.facts_updated_at,
               a.id AS agent_id, a.kind AS agent_kind, a.name AS agent_name, a.version AS agent_version, a.status AS agent_status,
               a.last_seen_at, a.skew_ms, a.heartbeat_interval_s, a.revoked_at
        FROM servers sv LEFT JOIN agents a ON a.id = sv.agent_id WHERE sv.id=:id"""), {"id": str(server_id)}).first()
    if not srv:
        return None
    now = datetime.now(UTC)
    latest = s.execute(text("SELECT ts, cpu_pct, mem_pct, load1, disk_pct, inode_pct, io_wait_ms FROM host_metrics WHERE server_id=:sid ORDER BY ts DESC LIMIT 1"),
                       {"sid": str(server_id)}).first()
    out: dict[str, Any] = {
        "server": {"id": srv.id, "hostname": srv.hostname, "labels": srv.labels or {}, "facts": srv.facts or {}, "facts_updated_at": srv.facts_updated_at},
        "agent": None if not srv.agent_id else {
            "id": srv.agent_id, "kind": srv.agent_kind, "name": srv.agent_name, "version": srv.agent_version,
            "state": agent_state(srv.last_seen_at, srv.heartbeat_interval_s, srv.revoked_at, now),
            "last_seen_at": srv.last_seen_at, "skew_ms": srv.skew_ms, "heartbeat_interval_s": srv.heartbeat_interval_s or 60},
        "latest": _point(latest) if latest else None,
        "series": series(s, server_id, now - timedelta(hours=hours), now),
        "jobs": [],
    }
    if with_jobs:
        rows = s.execute(text("SELECT id, name, status, last_status, last_run_at, paused FROM jobs WHERE server_id=:sid ORDER BY status <> 'failed', status <> 'missed', name"),
                         {"sid": str(server_id)}).all()
        out["jobs"] = [{**dict(r._mapping), "status": str(r.status), "last_status": str(r.last_status) if r.last_status else None} for r in rows]
    return out


def metrics_during(s, server_id, start: datetime | None, end: datetime | None, pad_s: int = 300) -> list[dict[str, Any]]:
    """Raw samples taken while a run was going, padded by `pad_s` either side so a one-minute run
    still shows the sample before and after it."""
    if not start:
        return []
    end = end or start
    since, until = start - timedelta(seconds=pad_s), end + timedelta(seconds=pad_s)
    rows = s.execute(text("SELECT ts, cpu_pct, mem_pct, load1, disk_pct, inode_pct, io_wait_ms FROM host_metrics WHERE server_id=:sid AND ts BETWEEN :a AND :b ORDER BY ts LIMIT 200"),
                     {"sid": str(server_id), "a": since, "b": until}).all()
    return [_point(r) for r in rows]
