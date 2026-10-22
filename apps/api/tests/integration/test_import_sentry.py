"""R67: Sentry Crons import + Sentry-compatible check-ins.

The import runs against tests/fakes/sentry.py (written to Sentry's serializers and paging code). The
check-ins are sent three ways: Sentry's HTTP check-in paths, hand-built envelopes, and the real
sentry-python SDK with only the DSN host changed — gzip and brotli transports both."""
import gzip
import json
import socket
import threading
import time
import uuid

import pytest
import uvicorn
from sqlalchemy import text

from cronsentinel.importers import sentry as se
from tests.fakes import sentry as fake

KEY = fake.BACKEND_KEY
PID = fake.BACKEND["id"]


def _serve(app, lifespan="auto"):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan=lifespan))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def fake_sentry():
    server, url = _serve(fake.app)
    yield url
    server.should_exit = True


@pytest.fixture
def private_ok(monkeypatch):
    from cronsentinel.config import settings
    monkeypatch.setattr(settings, "outbound_allow_private", True)      # the fake runs on localhost


@pytest.fixture
def clients(org, private_ok):
    from fastapi.testclient import TestClient

    from cronsentinel.auth import generate_api_key, hash_secret
    from cronsentinel.db import system_session
    from cronsentinel.ingest_main import app as ingest
    from cronsentinel.main import app
    prefix, raw = generate_api_key()
    with system_session() as s:
        s.execute(text("UPDATE organizations SET plan='business' WHERE id=:o"), {"o": org["id"]})
        s.execute(text("INSERT INTO api_keys (org_id, name, prefix, key_hash, role) VALUES (:o,'a',:p,:h,'admin')"), {"o": org["id"], "p": prefix, "h": hash_secret(raw)})
    ingest.state.js = None
    return TestClient(app, raise_server_exceptions=False), TestClient(ingest, raise_server_exceptions=False), {"X-API-Key": raw}


def _req(org, **kw):
    return {"auth_token": fake.READ_TOKEN, "organization": fake.ORG, "workspace_id": str(org["ws"]), **kw}


def _execs(org_id, name):
    from cronsentinel.db import system_session
    with system_session() as s:
        return s.execute(text("""SELECT e.status::text, e.duration_ms, e.meta FROM executions e JOIN jobs j ON j.id=e.job_id
            WHERE j.org_id=:o AND j.name=:n ORDER BY e.server_received_ts"""), {"o": org_id, "n": name}).all()


# ---- mapping -------------------------------------------------------------------------------------

def test_schedule_translation():
    assert se.translate_schedule("crontab", "0 2 * * *") == ("0 2 * * *", 0, None)
    assert se.translate_schedule("interval", [5, "minute"])[:2] == ("*/5 * * * *", 300)
    assert se.translate_schedule("interval", [1, "hour"])[0] == "0 * * * *"
    assert se.translate_schedule("interval", [1, "week"])[0] == "0 0 * * 0"
    assert se.translate_schedule("interval", [1, "month"])[0] == "0 0 1 * *"
    assert se.translate_schedule("interval", [1, "year"])[0] == "0 0 1 1 *"
    assert se.translate_schedule("interval", [90, "minute"])[0] is None
    assert se.translate_schedule("interval", [2, "month"])[0] is None
    assert se.translate_schedule("crontab", "not cron")[0] is None
    assert se.translate_schedule(None, None) == (None, 0, "no schedule in Sentry")


def test_mapping_rules():
    m = se.map_monitor(fake.MONITORS[0], KEY)
    j = m["job"]
    assert m["status"] == "imported" and j["schedule_expr"] == "0 2 * * *" and j["tz"] == "Asia/Kolkata"
    assert j["grace_s"] == 15 * 60 and j["expected_runtime_s"] == 120 * 60 and j["tags"] == ["sentry", "project:backend"]
    assert m["token"] == f"sentry:{PID}:{KEY}:nightly-backup"
    d = se.map_monitor(fake.MONITORS[1], KEY)["job"]           # nulls → Sentry defaults, interval → cron + one period
    assert d["grace_s"] == 60 + 300 and d["expected_runtime_s"] == 30 * 60 and d["tz"] == "UTC"
    assert se.map_monitor(fake.MONITORS[4], KEY)["job"]["paused"] is True                       # status disabled
    noisy = se.map_monitor(fake.MONITORS[5], KEY)["note"]
    assert "muted" in noisy and "3 failed check-ins" in noisy and "2 environments" in noisy
    assert se.map_monitor(fake.MONITORS[0], None)["token"] is None                              # no key → new URL
    assert se.map_monitor({**fake.MONITORS[0], "project": {"id": "x1", "slug": "p"}}, KEY)["token"] is None


