"""Mock JobWatch API for UI review — demo data only, no DB."""
import random
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://localhost:3001"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
now = datetime.now(timezone.utc)
iso = lambda d: d.isoformat()
random.seed(7)
# The real API always returns org_id/created_at on these rows; the mock must too, or the
# frontend is developed against a shape production never sends (caught by R14 schema contract).
ORG = str(uuid.uuid5(uuid.NAMESPACE_DNS, "jobwatch-demo-org"))
CREATED = iso(now - timedelta(days=90))
J = [("nightly-database-backup","0 2 * * *","At 02:00 AM","healthy",["prod","db","backup"],91,900),("billing-reconciliation","0 */6 * * *","Every 6 hours","healthy",["prod","billing"],98,300),
     ("market-data-import","*/15 * * * *","Every 15 minutes","recovered",["prod","data"],74,60),("customer-report-generator","30 6 * * *","At 06:30 AM","failed",["prod","reports"],61,600),
     ("log-cleanup","0 4 * * *","At 04:00 AM","healthy",["prod","maintenance"],99,120),("mongodb-backup","0 3 * * *","At 03:00 AM","missed",["prod","db","backup"],83,700),
     ("redis-snapshot","*/30 * * * *","Every 30 minutes","running",["prod","cache"],97,20),("payments/settle-eod","0 22 * * *","At 10:00 PM","late",["kubernetes","payments"],88,400)]
JOBS = [{"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, n)), "workspace_id": "ws", "name": n, "description": None, "kind": "cron", "schedule_expr": c, "schedule_human": h, "tz": "UTC", "expected_runtime_s": e,
         "grace_s": 300, "tags": t, "status": s, "paused": False, "last_run_at": iso(now - timedelta(minutes=random.randint(5, 600))), "last_status": "failed" if s == "failed" else "success",
         "next_expected_at": iso(now + timedelta(hours=random.randint(1, 9))), "reliability_score": r, "heartbeat_token": None, "heartbeat_token_hint": n[-4:],
         "assertions": ["metric.size_bytes > 0", "duration < 2h"] if "backup" in n else [],   # R54
         "anomaly_sensitivity": "normal", "anomaly_action": "warn",
         "server_id": None if "kubernetes" in t else ("srv-db" if "db" in t or s == "failed" else "srv-web")} for n, c, h, s, t, r, e in J]   # R68, R70
def execs(j, n=30):
    out = []; base = j["expected_runtime_s"] * 1000; slow = j["name"] == "nightly-database-backup"
    for i in range(n):
        t = now - timedelta(hours=(n - i) * 3)
        st = "success"; d = int(random.gauss(base, base * .08)); code = 0
        if slow: d = int(base * (1 + 3.2 * i / n))
        if j["status"] == "failed" and i >= n - 3: st, code, d = "failed", 2, 12000
        if j["name"] == "market-data-import" and random.random() < .15: st, code = "failed", 1
        if j["status"] == "missed" and i == n - 1: st, d = "missed", None
        anomalies = []
        if j["name"] == "nightly-database-backup" and i == n - 2:   # R69: a backup that wrote almost nothing
            anomalies = [{"kind": "low", "field": "size_bytes", "value": 1200, "typical": 4.2e9, "runs": 28, "message": "size_bytes was 1.2 KB; usually 4.2 GB — suspiciously small"}]
        if j["name"] == "log-cleanup" and i == n - 1:   # R68: the latest run finished almost instantly
            typical = base; d = 1800
            anomalies = [{"kind": "fast", "field": "duration", "value": d, "typical": typical, "runs": 29,
                          "message": f"finished in 1.8 s; usually {typical // 60000} min {typical // 1000 % 60:02d} s — it may have done nothing"}]
        out.append({"id": f"{j['id'][:8]}-{int(t.timestamp())}-{i}", "job_id": j["id"], "status": st, "scheduled_ts": iso(t), "agent_ts_start": iso(t), "agent_ts_end": iso(t + timedelta(milliseconds=d or 0)), "duration_ms": d, "exit_code": code if d else None, "host": "prod-db-01" if "db" in j["tags"] or j["status"] == "failed" else "prod-web-01", "skew_ms": random.randint(-40, 40),
                    "metrics": {}, "assertion_failures": [], "anomalies": anomalies})
    if j["status"] == "running": out.append({"id": "run-now", "job_id": j["id"], "status": "running", "scheduled_ts": iso(now - timedelta(seconds=25)), "agent_ts_start": iso(now - timedelta(seconds=25)), "agent_ts_end": None, "duration_ms": None, "exit_code": None, "host": "prod-web-01", "skew_ms": 12})
    return list(reversed(out))
EX = {j["id"]: execs(j) for j in JOBS}
byid = {j["id"]: j for j in JOBS}
INC = [{"org_id": ORG, "id": "inc1", "severity": "high", "status": "open", "title": "3 related jobs failing", "started_at": iso(now - timedelta(hours=1, minutes=12)), "acknowledged_at": None, "resolved_at": None, "affected_job_ids": [JOBS[3]["id"], JOBS[5]["id"], JOBS[0]["id"]], "job_names": ["customer-report-generator", "mongodb-backup", "nightly-database-backup"], "root_cause": None, "resolution": None, "last_notified_at": iso(now - timedelta(minutes=58)),
        "correlation_signals": [{"host": "prod-db-01", "job_id": JOBS[3]["id"], "infra": ["io_wait 188ms"]}, {"host": "prod-db-01", "job_id": JOBS[5]["id"]}, {"host": "prod-db-01", "job_id": JOBS[0]["id"], "infra": ["io_wait 188ms", "disk 91%"]}]},
       {"org_id": ORG, "id": "inc2", "severity": "medium", "status": "resolved", "title": "market-data-import is failed", "started_at": iso(now - timedelta(days=1, hours=3)), "acknowledged_at": iso(now - timedelta(days=1, hours=2)), "resolved_at": iso(now - timedelta(days=1)), "affected_job_ids": [JOBS[2]["id"]], "job_names": ["market-data-import"], "root_cause": "Upstream feed returned 502 for 40 minutes", "resolution": "auto: job recovered"}]

@app.get("/api/v1/analytics/overview")
def ov(): return {"total_jobs": 8, "by_status": {"healthy": 3, "failed": 1, "missed": 1, "late": 1, "running": 1, "recovered": 1}, "executions_today": 146, "success_rate_today": 94.52, "top_slowest_7d": [{"name": "nightly-database-backup", "p95_ms": 3120000}, {"name": "mongodb-backup", "p95_ms": 712000}, {"name": "customer-report-generator", "p95_ms": 640000}], "top_failing_7d": [{"name": "customer-report-generator", "failures": 3}, {"name": "market-data-import", "failures": 2}], "mttd_min": 1.4, "mttr_min": 42.5}
@app.get("/api/v1/platform/monitoring-gaps")
# R25 said "two days old" but hardcoded an absolute date (2026-09-20), which drifted outside the
# dashboard's 7-day window and silently zeroed the banner the moment real time passed 2026-09-27.
# R38 caught it as a side effect of running the full suite: compute it relative to `now` instead.
def gaps():
    started = now - timedelta(days=2, hours=1, minutes=8)
    ended = now - timedelta(days=2, hours=0, minutes=26)
    return {"gaps": [{"id": 1, "service": "schedule-generator", "started_at": iso(started), "ended_at": iso(ended), "slots_unobserved": 14}], "unobserved_slots_30d": 14}
