"""R68: unusual runs, learned from each job's history — through the real ingest path, the processor,
the exec-processor's publish decision and the rule engine."""
import uuid
from datetime import UTC, datetime
from unittest import mock

import pytest
from sqlalchemy import text

NORMAL = [(1_200_000 + i * 7_000, 4.2e9 + i * 1e7) for i in range(12)]     # ~20 min, ~4.2 GB


@pytest.fixture
def env(org):
    from fastapi.testclient import TestClient

    from cronsentinel.auth import generate_api_key, hash_secret
    from cronsentinel.db import system_session
    from cronsentinel.ingest_main import app as ingest
    from cronsentinel.main import app
    prefix, raw = generate_api_key()
    with system_session() as s:
        s.execute(text("INSERT INTO api_keys (org_id, name, prefix, key_hash, role) VALUES (:o,'d',:p,:h,'devops')"), {"o": org["id"], "p": prefix, "h": hash_secret(raw)})
    ingest.state.js = None
    return TestClient(app, raise_server_exceptions=False), TestClient(ingest, raise_server_exceptions=False), {"X-API-Key": raw}


def _job(api, h, org, **kw):
    r = api.post("/api/v1/jobs", headers=h, json={"workspace_id": str(org["ws"]), "name": f"bk-{uuid.uuid4().hex[:6]}", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _ping(ingest, tok, dur, size):
    body = {"status": "success", "exit_code": 0, "duration_ms": dur}
    if size is not None:
        body["metrics"] = {"size_bytes": size}
    assert ingest.post(f"/api/v1/heartbeat/{tok}", json=body).status_code == 200


def _history(ingest, tok):
    for dur, size in NORMAL:
        _ping(ingest, tok, dur, size)


def _latest(api, h, jid):
    """The run that finished last. The API orders by start time, and a ping-only run "started"
    duration_ms before it finished, so a 3-second run sorts above a 20-minute one sent earlier."""
    runs = api.get(f"/api/v1/jobs/{jid}/executions", headers=h, params={"limit": 200}).json()
    return max(runs, key=lambda r: r["agent_ts_end"] or "")


def test_defaults_and_settings_round_trip(env, org):
    api, _, h = env
    j = _job(api, h, org)
    assert j["anomaly_sensitivity"] == "normal" and j["anomaly_action"] == "warn"
    r = api.patch(f"/api/v1/jobs/{j['id']}", headers=h, json={"anomaly_sensitivity": "high", "anomaly_action": "fail"}).json()
    assert r["anomaly_sensitivity"] == "high" and r["anomaly_action"] == "fail"
    assert api.patch(f"/api/v1/jobs/{j['id']}", headers=h, json={"anomaly_sensitivity": "extreme"}).status_code == 422
    assert api.patch(f"/api/v1/jobs/{j['id']}", headers=h, json={"anomaly_action": None}).status_code == 422


def test_warn_mode_records_finding_and_keeps_the_run_successful(env, org):
    api, ingest, h = env
    j = _job(api, h, org)
    _history(ingest, j["heartbeat_token"])
    assert _latest(api, h, j["id"])["anomalies"] == []
    _ping(ingest, j["heartbeat_token"], 3_000, 4.2e9)                     # 3 seconds: it did nothing
    run = _latest(api, h, j["id"])
    assert run["status"] == "success"
    assert [a["kind"] for a in run["anomalies"]] == ["fast"] and "it may have done nothing" in run["anomalies"][0]["message"]
    _ping(ingest, j["heartbeat_token"], 1_210_000, 1_200)                 # normal length, almost no output
    run = _latest(api, h, j["id"])
    assert run["status"] == "success" and run["anomalies"][0]["message"] == "size_bytes was 1.2 KB; usually 4.3 GB — suspiciously small"
    assert api.get(f"/api/v1/jobs/{j['id']}", headers=h).json()["status"] in ("healthy", "recovered")
    # flagged runs are kept out of the baseline: ten more tiny outputs are still flagged each time
    for _ in range(10):
        _ping(ingest, j["heartbeat_token"], 1_210_000, 1_200)
    assert _latest(api, h, j["id"])["anomalies"], "an unusual run must not become the new normal"


def test_fail_mode_makes_the_run_a_failure(env, org):
    api, ingest, h = env
    j = _job(api, h, org, anomaly_action="fail")
    _history(ingest, j["heartbeat_token"])
    _ping(ingest, j["heartbeat_token"], 4_800_000, 4.2e9)                 # 80 minutes instead of ~20
    run = _latest(api, h, j["id"])
    assert run["status"] == "failed" and run["anomalies"][0]["kind"] == "slow"
    assert api.get(f"/api/v1/jobs/{j['id']}", headers=h).json()["status"] == "failed"


def test_off_and_run_checks_take_precedence(env, org):
    api, ingest, h = env
    off = _job(api, h, org, anomaly_sensitivity="off")
    _history(ingest, off["heartbeat_token"])
    _ping(ingest, off["heartbeat_token"], 3_000, 1)
    assert _latest(api, h, off["id"])["anomalies"] == [] and _latest(api, h, off["id"])["status"] == "success"
    checked = _job(api, h, org, assertions=["metric.size_bytes > 1000"])
    _history(ingest, checked["heartbeat_token"])
    _ping(ingest, checked["heartbeat_token"], 1_200_000, 10)
    run = _latest(api, h, checked["id"])
    assert run["status"] == "failed" and run["assertion_failures"] and run["anomalies"] == []   # one reason, not two


def _ev(org_id, job_id, dur, size):
    return {"org_id": str(org_id), "job_id": str(job_id), "kind": "success", "execution_id": None, "sequence": 0, "agent_ts": None,
            "server_ts": datetime.now(UTC).isoformat(), "duration_ms": dur, "exit_code": 0, "host": "db-01",
            "stdout_tail": None, "stderr_tail": None, "meta": {}, "metrics": {"size_bytes": size}}


def test_rule_engine_fires_anomaly_once_per_unusual_run(env, org):
    api, ingest, h = env
    from cronsentinel.alerting import engine
    from cronsentinel.alerting.context import build, subject
    from cronsentinel.db import system_session
    from cronsentinel.workers.exec_processor import handle_one
    j = _job(api, h, org)
    assert ingest.post(f"/api/v1/heartbeat/{j['heartbeat_token']}", json={"status": "fail", "exit_code": 1}).status_code == 200
    _history(ingest, j["heartbeat_token"])                                # one failure + 12 successes: below a 100 % SLA
    _ping(ingest, j["heartbeat_token"], 1_200_000, 4.2e9)                 # a normal run settles the status
    with system_session() as s:
        ch = s.execute(text("INSERT INTO notification_channels (org_id, name, kind, config_enc) VALUES (:o, 'hook', 'webhook', '\\x00') RETURNING id"), {"o": org["id"]}).scalar()
        for cond in ("anomaly", "failed", "recovered", "sla_breach"):
            s.execute(text("INSERT INTO alert_rules (org_id, name, condition, scope, severity, channel_ids, enabled) VALUES (:o, :n, :c, '{}', 'medium', ARRAY[:ch]::uuid[], true)"),
                      {"o": org["id"], "n": f"r-{cond}", "c": cond, "ch": ch})
        s.execute(text("UPDATE jobs SET sla_target=100 WHERE id=:j"), {"j": j["id"]})   # would "breach" if anything but anomaly fired
        normal = handle_one(s, _ev(org["id"], j["id"], 1_215_000, 4.25e9))
        unusual = handle_one(s, _ev(org["id"], j["id"], 2_000, 4.2e9))
    assert normal is None                                                   # unchanged status, nothing unusual: not published
    assert unusual and unusual["prev_status"] == unusual["new_status"] and unusual["anomalies"][0]["kind"] == "fast"
    sent = []
    with mock.patch.object(engine.send_notification, "delay", side_effect=lambda *a: sent.append(a)):
        engine.handle_status_change(unusual)
        engine.handle_status_change(unusual)                               # redelivery
    assert len(sent) >= 1
    org_id, ch_id, dk, incident, payload = sent[0]
    assert payload["condition"] == "anomaly" and payload["anomalies"][0]["kind"] == "fast" and incident is None
    assert dk.endswith(f":anomaly:{unusual['execution_id']}")
    assert {p[4]["condition"] for p in sent} == {"anomaly"}                # no failed / recovered / sla_breach noise
    assert {p[2] for p in sent} == {dk}                                    # the redelivery has the same key: the notifier ledger drops it
    with system_session() as s:
        assert s.execute(text("SELECT count(*) FROM incidents WHERE org_id=:o"), {"o": org["id"]}).scalar() == 0
        ctx = build(s, str(org["id"]), payload)
    subj = subject(payload, ctx)
    assert subj.startswith("◆ [MEDIUM] UNUSUAL RUN · ") and "unusual run: finished in 2.0 s; usually 20 min" in subj


def test_unusual_runs_feed(env, org):   # R69: the overview's "Unusual runs" widget
    api, ingest, h = env
    j = _job(api, h, org)
    _history(ingest, j["heartbeat_token"])
    assert api.get("/api/v1/analytics/unusual-runs", headers=h).json() == []
    _ping(ingest, j["heartbeat_token"], 3_000, 4.2e9)
    feed = api.get("/api/v1/analytics/unusual-runs", headers=h).json()
    assert len(feed) == 1 and feed[0]["job_name"] == j["name"] and feed[0]["status"] == "success"
    assert feed[0]["anomalies"][0]["kind"] == "fast" and feed[0]["finished_at"]
    assert api.get("/api/v1/analytics/unusual-runs", headers=h, params={"days": 0}).status_code == 422