def test_next_link():
    h = ('<https://sentry.io/api/0/organizations/acme/monitors/?&cursor=0:0:1>; rel="previous"; results="false"; cursor="0:0:1", '
         '<https://sentry.io/api/0/organizations/acme/monitors/?&cursor=0:100:0>; rel="next"; results="true"; cursor="0:100:0"')
    assert se._next_link(h).endswith("cursor=0:100:0")
    assert se._next_link(h.replace('results="true"', 'results="false"')) is None
    assert se._next_link(None) is None


# ---- fetch ---------------------------------------------------------------------------------------

def test_fetch_pages_and_reads_keys(fake_sentry, private_ok):
    fake.calls.clear()
    mons, keys, warnings = se.fetch(fake.READ_TOKEN, fake.ORG, fake_sentry)
    assert len(mons) == len(fake.MONITORS) == 106
    assert [c for c in fake.calls if c.startswith("monitors")] == ["monitors 0:0:0 project=-1", "monitors 0:100:0 project=-1"]
    assert keys == {"4505": KEY, "4506": "f" * 32}                 # revoked key skipped, first active wins
    assert any("2 active client keys" in w for w in warnings)


def test_paging_never_leaves_the_sentry_host(fake_sentry, private_ok):
    fake.FOREIGN_NEXT["on"] = True
    try:
        mons, _, _ = se.fetch(fake.READ_TOKEN, fake.ORG, fake_sentry)
    finally:
        fake.FOREIGN_NEXT["on"] = False
    assert len(mons) == 100          # stopped after the first page instead of following the link


def test_fetch_errors(fake_sentry, private_ok):
    with pytest.raises(se.ImportError_, match="rejected"):
        se.fetch("sntrys_wrong_000000000", fake.ORG, fake_sentry)
    with pytest.raises(se.ImportError_, match="org:read"):
        se.fetch(fake.NO_ORG_TOKEN, fake.ORG, fake_sentry)
    with pytest.raises(se.ImportError_, match="no organization"):
        se.fetch(fake.READ_TOKEN, "other-org", fake_sentry)
    with pytest.raises(se.ImportError_, match="organization slug"):
        se.fetch(fake.READ_TOKEN, "../evil", fake_sentry)
    _, keys, warnings = se.fetch(fake.NO_PROJECT_TOKEN, fake.ORG, fake_sentry)
    assert keys == {"4505": None, "4506": None} and all("project:read" in w for w in warnings)


def test_private_base_url_refused_by_default(clients, org, monkeypatch):
    api, _, h = clients
    from cronsentinel.config import settings
    monkeypatch.setattr(settings, "outbound_allow_private", False)
    r = api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url="http://127.0.0.1:9/"))
    assert r.status_code == 400


# ---- import + HTTP check-ins ---------------------------------------------------------------------

