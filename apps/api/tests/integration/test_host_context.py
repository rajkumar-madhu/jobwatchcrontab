"""R70 — host context: the agent's heartbeat carries host facts; the job, agent and run pages read
them back together with the host's metrics, and a run's output can be downloaded as a file."""
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import pytest
from sqlalchemy import text

from cronsentinel import hostcontext


@pytest.fixture
def env(org):
    from fastapi.testclient import TestClient

    from cronsentinel.auth import generate_api_key, hash_secret
    from cronsentinel.db import system_session
    from cronsentinel.ingest_main import app as ingest
    from cronsentinel.main import app
    prefix, raw = generate_api_key()
    key = "csa_" + uuid.uuid4().hex + uuid.uuid4().hex
    with system_session() as s:
        s.execute(text("INSERT INTO api_keys (org_id, name, prefix, key_hash, role) VALUES (:o,'d',:p,:h,'devops')"), {"o": org["id"], "p": prefix, "h": hash_secret(raw)})
        aid = s.execute(text("""INSERT INTO agents (org_id, kind, host_id, name, version, status, key_hash, key_prefix, heartbeat_interval_s)
            VALUES (:o, 'linux', :h, 'prod-db-01', '0.2.0', 'active', :kh, :kp, 60) RETURNING id"""),
            {"o": org["id"], "h": f"h-{uuid.uuid4().hex[:6]}", "kh": hash_secret(key), "kp": key[:12]}).scalar()
        sid = s.execute(text("INSERT INTO servers (org_id, agent_id, hostname) VALUES (:o, :a, 'prod-db-01') RETURNING id"), {"o": org["id"], "a": aid}).scalar()
        tok = uuid.uuid4().hex
        jid = s.execute(text("""INSERT INTO jobs (org_id, workspace_id, name, kind, heartbeat_token_hash, heartbeat_token_hint, server_id, status, schedule_expr, tz)
            VALUES (:o, :w, 'pg-backup', 'cron', encode(sha256(convert_to(CAST(:t AS text),'UTF8')),'hex'), right(CAST(:t AS text),4), :s, 'failed', '0 2 * * *', 'UTC') RETURNING id"""),
            {"o": org["id"], "w": org["ws"], "t": tok, "s": sid}).scalar()
        ping_tok = uuid.uuid4().hex
        pj = s.execute(text("""INSERT INTO jobs (org_id, workspace_id, name, kind, heartbeat_token_hash, heartbeat_token_hint, status)
            VALUES (:o, :w, 'ping-only', 'heartbeat', encode(sha256(convert_to(CAST(:t AS text),'UTF8')),'hex'), right(CAST(:t AS text),4), 'healthy') RETURNING id"""),
            {"o": org["id"], "w": org["ws"], "t": ping_tok}).scalar()
    ingest.state.js = None
    yield {"api": TestClient(app, raise_server_exceptions=False), "ingest": TestClient(ingest, raise_server_exceptions=False),
           "h": {"X-API-Key": raw}, "ah": {"X-Agent-Id": str(aid), "X-Agent-Key": key}, "agent": aid, "server": sid, "job": jid, "tok": tok, "ping_job": pj}
    with system_session() as s:
        s.execute(text("DELETE FROM host_metrics WHERE server_id=:s"), {"s": sid})
        s.execute(text("DELETE FROM agents WHERE id=:a"), {"a": aid})


FACTS = {"os": "Ubuntu 24.04.1 LTS", "kernel": "6.8.0-45-generic", "arch": "amd64", "cpus": 4, "mem_total_mb": 7950, "disk_total_gb": 98.3,
         "uptime_s": 864000, "load5": 1.2, "load15": 0.9, "timezone": "Asia/Kolkata", "virt": "vm"}


def test_heartbeat_stores_whitelisted_facts(env):
    r = env["ingest"].post("/agent/v1/heartbeat", headers=env["ah"], json={
        "version": "0.2.0", "agent_ts": datetime.now(UTC).isoformat(), "heartbeat_interval_s": 60,
        "host": {**FACTS, "ssh_private_key": "nope", "cpus": "four", "os": "x" * 500}})
    assert r.status_code == 200, r.text
    h = env["api"].get(f"/api/v1/jobs/{env['job']}/host", headers=env["h"]).json()
    facts = h["context"]["server"]["facts"]
    assert "ssh_private_key" not in facts and "cpus" not in facts          # unknown key, wrong type
    assert len(facts["os"]) == 120 and facts["kernel"] == FACTS["kernel"] and facts["disk_total_gb"] == 98.3
    assert h["context"]["server"]["facts_updated_at"] is not None


