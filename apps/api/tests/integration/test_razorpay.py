"""R75 — INR billing through Razorpay: the plan table after re-pricing, the checkout branch (HTTP
mocked), and the webhook's signature check and state machine against the real DB."""
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import text

from cronsentinel.auth import generate_api_key, hash_secret
from cronsentinel.config import settings
from cronsentinel.db import system_session

SECRET = "rzp_whsec_test"


@pytest.fixture
def env(org, monkeypatch):
    from fastapi.testclient import TestClient

    from cronsentinel.main import app
    monkeypatch.setattr(settings, "razorpay_webhook_secret", SECRET, raising=False)
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key", raising=False)
    monkeypatch.setattr(settings, "razorpay_key_secret", "rzp_test_secret", raising=False)
    prefix, raw = generate_api_key()
    with system_session() as s:
        s.execute(text("INSERT INTO api_keys (org_id, name, prefix, key_hash, role) VALUES (:o,'a',:p,:h,'admin')"), {"o": org["id"], "p": prefix, "h": hash_secret(raw)})
        s.execute(text("INSERT INTO subscriptions (org_id, plan, status) VALUES (:o, 'free', 'active') ON CONFLICT (org_id) DO NOTHING"), {"o": org["id"]})
        s.execute(text("UPDATE plan_limits SET razorpay_plan_month='plan_M_dev', razorpay_plan_year='plan_Y_dev' WHERE plan='developer'"))
    run = uuid.uuid4().hex[:6]
    yield {"c": TestClient(app, raise_server_exceptions=False), "h": {"X-API-Key": raw}, "org": org["id"], "ev": lambda n: f"evt_{run}_{n}"}
    with system_session() as s:
        s.execute(text("UPDATE plan_limits SET razorpay_plan_month=NULL, razorpay_plan_year=NULL WHERE plan='developer'"))
        s.execute(text("DELETE FROM razorpay_events WHERE id LIKE :p"), {"p": f"evt_{run}_%"})


def _signed(body: dict, secret=SECRET):
    raw = json.dumps(body).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def _event(ev_type, sub_id, plan="developer", status="active", current_end=1_800_000_000):
    return {"event": ev_type, "payload": {"subscription": {"entity": {"id": sub_id, "plan_id": "plan_M_dev", "status": status,
            "current_end": current_end, "notes": {"plan": plan, "interval": "month"}}}}}


def _state(org):
    with system_session() as s:
        return s.execute(text("SELECT o.plan, s.status, s.provider, s.currency FROM organizations o JOIN subscriptions s ON s.org_id=o.id WHERE o.id=:o"), {"o": org}).first()


def test_plan_table_after_repricing(env):
    r = env["c"].get("/api/v1/billing", headers=env["h"]); assert r.status_code == 200, r.text
    plans = {p["plan"]: p for p in r.json()["plans"]}
    assert plans["developer"]["max_jobs"] == 100 and float(plans["developer"]["monthly_usd"]) == 19
    assert plans["team"]["max_jobs"] == 1000 and plans["team"]["retention_days"] == 365
    assert plans["business"]["max_jobs"] is None
    assert {"slack", "webhook"} <= set(plans["free"]["features"])
    assert float(plans["developer"]["monthly_inr"]) == 799 and float(plans["developer"]["yearly_inr"]) == 7999
    assert float(plans["enterprise"]["yearly_usd"]) == 6000
    assert r.json()["configured_inr"] is True


def test_inr_checkout_creates_customer_and_subscription(env, monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        if path == "/customers": return {"id": "cust_1"}
        if path == "/subscriptions": return {"id": "sub_1", "short_url": "https://rzp.io/i/abc"}
        raise AssertionError(path)
    import cronsentinel.routers.billing as b
    monkeypatch.setattr(b, "_razorpay", fake)
    r = env["c"].post("/api/v1/billing/checkout?plan=developer&currency=inr&interval=year", headers=env["h"])
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://rzp.io/i/abc"
    assert calls[1][2]["plan_id"] == "plan_Y_dev" and calls[1][2]["total_count"] == 10 and calls[1][2]["notes"]["plan"] == "developer"
    st = _state(env["org"]); assert (st.provider, st.currency) == ("razorpay", "inr")
    # a plan without a Razorpay plan id is refused before any HTTP call
    r = env["c"].post("/api/v1/billing/checkout?plan=team&currency=inr", headers=env["h"])
    assert r.status_code == 400 and "Razorpay" in r.text
    r = env["c"].post("/api/v1/billing/checkout?plan=developer&currency=eur", headers=env["h"])
    assert r.status_code == 400


def test_webhook_rejects_bad_signature_and_grants_revokes_plan(env):
    c = env["c"]; sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    with system_session() as s:
        s.execute(text("UPDATE subscriptions SET razorpay_subscription_id=:sid, provider='razorpay', currency='inr' WHERE org_id=:o"), {"sid": sub_id, "o": env["org"]})
    raw, sig = _signed(_event("subscription.activated", sub_id))
    assert c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": "00" * 32}).status_code == 400
    assert c.post("/api/v1/billing/razorpay/webhook", content=raw).status_code == 400
    r = c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": env["ev"]("1")})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _state(env["org"]).plan == "developer" and _state(env["org"]).status == "active"
    # replay with the same event id is a no-op
    r = c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": env["ev"]("1")})
    assert r.json().get("duplicate") is True
    # a halted mandate marks past_due but keeps the plan; cancellation drops to free
    raw, sig = _signed(_event("subscription.halted", sub_id, status="halted"))
    c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": env["ev"]("2")})
    assert (_state(env["org"]).plan, _state(env["org"]).status) == ("developer", "past_due")
    raw, sig = _signed(_event("subscription.cancelled", sub_id, status="cancelled"))
    c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": env["ev"]("3")})
    assert (_state(env["org"]).plan, _state(env["org"]).status) == ("free", "canceled")


def test_webhook_ignores_unknown_subscriptions_and_non_subscription_events(env):
    c = env["c"]
    raw, sig = _signed(_event("subscription.activated", "sub_not_ours"))
    r = c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": env["ev"]("x")})
    assert r.status_code == 200 and r.json().get("ignored") is True
    raw, sig = _signed({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_1"}}}})
    r = c.post("/api/v1/billing/razorpay/webhook", content=raw, headers={"X-Razorpay-Signature": sig})
    assert r.status_code == 200 and r.json().get("ignored") is True
    assert _state(env["org"]).plan == "free"


def test_cannot_switch_currency_while_billed_elsewhere(env):
    with system_session() as s:
        s.execute(text("UPDATE subscriptions SET provider='stripe', status='active', plan='developer', stripe_customer_id='cus_1' WHERE org_id=:o"), {"o": env["org"]})
        s.execute(text("UPDATE organizations SET plan='developer' WHERE id=:o"), {"o": env["org"]})
    r = env["c"].post("/api/v1/billing/checkout?plan=developer&currency=inr", headers=env["h"])
    assert r.status_code == 409