def test_import_then_http_checkins(fake_sentry, clients, org):
    api, ingest, h = clients
    base = f"/sentry/api/{PID}/cron/nightly-backup/{KEY}/"
    assert ingest.get(base, params={"status": "ok"}).status_code == 404       # not imported yet
    dry = api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=True)).json()
    from cronsentinel.db import system_session
    with system_session() as s:
        assert s.execute(text("SELECT count(*) FROM jobs WHERE org_id=:o"), {"o": org["id"]}).scalar() == 0
    assert len(dry["results"]) == 106 and dry["warnings"]
    r = api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=False)).json()
    by = {x["name"]: x for x in r["results"]}
    assert by["Nightly backup"]["status"] == "imported" and by["Nightly backup"]["kept_ping_url"]
    assert by["Queue drain"]["status"] == "converted" and by["Queue drain"]["schedule_expr"] == "*/5 * * * *"
    assert by["Monthly invoices"]["schedule_expr"] == "0 0 1 * *" and by["Odd interval"]["status"] == "needs_schedule"
    assert "/sentry/" in r["ping_host_change"]
    again = api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=False)).json()
    assert not any(x["job_id"] for x in again["results"])

    # query-string check-ins, paired by check_in_id, exactly as Sentry's HTTP docs show them
    cid = uuid.uuid4().hex
    assert ingest.get(base, params={"status": "in_progress", "check_in_id": cid, "environment": "production"}).status_code == 202
    assert ingest.post(base, params={"status": "ok", "check_in_id": cid, "duration": "42.5", "environment": "production"}).status_code == 202
    # JSON body, key in the path without trailing slash
    assert ingest.post(f"/sentry/api/{PID}/cron/nightly-backup/{KEY}", json={"status": "error", "duration": 3}).status_code == 202
    # key in the X-Sentry-Auth header instead of the path; the slug is matched after Sentry's slugify
    assert ingest.get(f"/sentry/api/{PID}/cron/Nightly Backup/", params={"status": "ok"},
                      headers={"X-Sentry-Auth": f"Sentry sentry_key={KEY}, sentry_version=7"}).status_code == 202
    rows = _execs(org["id"], "Nightly backup")
    assert [x.status for x in rows] == ["success", "failed", "success"], rows
    assert rows[0].duration_ms == 42500 and rows[0].meta.get("env") == "production" and rows[0].meta.get("source") == "sentry"

    assert ingest.get(f"/sentry/api/{PID}/cron/no-such-monitor/{KEY}/", params={"status": "ok"}).status_code == 404
    assert ingest.get(f"/sentry/api/{PID}/cron/nightly-backup/{'b' * 32}/", params={"status": "ok"}).status_code == 404   # key is part of the credential
    assert ingest.get(f"/sentry/api/4506/cron/nightly-backup/{KEY}/", params={"status": "ok"}).status_code == 404         # so is the project
    assert ingest.get(base, params={"status": "missed"}).status_code == 400
    assert ingest.get(f"/sentry/api/{PID}/cron/nightly-backup/", params={"status": "ok"}).status_code == 401            # no key anywhere
    assert ingest.get(f"/sentry/api/abc/cron/nightly-backup/{KEY}/", params={"status": "ok"}).status_code == 404


def test_without_project_read_jobs_get_new_urls(fake_sentry, clients, org):
    api, ingest, h = clients
    r = api.post("/api/v1/import/sentry", headers=h, json={**_req(org, base_url=fake_sentry, dry_run=False), "auth_token": fake.NO_PROJECT_TOKEN}).json()
    made = [x for x in r["results"] if x["job_id"]]
    assert made and all(not x["kept_ping_url"] and x["new_ping_url"] for x in made)
    assert "new ping URL" in r["ping_host_change"]
    tok = made[0]["new_ping_url"].rsplit("/ping/", 1)[1]
    assert ingest.get(f"/ping/{tok}").status_code == 200


# ---- envelopes -----------------------------------------------------------------------------------

def _envelope(*checkins, dsn=None, extra=b""):
    head = {"event_id": uuid.uuid4().hex, "sent_at": "2026-10-10T00:00:00Z"}
    if dsn:
        head["dsn"] = dsn
    out = json.dumps(head).encode() + b"\n" + extra
    for c in checkins:
        p = json.dumps({"type": "check_in", **c}).encode()
        out += json.dumps({"type": "check_in", "length": len(p)}).encode() + b"\n" + p + b"\n"
    return out