def test_non_finite_facts_do_not_break_the_heartbeat(env):
    """R72: Python's JSON parser accepts NaN/Infinity. int(inf) raised and json.dumps(inf) is not
    valid JSON for Postgres, so one bad number failed the whole heartbeat and the agent went offline."""
    body = b'{"agent_ts": "%s", "host": {"cpus": Infinity, "load5": NaN, "uptime_s": 1e400, "os": "Debian 12", "mem_total_mb": 1e20}}' % datetime.now(UTC).isoformat().encode()
    r = env["ingest"].post("/agent/v1/heartbeat", headers={**env["ah"], "Content-Type": "application/json"}, content=body)
    assert r.status_code == 200, r.text
    facts = env["api"].get(f"/api/v1/jobs/{env['job']}/host", headers=env["h"]).json()["context"]["server"]["facts"]
    assert facts == {"os": "Debian 12"}, facts
    assert hostcontext.clean_facts({"cpus": float("inf"), "load5": float("nan"), "mem_total_mb": 1e20}) is None


def test_facts_are_rewritten_only_when_they_change(env):
    from cronsentinel.db import system_session
    def hb(f=FACTS):
        return env["ingest"].post("/agent/v1/heartbeat", headers=env["ah"], json={"agent_ts": datetime.now(UTC).isoformat(), "host": f})
    def stamp():
        with system_session() as s:
            return s.execute(text("SELECT facts_updated_at FROM servers WHERE id=:s"), {"s": env["server"]}).scalar()
    assert hb().status_code == 200
    first = stamp()
    assert hb().status_code == 200
    assert stamp() == first, "an unchanged heartbeat must not rewrite servers.facts"
    assert hb({**FACTS, "kernel": "6.8.0-46-generic"}).status_code == 200
    assert stamp() > first


def test_agent_list_carries_the_same_state_as_the_detail(env):
    from cronsentinel.db import system_session
    with system_session() as s:
        s.execute(text("UPDATE agents SET last_seen_at = now() - interval '4 minutes' WHERE id=:a"), {"a": env["agent"]})
    row = next(a for a in env["api"].get("/api/v1/agents", headers=env["h"]).json() if a["id"] == str(env["agent"]))
    assert row["state"] == "offline" and row["heartbeat_interval_s"] == 60
    assert env["api"].get(f"/api/v1/agents/{env['agent']}", headers=env["h"]).json()["state"] == "offline"