@app.get("/api/v1/jobs")
def jobs(status: str | None = None, limit: int = 50): return {"items": [j for j in JOBS if not status or j["status"] == status], "next_cursor": None}
@app.get("/api/v1/jobs/{jid}")
def job(jid: str): return byid[jid]
@app.get("/api/v1/jobs/{jid}/executions")
def jex(jid: str, limit: int = 50): return EX[jid][:limit]
@app.get("/api/v1/jobs/{jid}/next-runs")
def nr(jid: str, n: int = 3): return {"human": byid[jid]["schedule_human"], "runs": [iso(now + timedelta(hours=k * 6 + 2)) for k in range(n)]}
@app.get("/api/v1/jobs/{jid}/impact")
def imp(jid: str):
    if jid == JOBS[0]["id"]: return {"upstream": [], "downstream": [{"id": JOBS[5]["id"], "name": "mongodb-backup", "status": "missed", "depth": 1}, {"id": JOBS[4]["id"], "name": "log-cleanup", "status": "healthy", "depth": 2}]}
    return {"upstream": [{"id": JOBS[0]["id"], "name": "nightly-database-backup", "status": "healthy"}] if jid == JOBS[5]["id"] else [], "downstream": []}
@app.get("/api/v1/executions/{eid}")
def ex(eid: str):
    for jid, xs in EX.items():
        for e in xs:
            if e["id"] == eid:
                t = datetime.fromisoformat(e["scheduled_ts"]); j = byid[jid]
                tl = [{"sequence": 0, "kind": "start", "agent_ts": iso(t), "server_ts": iso(t), "payload": {"command": f"/opt/jobs/{j['name']}.sh"}}, *([{"sequence": 1, "kind": "progress", "agent_ts": iso(t + timedelta(seconds=30)), "server_ts": iso(t + timedelta(seconds=30)), "payload": {}}] if (e["duration_ms"] or 0) > 60000 else [])]
                if e["agent_ts_end"]: tl.append({"sequence": 2, "kind": "success" if e["status"] == "success" else "fail", "agent_ts": e["agent_ts_end"], "server_ts": e["agent_ts_end"], "payload": {}})
                if "backup" in j["name"]:   # R54: backups report their size; a failed run shows a broken check
                    e = {**e, "metrics": {"size_bytes": 0 if e["status"] == "failed" else 7340032}, "meta": {"assertion_failures": ["metric.size_bytes > 0 (was 0)"] if e["status"] == "failed" else []}}
                if e.get("anomalies"):
                    e = {**e, "meta": {**e.get("meta", {}), "anomalies": e["anomalies"]}}
                logs = {"stdout": STDOUT.format(t=t, name=j["name"]), "stderr": STDERR if e["status"] == "failed" else ""}
                host = _run_host(e)   # R70
                return {"execution": e, "timeline": tl, "logs": logs, "log_bytes": {k: len(v.encode()) for k, v in logs.items()},
                        "exit_meaning": EXIT.get(e.get("exit_code")), "host": host}
@app.get("/api/v1/executions/{eid}/logs")
def ex_logs(eid: str, stream: str = "both"):
    from fastapi.responses import PlainTextResponse
    d = ex(eid); l = d["logs"]
    body = l[stream] if stream != "both" else f"{l['stdout']}\n----- stderr -----\n{l['stderr']}"
    return PlainTextResponse(body, headers={"Content-Disposition": f'attachment; filename="run-{eid}-{stream}.log"'})
@app.get("/api/v1/executions/{a}/compare/{b}")
def cmp(a: str, b: str):
    fa = next(e for xs in EX.values() for e in xs if e["id"] == a); fb = next(e for xs in EX.values() for e in xs if e["id"] == b)
    return {"a": fa, "b": fb, "delta": {"duration_ms": fb["duration_ms"] - fa["duration_ms"], "pct": round((fb["duration_ms"] - fa["duration_ms"]) / fa["duration_ms"] * 100, 1)} if fa["duration_ms"] and fb["duration_ms"] else None}
@app.get("/api/v1/incidents")
def incs(status: str | None = None, limit: int = 50): return [i for i in INC if not status or i["status"] == status]
@app.get("/api/v1/incidents/{iid}")
def inc(iid: str):
    i = next(x for x in INC if x["id"] == iid)
    return {"incident": i, "timeline": [{"ts": i["started_at"], "kind": "opened", "actor_id": None, "payload": {"prev": "healthy", "new": "failed"}}, {"ts": iso(now - timedelta(hours=1, minutes=10)), "kind": "correlated", "payload": {"reason": "same host prod-db-01", "prev": "healthy", "new": "missed"}}, {"ts": iso(now - timedelta(minutes=58)), "kind": "notified", "payload": {"kind": "slack", "status": "sent"}}, {"ts": iso(now - timedelta(minutes=40)), "kind": "note", "payload": {"text": "DB team looking at io wait on prod-db-01"}}],
            "notifications": [{"sent_at": iso(now - timedelta(minutes=58)), "kind": "slack", "name": "ops-alerts", "status": "sent", "error": None}, {"sent_at": iso(now - timedelta(minutes=58)), "kind": "email", "name": "oncall", "status": "sent", "error": None}],
            "affected_jobs": [{"id": jid, "name": byid[jid]["name"], "status": byid[jid]["status"], "last_run_at": byid[jid]["last_run_at"]} for jid in i["affected_job_ids"]], "executions": EX[i["affected_job_ids"][0]][:4], "downstream_impact": {i["affected_job_ids"][0]: [{"id": JOBS[4]["id"], "name": "log-cleanup", "status": "healthy", "depth": 1}]}}
@app.get("/api/v1/logs/search")
# R16: was `**kw`, which FastAPI reads as a *required* query param named "kw" — every call 422'd
# and the Logs page only ever rendered its error state against this mock. Mirror the real params.
# R38: added `until` and real time-based pagination so the frontend's "Load more" (which walks
# `until` backwards from the oldest row shown) has something real to page through, and generated
# rows span several distinct hours so the hour-grouping headers have more than one bucket to draw.
def logs(q: str | None = None, job_id: str | None = None, stream: str | None = None, host: str | None = None,
         status: str | None = None, since: str | None = None, until: str | None = None, limit: int = 200):
    all_items = []
    for n in range(260):
        j = JOBS[n % 6]
        ts = now - timedelta(minutes=5 * n)  # every 5 min, newest first — spans >20 hours
        failed = n % 17 == 0
        if failed:
            all_items.append({"execution_id": f"log-{n}-err", "stream": "stderr", "content": 'psycopg2.OperationalError: connection to server at "prod-db-01" failed: timeout expired\n(12 retries exhausted)\n', "job_id": j["id"], "job_name": j["name"], "status": "failed", "host": "prod-db-01", "scheduled_ts": iso(ts), "exit_code": 2})
        all_items.append({"execution_id": f"log-{n}", "stream": "stdout", "content": f"starting {j['name']}\nprocessed 48,211 rows in 14.2s\ndone", "job_id": j["id"], "job_name": j["name"], "status": "failed" if failed else "success", "host": "prod-web-01", "scheduled_ts": iso(ts), "exit_code": 2 if failed else 0})
    if since: all_items = [r for r in all_items if r["scheduled_ts"] >= since]
    if until: all_items = [r for r in all_items if r["scheduled_ts"] < until]
    return {"items": all_items[:limit], "hosts": ["prod-web-01", "prod-db-01", "backup-01"]}