def test_envelopes(fake_sentry, clients, org):
    api, ingest, h = clients
    api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=False))
    url = f"/sentry/api/{PID}/envelope/"
    auth = {"X-Sentry-Auth": f"Sentry sentry_key={KEY}, sentry_version=7, sentry_client=test/1.0"}
    cid = uuid.uuid4().hex
    # an error event in the same envelope is ignored; the check-in is recorded
    event = b'{"type":"event","length":20}\n{"message":"boom!!"}\n'
    r = ingest.post(url, headers=auth, content=_envelope({"check_in_id": cid, "monitor_slug": "queue-drain", "status": "in_progress"}, extra=event))
    assert r.status_code == 200 and "id" in r.json()
    body = gzip.compress(_envelope({"check_in_id": cid, "monitor_slug": "queue-drain", "status": "ok", "duration": 1.25}))
    assert ingest.post(url, headers={**auth, "Content-Encoding": "gzip"}, content=body).status_code == 200
    # key only in the envelope header's dsn; unknown monitors inside are skipped without failing the rest
    env = _envelope({"monitor_slug": "who-knows", "status": "ok"}, {"monitor_slug": "Queue Drain", "status": "error"},
                    dsn=f"https://{KEY}@o1.ingest.sentry.io/{PID}")
    assert ingest.post(url, content=env).status_code == 200
    rows = _execs(org["id"], "Queue drain")
    assert [x.status for x in rows] == ["success", "failed"] and rows[0].duration_ms == 1250
    assert ingest.post(url, content=_envelope({"monitor_slug": "queue-drain", "status": "ok"})).status_code == 401
    assert ingest.post(url, headers=auth, content=b"garbage\n").status_code == 400
    assert ingest.post(url, headers={**auth, "Content-Encoding": "zstd"}, content=b"x").status_code == 415
    assert ingest.post(url, headers={**auth, "Content-Encoding": "gzip"}, content=gzip.compress(b"\0" * 5_000_000)).status_code == 413


def test_envelope_rate_limit_uses_sentry_header(fake_sentry, clients, org, monkeypatch):
    api, ingest, h = clients
    api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=False))
    from cronsentinel.config import settings
    monkeypatch.setattr(settings, "ingest_rate_per_min", 2)
    auth = {"X-Sentry-Auth": f"Sentry sentry_key={KEY}, sentry_version=7"}
    codes = [ingest.post(f"/sentry/api/{PID}/envelope/", headers=auth, content=_envelope({"monitor_slug": "noisy", "status": "ok"})) for _ in range(4)]
    assert [c.status_code for c in codes][:2] == [200, 200] and codes[-1].status_code == 429
    assert codes[-1].headers["X-Sentry-Rate-Limits"] == "60:monitor:organization"


# ---- the real SDK ----------------------------------------------------------------------------------

@pytest.fixture
def live_ingest(clients):
    from cronsentinel.ingest_main import app as ingest
    ingest.state.js = None               # no NATS here: pings are processed inline, as in the other tests
    server, url = _serve(ingest, lifespan="off")
    assert server.started
    yield url
    server.should_exit = True


@pytest.mark.parametrize("compression", ["gzip", "br"])
def test_real_sentry_sdk_checkins(fake_sentry, clients, org, live_ingest, compression):
    sentry_sdk = pytest.importorskip("sentry_sdk")
    if compression == "br":
        pytest.importorskip("brotli")
    from sentry_sdk.crons import capture_checkin, monitor
    api, _, h = clients
    api.post("/api/v1/import/sentry", headers=h, json=_req(org, base_url=fake_sentry, dry_run=False))
    dsn = f"{live_ingest.replace('http://', f'http://{KEY}@')}/sentry/{PID}"     # only the DSN host changed
    sentry_sdk.init(dsn=dsn, default_integrations=False, environment="production",
                    _experiments={"transport_compression_algo": compression})
    try:
        cid = capture_checkin(monitor_slug="nightly-backup", status="in_progress")
        capture_checkin(monitor_slug="nightly-backup", check_in_id=cid, status="ok", duration=7.5)

        @monitor(monitor_slug="queue-drain")
        def job():
            raise RuntimeError("queue drain broke")
        with pytest.raises(RuntimeError):
            job()
        sentry_sdk.flush(timeout=10)
    finally:
        sentry_sdk.get_client().close(timeout=5)
    deadline = time.time() + 10
    while time.time() < deadline and len(_execs(org["id"], "Queue drain")) < 1:
        time.sleep(0.2)
    nb, qd = _execs(org["id"], "Nightly backup"), _execs(org["id"], "Queue drain")
    assert [x.status for x in nb] == ["success"] and nb[0].duration_ms == 7500 and nb[0].meta.get("env") == "production"
    assert [x.status for x in qd] == ["failed"], qd