def test_job_host_has_agent_state_latest_sample_series_and_sibling_jobs(env):
    env["ingest"].post("/agent/v1/heartbeat", headers=env["ah"], json={"agent_ts": datetime.now(UTC).isoformat(), "host": FACTS})
    now = datetime.now(UTC)
    for i in range(6):   # six samples over the last hour, the last one hot
        env["ingest"].post("/agent/v1/metrics", headers=env["ah"], json={"ts": (now - timedelta(minutes=50 - i * 10)).isoformat(), "cpu_pct": 10 + i,
                           "mem_pct": 40, "load1": 0.5, "disk_pct": 60 + i * 6, "inode_pct": 3, "io_wait_pct": 1})
    r = env["api"].get(f"/api/v1/jobs/{env['job']}/host", headers=env["h"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "agent"
    c = d["context"]
    assert c["server"]["hostname"] == "prod-db-01" and c["server"]["facts"]["cpus"] == 4
    assert c["agent"]["state"] == "online" and c["agent"]["version"] == "0.2.0" and c["agent"]["heartbeat_interval_s"] == 60
    assert c["latest"]["disk_pct"] == 90.0 and c["latest"]["io_wait_pct"] == 1.0
    assert 1 <= len(c["series"]) <= 6 and all("ts" in pt for pt in c["series"])
    assert [j["name"] for j in c["jobs"]] == ["pg-backup"]


def test_agent_goes_offline_after_three_intervals(env):
    from cronsentinel.db import system_session
    with system_session() as s:
        s.execute(text("UPDATE agents SET last_seen_at = now() - interval '4 minutes' WHERE id=:a"), {"a": env["agent"]})
    a = env["api"].get(f"/api/v1/agents/{env['agent']}", headers=env["h"])
    assert a.status_code == 200, a.text
    assert a.json()["state"] == "offline" and a.json()["context"]["agent"]["state"] == "offline"
    assert a.json()["jobs"] == 1 and a.json()["context"]["jobs"][0]["name"] == "pg-backup"
    assert env["api"].get(f"/api/v1/agents/{uuid.uuid4()}", headers=env["h"]).status_code == 404


def test_ping_only_job_reports_last_host_and_no_context(env):
    from cronsentinel.db import system_session
    with system_session() as s:
        s.execute(text("INSERT INTO executions (id, org_id, job_id, status, scheduled_ts, host) VALUES (:e, :o, :j, 'success', now(), 'worker-7')"),
                  {"e": f"p-{uuid.uuid4().hex}", "o": s.execute(text("SELECT org_id FROM jobs WHERE id=:j"), {"j": env["ping_job"]}).scalar(), "j": env["ping_job"]})
    d = env["api"].get(f"/api/v1/jobs/{env['ping_job']}/host", headers=env["h"]).json()
    assert d == {"job_id": str(env["ping_job"]), "source": "ping", "last_host": "worker-7", "context": None}


def test_run_detail_carries_host_metrics_during_the_run_exit_meaning_and_download(env):
    from cronsentinel.db import system_session
    env["ingest"].post("/agent/v1/heartbeat", headers=env["ah"], json={"agent_ts": datetime.now(UTC).isoformat(), "host": FACTS})
    start = datetime.now(UTC) - timedelta(minutes=10)
    for off, disk in ((-20, 70), (-2, 96), (3, 97), (20, 50)):   # only the middle two fall inside start-5m .. end+5m
        env["ingest"].post("/agent/v1/metrics", headers=env["ah"], json={"ts": (start + timedelta(minutes=off)).isoformat(), "cpu_pct": 50, "mem_pct": 80, "load1": 7.1, "disk_pct": disk})
    eid = f"r-{uuid.uuid4().hex}"
    r = env["ingest"].post("/agent/v1/events", headers=env["ah"], json={"events": [
        {"job_token": env["tok"], "kind": "start", "execution_id": eid, "sequence": 0, "agent_ts": start.isoformat(), "host": "prod-db-01"},
        {"job_token": env["tok"], "kind": "fail", "execution_id": eid, "sequence": 1, "agent_ts": (start + timedelta(minutes=1)).isoformat(), "exit_code": 137,
         "duration_ms": 60000, "host": "prod-db-01", "stdout_tail": "dumping schema public\n", "stderr_tail": "pg_dump: error: out of memory\nKilled\n"}]})
    assert r.status_code == 200 and r.json()["accepted"] == 2, r.text
    d = env["api"].get(f"/api/v1/executions/{eid}", headers=env["h"])
    assert d.status_code == 200, d.text
    d = d.json()
    assert d["execution"]["exit_code"] == 137 and "OOM" in d["exit_meaning"]
    assert d["logs"]["stderr"].startswith("pg_dump") and d["log_bytes"]["stderr"] == len(d["logs"]["stderr"].encode())
    assert d["host"]["hostname"] == "prod-db-01" and d["host"]["facts"]["os"] == FACTS["os"]
    assert [pt["disk_pct"] for pt in d["host"]["metrics_during"]] == [96.0, 97.0]
    both = env["api"].get(f"/api/v1/executions/{eid}/logs", headers=env["h"])
    assert both.status_code == 200 and both.headers["content-type"].startswith("text/plain") and "attachment" in both.headers["content-disposition"]
    assert "dumping schema" in both.text and "----- stderr -----" in both.text and "out of memory" in both.text
    assert env["api"].get(f"/api/v1/executions/{eid}/logs?stream=stderr", headers=env["h"]).text == "pg_dump: error: out of memory\nKilled\n"
    assert env["api"].get(f"/api/v1/executions/{eid}/logs?stream=nope", headers=env["h"]).status_code == 422
    # R72: client-chosen ids must not reach the header raw (non-ASCII raised; CR/LF would be header injection)
    for odd in ("ரன்-" + uuid.uuid4().hex[:6], "a\r\nX-Injected: 1", 'q"uote' + uuid.uuid4().hex[:4]):
        with system_session() as s:
            s.execute(text("INSERT INTO executions (id, org_id, job_id, status, scheduled_ts) VALUES (:e, :o, :j, 'success', now())"),
                      {"e": odd, "o": s.execute(text("SELECT org_id FROM jobs WHERE id=:j"), {"j": env["job"]}).scalar(), "j": env["job"]})
        r = env["api"].get(f"/api/v1/executions/{quote(odd, safe='')}/logs", headers=env["h"])
        assert r.status_code == 200, (odd, r.status_code, r.text)
        cd = r.headers["content-disposition"]
        assert "\r" not in cd and "\n" not in cd and cd.isascii() and "filename*=UTF-8''" in cd and 'filename="run-' in cd
    assert env["api"].get(f"/api/v1/executions/{uuid.uuid4().hex}/logs", headers=env["h"]).status_code == 404


def test_exit_meaning_table():
    assert hostcontext.exit_meaning(None) is None
    assert hostcontext.exit_meaning(0).startswith("Completed")
    assert "not found" in hostcontext.exit_meaning(127)
    assert hostcontext.exit_meaning(150) == "Killed by signal 22."
    assert "Program-specific" in hostcontext.exit_meaning(42)
    assert hostcontext.clean_facts({"cpus": True, "os": "  ", "load5": -1, "mem_total_mb": 12.9}) == {"mem_total_mb": 12}
    assert hostcontext.clean_facts("x") is None and hostcontext.clean_facts({}) is None