# R16: R4's integrations endpoints were never mocked — the Integrations page rendered against 404s
# since R4 and R12's e2e did not notice (its assertions ran before the queries failed).
_DEST = str(uuid.uuid5(uuid.NAMESPACE_DNS, "jobwatch-demo-dest"))
@app.get("/api/v1/integrations/schema")
def sig_schema(): return {"schema": "jobwatch.signal/1", "version": 1, "event_types": ["job.state_changed", "job.failed", "job.missed", "job.recovered"],
                          "headers": ["X-JobWatch-Signal-Id", "X-JobWatch-Schema", "X-JobWatch-Signature"],
                          "signature": "sha256 HMAC of raw body with the destination secret, as 'sha256=<hex>'",
                          "idempotency": "dedupe on signal_id; deliveries may repeat on retry",
                          "example": {"schema": "jobwatch.signal/1", "event_type": "job.failed", "signal_id": "sig_demo"}}
@app.get("/api/v1/integrations/destinations")
def sig_dests(): return [{"id": _DEST, "name": "aegis-prod", "kind": "webhook", "event_types": ["job.failed", "job.missed"], "workspace_ids": None,
                          "enabled": True, "consecutive_failures": 0, "disabled_reason": None, "created_at": CREATED, "sent_24h": 42, "failed_24h": 1,
                          "url": "https://aegis.example.internal/ingest/jobwatch", "has_secret": True}]
@app.get("/api/v1/integrations/deliveries")
def sig_deliveries(limit: int = 100): return [{"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dlv{i}")), "destination_id": _DEST, "destination": "aegis-prod",
                                               "signal_id": f"sig_{i:04d}", "event_type": "job.failed", "status": "sent" if i else "failed", "attempts": 1 if i else 3,
                                               "last_error": None if i else "connect timeout", "response_code": 202 if i else None,
                                               "created_at": iso(now - timedelta(minutes=5 * i)), "sent_at": iso(now - timedelta(minutes=5 * i)) if i else None}
                                              for i in range(min(limit, 5))]
# ---- R70: host context ---------------------------------------------------------------------
STDOUT = ("[{t:%H:%M:%S}] starting {name}\n[{t:%H:%M:%S}] connected to postgres 16.4 (prod-db-01:5432)\n[{t:%H:%M:%S}] schema public: 212 tables\n"
          "[{t:%H:%M:%S}] dumping public.orders (48,211,034 rows)\n[{t:%H:%M:%S}] dumping public.order_items (191,004,117 rows)\n[{t:%H:%M:%S}] INFO  compression level 6\n"
          "[{t:%H:%M:%S}] WARN  slow write: 4.1 MB/s to /var/backups (expected > 40 MB/s)\n[{t:%H:%M:%S}] dumping public.events\n")
STDERR = ('pg_dump: error: could not write to output file: No space left on device\npg_dump: error: dumping contents of table "public.events" failed: PQgetCopyData() failed.\n'
          'pg_dump: detail: Error message from server: server closed the connection unexpectedly\n\tThis probably means the server terminated abnormally\n\tbefore or while processing the request.\n'
          'Traceback (most recent call last):\n  File "/opt/jobs/backup.py", line 88, in <module>\n    run_dump(target)\n  File "/opt/jobs/backup.py", line 61, in run_dump\n    raise BackupError(f"pg_dump exited {rc}")\nBackupError: pg_dump exited 1\n')
EXIT = {0: "Completed normally.", 1: "General failure — the program reported an error; the last stderr lines usually say which.",
        2: "Misuse of a shell builtin or a bad command-line argument (also psql/pg_dump: connection or query error).",
        127: "Command not found — PATH under cron is minimal; use the full path to the binary.", 137: "Killed (SIGKILL) — usually the kernel OOM killer; check memory on the host at that time."}
FACTS = {"srv-db": {"os": "Ubuntu 24.04.1 LTS", "kernel": "6.8.0-45-generic", "arch": "amd64", "cpus": 8, "mem_total_mb": 32096, "disk_total_gb": 491.2, "uptime_s": 37 * 86400 + 4 * 3600, "load5": 6.8, "load15": 5.9, "timezone": "Etc/UTC", "virt": "vm"},
         "srv-web": {"os": "Debian GNU/Linux 12 (bookworm)", "kernel": "6.1.0-25-amd64", "arch": "amd64", "cpus": 4, "mem_total_mb": 7950, "disk_total_gb": 78.7, "uptime_s": 112 * 86400, "load5": 0.4, "load15": 0.3, "timezone": "Etc/UTC", "virt": "vm"}}
SERVERS = {"srv-db": {"id": "srv-db", "hostname": "prod-db-01", "labels": {"env": "prod", "role": "database", "region": "ap-south-1"}, "facts": FACTS["srv-db"], "facts_updated_at": iso(now - timedelta(seconds=20)), "agent": "a1"},
           "srv-web": {"id": "srv-web", "hostname": "prod-web-01", "labels": {"env": "prod", "role": "web"}, "facts": FACTS["srv-web"], "facts_updated_at": iso(now - timedelta(seconds=35)), "agent": "a4"}}
def _series(sid, hours=24, step_min=15):
    """prod-db-01 tells a story: disk fills through the night and io wait climbs with it; the web box is flat."""
    pts = []; n = hours * 60 // step_min
    for i in range(n + 1):
        t = now - timedelta(minutes=(n - i) * step_min); f = i / n
        if sid == "srv-db":
            disk = 61 + 33 * max(0, (f - 0.45) / 0.55) ** 1.4
            pts.append({"ts": iso(t), "cpu_pct": round(22 + 10 * random.random() + (35 if 0.5 < f < 0.9 else 0), 1), "mem_pct": round(58 + 6 * random.random() + 20 * f, 1),
                        "load1": round(1.2 + 7 * max(0, f - 0.5) + random.random(), 2), "disk_pct": round(disk, 1), "inode_pct": round(4 + f, 1), "io_wait_pct": round(1 + 24 * max(0, f - 0.55) + random.random(), 1)})
        else:
            pts.append({"ts": iso(t), "cpu_pct": round(8 + 6 * random.random(), 1), "mem_pct": round(41 + 3 * random.random(), 1), "load1": round(0.2 + 0.3 * random.random(), 2),
                        "disk_pct": round(37 + f, 1), "inode_pct": 2.0, "io_wait_pct": round(0.3 + random.random(), 1)})
    return pts
