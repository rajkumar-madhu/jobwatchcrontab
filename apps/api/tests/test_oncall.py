"""R42: PagerDuty / Opsgenie senders, against a recording mock transport (no network)."""
import json

import httpx
import pytest

from cronsentinel.alerting import oncall

PD_KEY = "R0123456789abcdefABCDEF012345678"
OG_KEY = "4f2c1d9e-1b2a-4c3d-9e8f-0a1b2c3d4e5f"
P = {"job_id": "11111111-1111-1111-1111-111111111111", "job_name": "nightly-backup", "prev_status": "healthy",
     "new_status": "failed", "condition": "failed", "severity": "critical", "incident_id": "inc-1",
     "execution_id": "ex-1", "ts": "2026-10-01T04:15:00+00:00"}


def recorder(status=202):
    calls = []
    def handler(req: httpx.Request):
        calls.append((req.method, str(req.url), dict(req.headers), json.loads(req.content or b"{}")))
        return httpx.Response(status, json={"status": "success"})
    return calls, httpx.Client(transport=httpx.MockTransport(handler))


def test_validate():
    assert oncall.validate("pagerduty", {"routing_key": PD_KEY}) is None
    assert oncall.validate("pagerduty", {"routing_key": "short"})
    assert oncall.validate("pagerduty", {"routing_key": PD_KEY, "region": "mars"})
    assert oncall.validate("opsgenie", {"api_key": OG_KEY, "region": "eu"}) is None
    assert oncall.validate("opsgenie", {"api_key": "not-a-key"})


def test_pagerduty_trigger_then_resolve_share_one_dedup_key():
    calls, c = recorder()
    oncall.send_pagerduty({"routing_key": PD_KEY, "dashboard_url": "https://jw.example"}, "✕ [CRITICAL] nightly-backup: failed", "body", P, client=c)
    oncall.send_pagerduty({"routing_key": PD_KEY}, "t", "b", {**P, "condition": "recovered", "new_status": "recovered"}, client=c)
    (m1, u1, _, trig), (_, _, _, res) = calls
    assert u1 == "https://events.pagerduty.com/v2/enqueue" and m1 == "POST"
    assert trig["event_action"] == "trigger" and trig["payload"]["severity"] == "critical"
    assert trig["payload"]["component"] == "nightly-backup" and trig["links"][0]["href"].endswith(f"/jobs/{P['job_id']}")
    assert res == {"routing_key": PD_KEY, "event_action": "resolve", "dedup_key": trig["dedup_key"]}


def test_pagerduty_eu_region_and_test_closes_itself():
    calls, c = recorder()
    oncall.send_pagerduty({"routing_key": PD_KEY, "region": "eu"}, "t", "b", {**P, "test": True, "test_id": "ch1"}, client=c)
    assert [x[1] for x in calls] == ["https://events.eu.pagerduty.com/v2/enqueue"] * 2
    assert [x[3]["event_action"] for x in calls] == ["trigger", "resolve"]
    assert calls[0][3]["dedup_key"] == "jobwatch-test-ch1"   # never collides with a real job's alert


def test_opsgenie_create_and_close_by_alias():
    calls, c = recorder()
    oncall.send_opsgenie({"api_key": OG_KEY}, "x" * 300, "body", P, client=c)
    oncall.send_opsgenie({"api_key": OG_KEY}, "t", "b", {**P, "condition": "recovered"}, client=c)
    (m1, u1, h1, alert), (m2, u2, h2, _) = calls
    assert u1 == "https://api.opsgenie.com/v2/alerts" and h1["authorization"] == f"GenieKey {OG_KEY}"
    assert len(alert["message"]) == 130 and alert["priority"] == "P1" and alert["alias"] == f"jobwatch-job-{P['job_id']}"
    assert u2 == f"https://api.opsgenie.com/v2/alerts/{alert['alias']}/close?identifierType=alias"


def test_vendor_error_raises_so_the_notifier_retries():
    _, c = recorder(status=400)
    with pytest.raises(httpx.HTTPStatusError):
        oncall.send_pagerduty({"routing_key": PD_KEY}, "t", "b", P, client=c)