SERIES = {k: _series(k) for k in SERVERS}
AGENTS = [{"id": "a1", "kind": "linux", "name": "prod-db-01", "host_id": "4c9e1f…", "version": "0.2.0", "status": "active", "last_seen_at": iso(now - timedelta(seconds=20)), "skew_ms": 38, "revoked_at": None, "created_at": CREATED, "jobs": 3},
          {"id": "a2", "kind": "linux", "name": "backup-01", "host_id": "9a02bb…", "version": "0.1.0", "status": "active", "last_seen_at": iso(now - timedelta(minutes=9)), "skew_ms": 7200, "revoked_at": None, "created_at": CREATED, "jobs": 2},
          {"id": "a3", "kind": "k8s", "name": "production", "host_id": "k8s:production", "version": "0.2.0", "status": "active", "last_seen_at": iso(now - timedelta(seconds=40)), "skew_ms": -12, "revoked_at": None, "created_at": CREATED, "jobs": 6},
          {"id": "a4", "kind": "linux", "name": "prod-web-01", "host_id": "e71d20…", "version": "0.2.0", "status": "active", "last_seen_at": iso(now - timedelta(seconds=35)), "skew_ms": 5, "revoked_at": None, "created_at": CREATED, "jobs": 5}]
def _agent_state(a): return "revoked" if a["revoked_at"] else ("offline" if now - datetime.fromisoformat(a["last_seen_at"]) > timedelta(minutes=3) else "online")
def _ctx(sid):
    sv = SERVERS[sid]; a = next(x for x in AGENTS if x["id"] == sv["agent"]); ser = SERIES[sid]
    return {"server": {k: sv[k] for k in ("id", "hostname", "labels", "facts", "facts_updated_at")},
            "agent": {"id": a["id"], "kind": a["kind"], "name": a["name"], "version": a["version"], "state": _agent_state(a), "last_seen_at": a["last_seen_at"], "skew_ms": a["skew_ms"], "heartbeat_interval_s": 60},
            "latest": ser[-1], "series": ser,
            "jobs": sorted([{"id": j["id"], "name": j["name"], "status": j["status"], "last_status": j["last_status"], "last_run_at": j["last_run_at"], "paused": False} for j in JOBS if j["server_id"] == sid],
                           key=lambda j: (j["status"] not in ("failed", "missed"), j["name"]))}
def _run_host(e):
    j = byid[e["job_id"]]; sid = j["server_id"] or next((k for k, v in SERVERS.items() if v["hostname"] == e.get("host")), None)
    if not sid and not e.get("host"): return None
    during = []
    if sid and e.get("agent_ts_start"):
        a = datetime.fromisoformat(e["agent_ts_start"]) - timedelta(minutes=5); b = datetime.fromisoformat(e["agent_ts_end"] or e["agent_ts_start"]) + timedelta(minutes=5)
        during = [p for p in SERIES[sid] if a <= datetime.fromisoformat(p["ts"]) <= b]
        if len(during) < 3 and e["status"] == "failed":   # old failed runs: synthesise the samples so the panel has something to say
            t = datetime.fromisoformat(e["agent_ts_start"])
            during = [{"ts": iso(t + timedelta(minutes=m)), "cpu_pct": 71.0 + m, "mem_pct": 88.5, "load1": 7.9 + m / 10, "disk_pct": 94.0 + m / 2, "inode_pct": 5.0, "io_wait_pct": 26.0 + m} for m in (-4, 1, 6)]
    return {"hostname": e.get("host") or SERVERS[sid]["hostname"], "server_id": sid, "facts": SERVERS[sid]["facts"] if sid else {}, "metrics_during": during}
@app.get("/api/v1/jobs/{jid}/host")
def job_host(jid: str):
    j = byid[jid]
    if not j["server_id"]: return {"job_id": jid, "source": "ping", "last_host": EX[jid][0].get("host") if EX[jid] else None, "context": None}
    return {"job_id": jid, "source": "agent", "last_host": EX[jid][0].get("host"), "context": _ctx(j["server_id"])}
@app.get("/api/v1/agents/{aid}")
def agent_detail(aid: str):
    a = next(x for x in AGENTS if x["id"] == aid); sid = next((k for k, v in SERVERS.items() if v["agent"] == aid), None)
    return {**a, "heartbeat_interval_s": 60, "state": _agent_state(a), "context": _ctx(sid) if sid else None}
@app.get("/api/v1/agents")
def agents(): return [{**a, "heartbeat_interval_s": 60, "state": _agent_state(a)} for a in AGENTS]   # R72
def _old_agents(): return [{"id": "a1", "kind": "linux", "name": "prod-db-01", "host_id": "4c9e1f…", "version": "0.1.0", "status": "active", "last_seen_at": iso(now - timedelta(seconds=20)), "skew_ms": 38, "revoked_at": None, "created_at": CREATED, "jobs": 3}, {"id": "a2", "kind": "linux", "name": "backup-01", "host_id": "9a02bb…", "version": "0.1.0", "status": "active", "last_seen_at": iso(now - timedelta(minutes=9)), "skew_ms": 7200, "revoked_at": None, "created_at": CREATED, "jobs": 2}, {"id": "a3", "kind": "k8s", "name": "production", "host_id": "k8s:production", "version": "0.1.0", "status": "active", "last_seen_at": iso(now - timedelta(seconds=40)), "skew_ms": -12, "revoked_at": None, "created_at": CREATED, "jobs": 6}]
@app.get("/api/v1/alerts/channels")
def ch(): return [{"id": "c1", "kind": "slack", "name": "ops-alerts", "rate_per_min": 30, "enabled": True, "created_at": CREATED}, {"id": "c2", "kind": "email", "name": "oncall", "rate_per_min": 30, "enabled": True, "created_at": CREATED}]
@app.get("/api/v1/alerts/rules")
def rules(): return [{"org_id": ORG, "created_at": CREATED, "id": "r1", "name": "Prod failures → Slack", "condition": "failed", "scope": {"tags": ["prod"]}, "severity": "high", "enabled": True}, {"org_id": ORG, "created_at": CREATED, "id": "r2", "name": "Missed backups page oncall", "condition": "missed", "scope": {"tags": ["backup"]}, "severity": "critical", "enabled": True}, {"org_id": ORG, "created_at": CREATED, "id": "r3", "name": "Recovery notices", "condition": "recovered", "scope": {}, "severity": "low", "enabled": False}]
@app.get("/api/v1/alerts/ledger")
def ledger(limit: int = 30): return [{"id": k, "incident_id": "inc1", "channel_id": "c1", "kind": "slack", "name": "ops-alerts", "dedup_key": "r1:cust…:failed", "sent_at": iso(now - timedelta(minutes=58 + k * 30)), "status": ["sent", "sent", "rate_limited", "failed"][k % 4], "error": "502 from hooks.slack.com" if k % 4 == 3 else None} for k in range(6)]
@app.get("/api/v1/clusters")
def clusters(): return [{"id": "cl1", "name": "production", "scope": "cluster", "namespaces": [], "last_seen_at": iso(now - timedelta(seconds=40)), "version": "0.1.0", "cronjobs": 6, "failing": 1}, {"id": "cl2", "name": "analytics", "scope": "namespaces", "namespaces": ["analytics", "data"], "last_seen_at": iso(now - timedelta(minutes=3)), "version": "0.1.0", "cronjobs": 4, "failing": 0}]
@app.get("/api/v1/clusters/{cid}/cronjobs")
def cjs(cid: str, namespace: str | None = None):
    rows = [{"namespace": "payments", "name": "settle-eod", "schedule": "0 22 * * *", "suspend": False, "concurrency_policy": "Forbid", "successful_history_limit": 3, "failed_history_limit": 1, "active_deadline_s": 3600, "starting_deadline_s": 200, "last_schedule_at": iso(now - timedelta(hours=2)), "last_success_at": iso(now - timedelta(days=1, hours=2)), "image": "ghcr.io/acme/settle:1.42.0", "job_id": JOBS[7]["id"], "status": "late", "reliability_score": 88, "failures_7d": 1, "last_reason": "OOMKilled"},
            {"namespace": "payments", "name": "reconcile-ledger", "schedule": "*/10 * * * *", "suspend": False, "concurrency_policy": "Replace", "successful_history_limit": 3, "failed_history_limit": 1, "active_deadline_s": None, "starting_deadline_s": None, "last_schedule_at": iso(now - timedelta(minutes=4)), "last_success_at": iso(now - timedelta(minutes=4)), "image": "ghcr.io/acme/ledger:2.1.3", "job_id": JOBS[1]["id"], "status": "healthy", "reliability_score": 99, "failures_7d": 0, "last_reason": None},
            {"namespace": "analytics", "name": "warehouse-sync", "schedule": "0 * * * *", "suspend": True, "concurrency_policy": "Allow", "successful_history_limit": 5, "failed_history_limit": 2, "active_deadline_s": 1800, "starting_deadline_s": None, "last_schedule_at": iso(now - timedelta(days=3)), "last_success_at": iso(now - timedelta(days=3)), "image": "ghcr.io/acme/wh:0.9", "job_id": JOBS[4]["id"], "status": "paused", "reliability_score": 96, "failures_7d": 0, "last_reason": None}]
    # R65: time zone, annotation warnings, and an ignored (not monitored) CronJob
    rows[0] = {**rows[0], "time_zone": "Asia/Kolkata", "annotation_warnings": []}
    rows[1] = {**rows[1], "time_zone": None, "annotation_warnings": ["jobwatch.io/grace: 'soon' is not a duration (e.g. 90, 10m, 2h, 1h30m)"]}
    rows.append({**rows[1], "name": "scratch-cleanup", "job_id": None, "status": None, "time_zone": None, "annotation_warnings": []})
    return {"cronjobs": [r for r in rows if not namespace or r["namespace"] == namespace], "events": [{"namespace": "payments", "object_kind": "Pod", "object_name": "settle-eod-29012345-x8k2p", "reason": "OOMKilled", "message": "Container settle was OOM killed (limit 512Mi)", "ts": iso(now - timedelta(hours=2))}, {"namespace": "payments", "object_kind": "Pod", "object_name": "settle-eod-29012345-x8k2p", "reason": "BackOff", "message": "Back-off restarting failed container", "ts": iso(now - timedelta(hours=1, minutes=55))}]}
@app.get("/api/v1/topology")
def topo(): return {"status": "failed", "servers": [{"id": "s1", "name": "prod-db-01", "status": "failed", "users": [{"name": "root", "status": "failed", "jobs": [{"id": JOBS[0]["id"], "name": "nightly-database-backup", "status": "healthy"}, {"id": JOBS[3]["id"], "name": "customer-report-generator", "status": "failed"}]}, {"name": "postgres", "status": "missed", "jobs": [{"id": JOBS[5]["id"], "name": "mongodb-backup", "status": "missed"}]}]}, {"id": "s2", "name": "prod-web-01", "status": "healthy", "users": [{"name": "www-data", "status": "healthy", "jobs": [{"id": JOBS[1]["id"], "name": "billing-reconciliation", "status": "healthy"}, {"id": JOBS[4]["id"], "name": "log-cleanup", "status": "healthy"}]}]}], "clusters": [{"id": "cl1", "name": "production", "status": "late", "namespaces": [{"name": "payments", "status": "late", "cronjobs": [{"id": JOBS[7]["id"], "name": "settle-eod", "status": "late"}, {"id": JOBS[1]["id"], "name": "reconcile-ledger", "status": "healthy"}]}]}], "heartbeat_only": [{"id": JOBS[2]["id"], "name": "market-data-import", "status": "recovered"}, {"id": JOBS[6]["id"], "name": "redis-snapshot", "status": "running"}]}
@app.get("/api/v1/dependencies")
def deps(): return {"nodes": [{"id": JOBS[0]["id"], "name": "nightly-database-backup", "status": "healthy"}, {"id": JOBS[5]["id"], "name": "mongodb-backup", "status": "missed"}, {"id": JOBS[4]["id"], "name": "log-cleanup", "status": "healthy"}, {"id": JOBS[3]["id"], "name": "customer-report-generator", "status": "failed"}], "edges": [{"job_id": JOBS[5]["id"], "depends_on_job_id": JOBS[0]["id"]}, {"job_id": JOBS[4]["id"], "depends_on_job_id": JOBS[5]["id"]}, {"job_id": JOBS[3]["id"], "depends_on_job_id": JOBS[0]["id"]}]}
@app.get("/api/v1/analytics/series")
def series(days: int = 14, bucket: str = "day"):
    if bucket == "hour":   # R69: the overview's 24-hour range
        n = days * 24; r = random.Random(days)
        return {"bucket": "hour", "points": [{"t": iso((now - timedelta(hours=n - k)).replace(minute=0, second=0, microsecond=0)), "executions": (e := 4 + r.randint(0, 5) + (6 if k % 24 in (2, 3, 4) else 0)), "ok": e - (f := r.choice([0, 0, 0, 0, 1])) - (m := r.choice([0] * 9 + [1])), "failed": f, "missed": m, "p50_ms": 42000, "p95_ms": 380000} for k in range(n)],
                "incidents": [{"t": iso(now - timedelta(hours=5)), "n": 1}]}
    r = random.Random(days)
    return {"bucket": "day", "points": [{"t": iso(now - timedelta(days=days - k)), "executions": (e := 140 + r.randint(-10, 10)), "ok": e - (f := r.randint(0, 6)) - (m := r.randint(0, 2)), "failed": f, "missed": m, "p50_ms": 42000 + k * 900, "p95_ms": 380000 + k * 9000} for k in range(days)], "incidents": [{"t": iso(now - timedelta(days=days - k)), "n": r.choice([0, 0, 1, 2])} for k in range(days)]}
@app.get("/api/v1/analytics/unusual-runs")   # R69
def unusual(days: int = 7, limit: int = 20):
    out = []
    for j in JOBS:
        for e in EX[j["id"]]:
            if e.get("anomalies"):
                out.append({"execution_id": e["id"], "job_id": j["id"], "job_name": j["name"], "status": e["status"], "finished_at": e["agent_ts_end"], "host": e["host"], "anomalies": e["anomalies"]})
    return out[:limit]
@app.get("/api/v1/analytics/jobs")
def ajobs(days: int = 30, sort: str = "reliability"): return sorted([{**j, "runs": len(EX[j["id"]]), "ok": sum(e["status"] == "success" for e in EX[j["id"]]), "failures": sum(e["status"] == "failed" for e in EX[j["id"]]), "missed": sum(e["status"] == "missed" for e in EX[j["id"]]), "success_rate": round(100 * sum(e["status"] == "success" for e in EX[j["id"]]) / len(EX[j["id"]]), 1), "p50_ms": j["expected_runtime_s"] * 1000, "p95_ms": int(j["expected_runtime_s"] * 1400), "drift_pct": 212.0 if j["name"] == "nightly-database-backup" else round(random.uniform(-4, 9), 1), "sla_target": 99.5 if "backup" in j["tags"] else None, "sla_met": False if j["status"] in ("failed", "missed") else (True if "backup" in j["tags"] else None), "est_cost_usd": round(j["expected_runtime_s"] / 3600 * len(EX[j["id"]]) * .05, 2)} for j in JOBS if EX[j["id"]]], key=lambda x: x["reliability_score"])   # R74: jobs created during a run have no executions yet
@app.get("/api/v1/analytics/mttr")
def mttr(days: int = 30): return {"incidents": 7, "mttd_min": 1.4, "mtta_min": 9.0, "mttr_min": 42.5, "resolved": 6}
@app.get("/api/v1/analytics/report")
def rep(period: str = "weekly"): return {"period": period, "runs": 1012, "success_rate": 96.1, "success_rate_prev": 97.4, "delta_pts": -1.3, "failed": 27, "missed": 6, "p95_ms": 402000, "incidents": 4, "open_incidents": 1, "jobs_with_sla": 2, "worst_jobs": [{"name": "customer-report-generator", "failures": 9}, {"name": "market-data-import", "failures": 8}, {"name": "mongodb-backup", "failures": 3}], "slowest_jobs": [{"name": "nightly-database-backup", "p95_ms": 3120000}, {"name": "mongodb-backup", "p95_ms": 712000}], "lowest_reliability": [{"name": "customer-report-generator", "reliability_score": 61}, {"name": "market-data-import", "reliability_score": 74}, {"name": "mongodb-backup", "reliability_score": 83}]}
@app.get("/api/v1/copilot/suggestions")
def sug(): return {"questions": ["Why did the most recent failure happen?", "Which jobs failed after the last deployment?", "Which jobs have increasing duration?", "Which servers have the most cron failures?"]}
@app.get("/api/v1/copilot/history")
def hist(limit: int = 10): return [{"id": "h1", "question": "Why is customer-report-generator failed?", "created_at": iso(now - timedelta(minutes=35)), "answer": ANS}]
ANS = {"summary": "customer-report-generator has failed 3 consecutive runs since 06:30 because it cannot obtain a PostgreSQL connection from prod-db-01.", "root_cause": "Database connection timeout — prod-db-01 disk I/O latency climbed from 12 ms to 188 ms, starving the connection pool while nightly-database-backup ran 3× longer than usual.", "evidence": ["12 'connection to server at prod-db-01 failed: timeout expired' lines across the last 3 runs", "io_wait on prod-db-01: 12 ms → 188 ms over 48 h; disk 91%", "nightly-database-backup duration +212% in the same window", "mongodb-backup missed its 03:00 schedule on the same host"], "affected_resources": ["prod-db-01", "customer-report-generator", "mongodb-backup", "nightly-database-backup"], "confidence": 0.82, "remediation": ["Check PostgreSQL connection pool saturation (pg_stat_activity)", "Inspect disk utilisation and I/O wait on prod-db-01; free space below 10%", "Consider moving nightly-database-backup earlier or to backup-01 to avoid overlap with 06:30 report"], "relevant_logs": ["psycopg2.OperationalError: connection to server at \"prod-db-01\" failed: timeout expired", "(12 retries exhausted)"], "investigate_commands": ["ssh prod-db-01 'iostat -x 5 3'", "psql -h prod-db-01 -c \"select state, count(*) from pg_stat_activity group by 1\"", "df -h /var/lib/postgresql"], "what_changed": ["Disk usage on prod-db-01 crossed 90% ~36 h ago", "Backup duration began climbing 5 days ago"]}
@app.post("/api/v1/copilot/ask")
def ask(body: dict): return {"id": "x", "answer": ANS, "context": {"jobs": ["customer-report-generator", "mongodb-backup", "nightly-database-backup"], "executions": 36, "metrics_points": 48}, "model": "qwen2.5:14b", "latency_ms": 4210}
@app.get("/api/v1/billing")
def bill(): return {"subscription": {"plan": "team", "status": "trialing", "trial_ends_at": iso(now + timedelta(days=9)), "current_period_end": None, "cancel_at_period_end": False, "has_customer": False, "effective_plan": "team", "provider": "stripe", "currency": "usd", "billing_interval": "month"}, "plans": [{"plan": "free", "max_jobs": 5, "retention_days": 7, "features": ["email", "slack", "webhook"], "monthly_usd": 0, "yearly_usd": 0, "monthly_inr": 0, "yearly_inr": 0}, {"plan": "developer", "max_jobs": 100, "retention_days": 30, "features": ["email", "slack", "webhook"], "monthly_usd": 19, "yearly_usd": 190, "monthly_inr": 799, "yearly_inr": 7999}, {"plan": "team", "max_jobs": 1000, "retention_days": 365, "features": ["slack", "webhook", "teams", "ai", "kubernetes", "pagerduty", "oncall"], "monthly_usd": 79, "yearly_usd": 790, "monthly_inr": 3299, "yearly_inr": 32999}, {"plan": "business", "max_jobs": None, "retention_days": 730, "features": ["pagerduty", "sso", "audit_stream"], "monthly_usd": 299, "yearly_usd": 2990, "monthly_inr": 12499, "yearly_inr": 124999}, {"plan": "enterprise", "max_jobs": None, "retention_days": None, "features": ["all"], "monthly_usd": None, "yearly_usd": 6000, "monthly_inr": None, "yearly_inr": None}], "usage": {"jobs": 8, "executions_this_month": 4120, "log_bytes": 18400000}, "limits": {"max_jobs": 1000, "retention_days": 365}, "configured": False, "configured_inr": False}
@app.get("/public/status/{slug}")
def st(slug: str): return {"title": "Acme scheduled jobs", "overall": "degraded", "jobs": [{"name": j["name"], "status": j["status"], "last_run_at": j["last_run_at"], "uptime_90d": round(99.9 - (100 - j["reliability_score"]) / 4, 2), "recent": [e["status"] for e in EX[j["id"]]][:30], "show_duration": False} for j in JOBS[:5]], "incidents": [{"title": INC[1]["title"], "severity": "medium", "status": "resolved", "started_at": INC[1]["started_at"], "resolved_at": INC[1]["resolved_at"]}], "maintenance": [{"starts_at": iso(now + timedelta(days=2)), "ends_at": iso(now + timedelta(days=2, hours=2))}]}
@app.get("/api/v1/workspaces")
def ws(): return [{"id": "ws", "name": "default", "created_at": CREATED}]
@app.post("/api/v1/jobs", status_code=201)   # R74: onboarding creates the first job from a pasted crontab line
def create_job(body: dict):
    j = {**JOBS[0], "id": str(uuid.uuid4()), "name": body.get("name", "my-first-job"), "description": body.get("description"), "kind": "heartbeat",
         "schedule_expr": body.get("schedule_expr"), "schedule_human": body.get("schedule_expr"), "tz": body.get("tz", "UTC"), "grace_s": body.get("grace_s", 300),
         "tags": body.get("tags", []), "status": "healthy" if body.get("schedule_expr") else "unknown", "last_run_at": None, "last_status": None,
         "next_expected_at": None, "reliability_score": None, "heartbeat_token": "tok_" + uuid.uuid4().hex, "heartbeat_token_hint": "mock", "assertions": [], "server_id": None}
    JOBS.append(j); byid[j["id"]] = j; EX[j["id"]] = []
    return j
@app.get("/api/v1/status-pages")
def sp(): return [{"id": "p1", "slug": "demo", "title": "Acme scheduled jobs", "visibility": "public", "job_ids": [j["id"] for j in JOBS[:5]]}]
@app.get("/auth/providers")   # R51
def providers(): return {"social": [{"alias": "google", "label": "Google"}, {"alias": "github", "label": "GitHub"}, {"alias": "microsoft", "label": "Microsoft"}], "sso": True, "signup": True}
@app.get("/auth/discover")   # R51
def discover(email: str): return {"sso": email.endswith("@acme.com"), "provider": "Okta" if email.endswith("@acme.com") else None}
@app.get("/auth/session")
def sess(): return {"user": {"id": "u", "email": "le@finspot.in", "name": "LE"}, "org_id": "o", "orgs": [{"id": "o", "name": "Acme", "slug": "acme", "plan": "team", "role": "owner"}]}
# R66: on-call
_PEOPLE = [{"id": "7a000000-0000-4000-8000-000000000001", "name": "Ana Rao", "email": "ana@acme.io"},
           {"id": "7a000000-0000-4000-8000-000000000002", "name": "Ben Ito", "email": "ben@acme.io"},
           {"id": "7a000000-0000-4000-8000-000000000003", "name": "Cy Diaz", "email": "cy@acme.io"}]
def _sched(sid, name, tz, layers, now_name, src="Weekly"):
    tl = []
    t0 = now.replace(minute=0, second=0, microsecond=0)
    order = [p["name"] for p in _PEOPLE]
    for i in range(6):
        nm = order[i % 3]
        tl.append({"start": iso(t0 + timedelta(days=7 * i)), "end": iso(t0 + timedelta(days=7 * (i + 1))), "user_id": _PEOPLE[i % 3]["id"], "name": nm,
                   "source": "override" if (sid.endswith("1") and i == 1) else src})
    return {"id": sid, "name": name, "tz": tz, "description": None, "layers": layers,
            "on_call_now": {"user_id": _PEOPLE[0]["id"], "name": now_name, "source": src}, "timeline": tl,
            "overrides": [{"id": "ov1", "user_id": _PEOPLE[2]["id"], "starts_at": iso(now + timedelta(days=7)), "ends_at": iso(now + timedelta(days=8))}]}
_SCHEDS = [_sched("5c000000-0000-4000-8000-0000000000a1", "Platform primary", "Asia/Kolkata",
                  [{"name": "Weekly", "rotation": "weekly", "shift_hours": None, "members": [{"id": p["id"], "name": p["name"]} for p in _PEOPLE]}], "Ana Rao"),
           _sched("5c000000-0000-4000-8000-0000000000a2", "Data team business hours", "Europe/London",
                  [{"name": "Office", "rotation": "daily", "shift_hours": None, "members": [{"id": p["id"], "name": p["name"]} for p in _PEOPLE[1:]]}], "Ben Ito", "Office")]
@app.get("/api/v1/oncall/people")
def oc_people(): return _PEOPLE
@app.get("/api/v1/oncall/schedules")
def oc_scheds(): return [{k: v for k, v in s.items() if k not in ("timeline", "overrides")} for s in _SCHEDS]
@app.get("/api/v1/oncall/schedules/{sid}")
def oc_sched(sid: str): return next(s for s in _SCHEDS if s["id"] == sid)
@app.get("/api/v1/oncall/policies")
def oc_policies(): return [{"id": "5d000000-0000-4000-8000-0000000000b1", "name": "Platform", "repeat_count": 1, "delivery_channel_id": "ch-slack",
    "steps": [{"delay_min": 15, "targets": [{"type": "schedule", "id": _SCHEDS[0]["id"]}]}, {"delay_min": 15, "targets": [{"type": "user", "id": _PEOPLE[2]["id"]}]}]}]
@app.get("/api/v1/oncall/escalations")
def oc_runs(): return [{"id": "5e000000-0000-4000-8000-0000000000c1", "status": "active", "step": 1, "cycle": 0, "next_at": iso(now + timedelta(minutes=11)),
    "job_name": "customer-report-generator", "condition": "failed", "policy": "Platform", "incident_id": None, "job_id": JOBS[3]["id"],
    "history": [{"at": iso(now - timedelta(minutes=4)), "step": 1, "cycle": 1, "paged": ["Ana Rao"], "notes": []}], "created_at": iso(now - timedelta(minutes=4))}]
@app.get("/api/v1/alerts/maintenance")   # R63
def maintenance(): return [
    {"id": "6f1c2d3e-0000-4000-8000-0000000000d1", "name": "Sunday database patching", "scope": {"tags": ["db"]}, "starts_at": "2026-09-06T20:30:00Z",
     "ends_at": "2026-09-06T22:30:00Z", "tz": "Asia/Kolkata", "rrule": "FREQ=WEEKLY;BYDAY=SU", "active_now": False, "current_end": None,
     "next_start": "2026-10-11T20:30:00Z", "next_end": "2026-10-11T22:30:00Z"},
    {"id": "6f1c2d3e-0000-4000-8000-0000000000d2", "name": "Cluster upgrade", "scope": {}, "starts_at": "2026-10-05T11:00:00Z", "ends_at": "2026-10-05T15:00:00Z",
     "tz": "UTC", "rrule": None, "active_now": True, "current_end": "2026-10-05T15:00:00Z", "next_start": None, "next_end": None}]
@app.get("/api/v1/metric-exports")   # R58
def metric_exports(): return [{"id": "6f1c2d3e-0000-4000-8000-0000000000c1", "kind": "datadog", "name": "Datadog", "site": "datadoghq.eu", "enabled": True,
                               "points_total": 482113, "last_success_at": "2026-10-05T12:01:00Z", "last_error": None, "last_error_at": None, "next_attempt_at": "2026-10-05T12:02:00Z"}]
@app.get("/api/v1/audit-streams")   # R57
def audit_streams(): return [{"id": "6f1c2d3e-0000-4000-8000-0000000000b1", "kind": "splunk_hec", "name": "Security SIEM", "host": "splunk.acme.com", "enabled": True,
                              "delivered_total": 18342, "pending": 0, "last_success_at": "2026-10-05T11:58:02Z", "last_error": None, "last_error_at": None,
                              "next_attempt_at": "2026-10-05T11:58:02Z", "created_at": "2026-09-01T09:00:00Z"},
                             {"id": "6f1c2d3e-0000-4000-8000-0000000000b2", "kind": "webhook", "name": "Log pipeline", "host": "logs.acme.com", "enabled": True,
                              "delivered_total": 9211, "pending": 37, "last_success_at": "2026-10-05T11:41:10Z", "last_error": "destination answered HTTP 503",
                              "last_error_at": "2026-10-05T11:57:40Z", "next_attempt_at": "2026-10-05T12:02:40Z", "created_at": "2026-09-14T09:00:00Z"}]
@app.get("/api/v1/sso/scim-groups")   # R56
def scim_groups(): return [{"id": "6f1c2d3e-0000-4000-8000-0000000000a1", "display_name": "JobWatch Admins", "role": "admin", "members": 2, "updated_at": "2026-10-05T09:00:00Z"},
                           {"id": "6f1c2d3e-0000-4000-8000-0000000000a2", "display_name": "SRE", "role": "sre", "members": 7, "updated_at": "2026-10-05T09:00:00Z"},
                           {"id": "6f1c2d3e-0000-4000-8000-0000000000a3", "display_name": "All Engineering", "role": None, "members": 42, "updated_at": "2026-10-05T09:00:00Z"}]
@app.get("/api/v1/sso/scim-tokens")   # R44
def scim_tokens(): return {"base_url": "https://api.jobwatch.example/scim/v2", "tokens": [{"id": "6f1c2d3e-0000-4000-8000-000000000001", "name": "Okta", "prefix": "jwscim_1a2b3c4d", "created_at": "2026-10-01T09:10:00Z", "last_used_at": "2026-10-01T11:42:00Z"}]}
@app.get("/api/v1/sso")   # R43
def sso(): return {"configured": True, "protocol": "oidc", "display_name": "Okta", "enabled": True, "enforce": False, "default_role": "developer",
                   "config": {"issuer": "https://acme.okta.com", "client_id": "0oa1b2c3"}, "has_client_secret": True, "updated_at": "2026-10-01T09:00:00Z",
                   "redirect_uri": "https://sso.jobwatch.example/realms/cronsentinel/broker/org-o/endpoint",
                   "domains": [{"id": "d1", "domain": "acme.com", "verified_at": "2026-10-01T09:05:00Z", "txt_name": "_jobwatch-verify.acme.com", "txt_value": "jobwatch-verify=abc"},
                               {"id": "d2", "domain": "acme.io", "verified_at": None, "txt_name": "_jobwatch-verify.acme.io", "txt_value": "jobwatch-verify=def"}]}
@app.post("/api/v1/jobs/schedule/preview")
def prev(expr: str, tz: str = "UTC"):
    from cronsentinel import schedule
    return {"expr": expr, "human": schedule.human(expr), "next": [iso(x) for x in schedule.next_runs(expr, tz, 5)]}
# R67: import preview (Sentry Crons); the other sources answer the same shape
def _import_preview(source: str, body: dict):
    rows = [("Nightly backup", "imported", None, "0 2 * * *", True), ("Queue drain", "converted", "'every 5 minutes' became '*/5 * * * *' with extra grace 300 s; review the schedule", "*/5 * * * *", True),
            ("Monthly invoices", "converted", "'every 1 month' became '0 0 1 * *' with extra grace 1 day; review the schedule", "0 0 1 * *", True),
            ("Odd interval", "needs_schedule", "'every 90 minutes' has no cron equivalent; imported without a schedule — set one to detect missed runs", None, True),
            ("Noisy", "imported", "muted in Sentry; imported active — pause it in JobWatch to keep it quiet; Sentry waited for 3 failed check-ins before alerting; JobWatch alerts on the first", "0 * * * *", True),
            ("Old report", "exists", "a job with this name already exists in the workspace; left unchanged", "0 * * * *", False)]
    dry = body.get("dry_run", True)
    return {"dry_run": dry, "warnings": ["project batch has 2 active client keys; check-ins must use the first one (…ffff) to reach JobWatch"] if source == "sentry" else [],
            "ping_host_change": "SDKs: change the host in the DSN you use for crons, e.g. https://<key>@o1.ingest.sentry.io/<project id> → https://<key>@ingest.example.com/sentry/<project id>. HTTP check-ins: replace https://<your Sentry ingest host>/api/ with https://ingest.example.com/sentry/api/ (status=in_progress|ok|error and check_in_id keep working).",
            "results": [{"name": n, "status": s, "note": note, "job_id": None if dry or s == "exists" else str(uuid.uuid4()), "schedule_expr": e, "kept_ping_url": k and s != "exists", "new_ping_url": None} for n, s, note, e, k in rows]}
@app.post("/api/v1/import/sentry")
def import_sentry(body: dict): return _import_preview("sentry", body)
@app.post("/api/v1/import/cronitor")
def import_cronitor(body: dict): return _import_preview("cronitor", body)
@app.post("/api/v1/import/healthchecks")
def import_healthchecks(body: dict): return _import_preview("healthchecks", body)
# R69: team, security and invitations
_MEMBERS = [{"user_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, e)), "email": e, "name": n, "role": r, "joined_at": iso(now - timedelta(days=d)), "managed_by_directory": m}
            for e, n, r, d, m in [("le@finspot.in", "LE", "owner", 210, False), ("ana@acme.io", "Ana Rao", "admin", 180, False), ("ben@acme.io", "Ben Ito", "sre", 120, True),
                                  ("chen@acme.io", "Chen Li", "developer", 60, True), ("dev@acme.io", "Devi Nair", "viewer", 12, False)]]
_INVITES = [{"id": "9b000000-0000-4000-8000-000000000001", "email": "farah@acme.io", "role": "developer", "created_at": iso(now - timedelta(days=2)), "expires_at": iso(now + timedelta(days=5)), "status": "pending", "invite_url": None}]
_SECURITY = {"require_mfa": False, "mfa_checkable": True, "sso_enforced": False}
@app.get("/api/v1/org/members")
def members(): return _MEMBERS
@app.patch("/api/v1/org/members/{uid}")
def member_role(uid: str, body: dict):
    m = next(x for x in _MEMBERS if x["user_id"] == uid); m["role"] = body["role"]; return m
@app.post("/__seed/member", status_code=201)   # e2e only: add a throwaway member so each project can remove its own
def seed_member(body: dict):
    m = {"user_id": str(uuid.uuid4()), "email": body["email"], "name": body.get("name"), "role": "viewer", "joined_at": iso(now - timedelta(days=3)), "managed_by_directory": False}
    _MEMBERS.append(m); return m
@app.delete("/api/v1/org/members/{uid}", status_code=204)
def member_remove(uid: str): _MEMBERS[:] = [x for x in _MEMBERS if x["user_id"] != uid]
@app.get("/api/v1/org/invites")
def invites(): return _INVITES
@app.post("/api/v1/org/invites", status_code=201)
def invite(body: dict):
    inv = {"id": str(uuid.uuid4()), "email": body["email"].lower(), "role": body.get("role", "developer"), "created_at": iso(now), "expires_at": iso(now + timedelta(days=7)), "status": "pending",
           "invite_url": "http://localhost:3000/signup?invite=demo-invite-token-0123456789abcdef"}
    _INVITES.insert(0, {**inv, "invite_url": None}); return inv
@app.delete("/api/v1/org/invites/{iid}", status_code=204)
def invite_revoke(iid: str):
    for x in _INVITES:
        if x["id"] == iid: x["status"] = "revoked"
@app.get("/api/v1/org/security")
def security(): return _SECURITY
@app.put("/api/v1/org/security")
def security_put(body: dict): _SECURITY["require_mfa"] = bool(body["require_mfa"]); return _SECURITY
@app.get("/auth/invite/{token}")
def invite_preview(token: str):
    from fastapi import HTTPException
    if not token.startswith("demo-invite-token"): raise HTTPException(404, "invitation not found")
    return {"email": "farah@acme.io", "role": "developer", "organization": "Acme", "invited_by": "Ana Rao", "expired": False, "expires_at": iso(now + timedelta(days=5))}
@app.post("/public/contact", status_code=202)
def contact(body: dict): return {"ok": True}
