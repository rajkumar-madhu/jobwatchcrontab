"""Subscriptions: checkout → webhook → plan on org. Two processors, plain REST, no SDKs, so it runs without keys in dev.

Stripe   — USD, card; monthly or yearly Prices (plan_limits.stripe_price_id / _year).
Razorpay — INR, UPI AutoPay / cards / net banking (R75); Razorpay Plans (plan_limits.razorpay_plan_month / _year),
           hosted subscription page via `short_url`, webhook signed HMAC-SHA256 over the raw body.
An organisation has one provider at a time (subscriptions.provider); switching currency means cancelling the
other subscription first, which the portal/dashboard of that processor does."""
import hashlib
import hmac
import json
import time

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text

from ..auth import Principal, audit, current_principal, require_role
from ..config import settings
from ..db import system_session, tenant_session

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
STRIPE = "https://api.stripe.com/v1"
RAZORPAY = "https://api.razorpay.com/v1"


def _stripe(method: str, path: str, data: dict | None = None):
    if not settings.stripe_secret_key: raise HTTPException(503, "Billing not configured (STRIPE_SECRET_KEY)")
    r = httpx.request(method, f"{STRIPE}{path}", auth=(settings.stripe_secret_key, ""), data=data, timeout=15)
    if r.status_code >= 300: raise HTTPException(502, f"stripe: {r.text[:200]}")
    return r.json()


def _razorpay(method: str, path: str, body: dict | None = None):
    if not (settings.razorpay_key_id and settings.razorpay_key_secret): raise HTTPException(503, "INR billing not configured (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)")
    r = httpx.request(method, f"{RAZORPAY}{path}", auth=(settings.razorpay_key_id, settings.razorpay_key_secret), json=body, timeout=15)
    if r.status_code >= 300: raise HTTPException(502, f"razorpay: {r.text[:200]}")
    return r.json()


PLAN_COLS = "plan, max_jobs, retention_days, features, monthly_usd, yearly_usd, monthly_inr, yearly_inr"


@router.get("")
def status(p: Principal = Depends(current_principal)):
    with tenant_session(p.org_id) as s:
        # R38: was an INNER JOIN on subscriptions — if that row is ever missing (a bad migration,
        # manual DB fix, an org-deletion interrupted mid-transaction), `sub` came back None and the
        # frontend's `s?.effective_plan ?? "free"` silently displayed "Free" while every *numeric*
        # limit on the same page (below, joined straight from organizations.plan) correctly showed
        # the org's real plan — a paying org told it's on Free. LEFT JOIN + COALESCE means the
        # organization's own plan column, the authoritative source, is always what's reported, with
        # or without a subscriptions row; billing metadata (status/trial/renewal) is null instead of
        # making the whole object disappear. This billing page should hold itself to the same rule
        # R25 set for job monitoring: an internal data gap must never silently misreport the truth.
        sub = s.execute(text(
            "SELECT s.plan, s.status, s.trial_ends_at, s.current_period_end, s.cancel_at_period_end, "
            "(s.stripe_customer_id IS NOT NULL OR s.razorpay_customer_id IS NOT NULL) AS has_customer, COALESCE(s.plan, o.plan) AS effective_plan, "
            "s.provider, s.currency, s.billing_interval "
            "FROM organizations o LEFT JOIN subscriptions s ON s.org_id=o.id WHERE o.id=:o"), {"o": str(p.org_id)}).first()
        plans = [dict(r._mapping) for r in s.execute(text(f"SELECT {PLAN_COLS} FROM plan_limits ORDER BY COALESCE(monthly_usd, 99999)")).all()]
        usage = s.execute(text("SELECT (SELECT count(*) FROM jobs) AS jobs, (SELECT count(*) FROM executions WHERE scheduled_ts >= date_trunc('month', now())) AS executions_this_month, (SELECT COALESCE(sum(length(content)),0) FROM execution_logs) AS log_bytes")).first()
        limits = s.execute(text("SELECT pl.max_jobs, pl.retention_days FROM organizations o JOIN plan_limits pl ON pl.plan=o.plan WHERE o.id=:o"), {"o": str(p.org_id)}).first()
    return {"subscription": dict(sub._mapping) if sub else None, "plans": plans, "usage": dict(usage._mapping), "limits": dict(limits._mapping) if limits else None,
            "configured": bool(settings.stripe_secret_key), "configured_inr": bool(settings.razorpay_key_id and settings.razorpay_key_secret)}


@router.post("/checkout")
def checkout(plan: str, request: Request, currency: str = "usd", interval: str = "month", p: Principal = Depends(require_role("admin"))):
    """Start a subscription. currency=usd → Stripe Checkout; currency=inr → Razorpay hosted subscription page.
    interval=month|year. Returns the URL to send the browser to."""
    if currency not in ("usd", "inr"): raise HTTPException(400, "currency must be usd or inr")
    if interval not in ("month", "year"): raise HTTPException(400, "interval must be month or year")
    with tenant_session(p.org_id) as s:
        row = s.execute(text("SELECT stripe_price_id, stripe_price_id_year, razorpay_plan_month, razorpay_plan_year FROM plan_limits WHERE plan=:p"), {"p": plan}).first()
        if not row: raise HTTPException(404, "unknown plan")
        cur = s.execute(text("SELECT provider, status FROM subscriptions WHERE org_id=:o"), {"o": str(p.org_id)}).first()
        want = "razorpay" if currency == "inr" else "stripe"
        if cur and cur.provider != want and cur.status in ("active", "trialing", "past_due") and s.execute(text("SELECT plan FROM organizations WHERE id=:o"), {"o": str(p.org_id)}).scalar() != "free":
            raise HTTPException(409, f"this organisation is billed through {cur.provider}; cancel that subscription before switching currency")
        email = s.execute(text("SELECT email FROM users WHERE id=:u"), {"u": str(p.user_id)}).scalar() if p.user_id else None
        if want == "stripe":
            price = row.stripe_price_id_year if interval == "year" else row.stripe_price_id
            if not price: raise HTTPException(400, f"plan {plan} has no Stripe {interval}ly price configured")
            cust = s.execute(text("SELECT stripe_customer_id FROM subscriptions WHERE org_id=:o"), {"o": str(p.org_id)}).scalar()
            if not cust:
                cust = _stripe("POST", "/customers", {"metadata[org_id]": str(p.org_id), **({"email": email} if email else {})})["id"]
                s.execute(text("UPDATE subscriptions SET stripe_customer_id=:c, provider='stripe', currency='usd' WHERE org_id=:o"), {"c": cust, "o": str(p.org_id)})
            sess = _stripe("POST", "/checkout/sessions", {"mode": "subscription", "customer": cust, "line_items[0][price]": price, "line_items[0][quantity]": 1,
                                                           "success_url": f"{settings.web_public_url}/billing?ok=1", "cancel_url": f"{settings.web_public_url}/billing", "metadata[org_id]": str(p.org_id), "metadata[plan]": plan})
            s.execute(text("UPDATE subscriptions SET billing_interval=:i WHERE org_id=:o"), {"i": interval, "o": str(p.org_id)})
            url = sess["url"]
        else:
            rp_plan = row.razorpay_plan_year if interval == "year" else row.razorpay_plan_month
            if not rp_plan: raise HTTPException(400, f"plan {plan} has no Razorpay {interval}ly plan configured")
            cust = s.execute(text("SELECT razorpay_customer_id FROM subscriptions WHERE org_id=:o"), {"o": str(p.org_id)}).scalar()
            if not cust:
                name = s.execute(text("SELECT name FROM organizations WHERE id=:o"), {"o": str(p.org_id)}).scalar() or "Argus customer"
                cust = _razorpay("POST", "/customers", {"name": name[:50], **({"email": email} if email else {}), "fail_existing": "0", "notes": {"org_id": str(p.org_id)}})["id"]
                s.execute(text("UPDATE subscriptions SET razorpay_customer_id=:c WHERE org_id=:o"), {"c": cust, "o": str(p.org_id)})
            # total_count: Razorpay subscriptions need a finite number of cycles; 10 years is the dashboard's own ceiling.
            sub = _razorpay("POST", "/subscriptions", {"plan_id": rp_plan, "customer_id": cust, "total_count": 120 if interval == "month" else 10,
                                                       "customer_notify": 1, "notes": {"org_id": str(p.org_id), "plan": plan, "interval": interval}})
            s.execute(text("UPDATE subscriptions SET razorpay_subscription_id=:sid, provider='razorpay', currency='inr', billing_interval=:i WHERE org_id=:o"),
                      {"sid": sub["id"], "i": interval, "o": str(p.org_id)})
            url = sub["short_url"]
        audit(s, p, "billing.checkout", "subscription", plan, {"currency": currency, "interval": interval}, ip=request.client.host)
    return {"url": url}


@router.post("/portal")
def portal(p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        row = s.execute(text("SELECT provider, stripe_customer_id, razorpay_subscription_id FROM subscriptions WHERE org_id=:o"), {"o": str(p.org_id)}).first()
    if not row or not (row.stripe_customer_id or row.razorpay_subscription_id): raise HTTPException(400, "no billing customer yet")
    if row.provider == "razorpay":
        # Razorpay has no self-serve portal API; the hosted subscription page shows invoices and lets the customer cancel.
        sub = _razorpay("GET", f"/subscriptions/{row.razorpay_subscription_id}")
        return {"url": sub.get("short_url") or f"{settings.web_public_url}/billing"}
    return {"url": _stripe("POST", "/billing_portal/sessions", {"customer": row.stripe_customer_id, "return_url": f"{settings.web_public_url}/billing"})["url"]}


TOLERANCE_S = 300


def _verify(payload: bytes, sig_header: str) -> bool:
    """Stripe's scheme: `t=<ts>,v1=<hex>[,v1=<hex>...]`. During a secret rotation Stripe signs with
    both the old and the new secret and sends several `v1=` values in no guaranteed order, so we
    must accept *any* match — building a dict here kept only the last one and dropped half the
    events mid-rotation."""
    try:
        ts = None
        sigs = []
        for kv in sig_header.split(","):
            k, _, v = kv.strip().partition("=")
            if k == "t":
                ts = int(v)
            elif k == "v1":
                sigs.append(v)
        if ts is None or not sigs:
            return False
        if abs(time.time() - ts) > TOLERANCE_S:   # replay window
            return False
        expected = hmac.new(settings.stripe_webhook_secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, s) for s in sigs)
    except Exception:
        return False


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, stripe_signature: str = Header(default="")):
    raw = await request.body()
    if not settings.stripe_webhook_secret or not _verify(raw, stripe_signature): raise HTTPException(400, "bad signature")
    try:
        ev = json.loads(raw)
        obj = ev["data"]["object"]
        ev_id, ev_type = ev["id"], ev["type"]
    except (ValueError, KeyError, TypeError) as e:
        # Malformed beyond use: 400 so Stripe stops retrying, and nothing is recorded.
        raise HTTPException(400, f"unparseable event: {e}") from e
    with system_session() as s:
        if s.execute(text("INSERT INTO stripe_events (id, type) VALUES (:i, :t) ON CONFLICT DO NOTHING RETURNING 1"), {"i": ev_id, "t": ev_type}).first() is None:
            return {"ok": True, "duplicate": True}
        t = ev_type
        if t == "checkout.session.completed":
            md = obj.get("metadata") or {}
            plan, org_id = md.get("plan"), md.get("org_id")
            if not plan or not org_id:
                # Our own checkout always sets both; anything else is not ours to act on. Raising
                # here rolls back the stripe_events insert too, so a corrected retry still lands.
                raise HTTPException(400, "checkout.session.completed without plan/org_id metadata")
            s.execute(text("UPDATE subscriptions SET stripe_subscription_id=:sid, plan=:p, status='active' WHERE org_id=CAST(:o AS uuid)"), {"sid": obj.get("subscription"), "p": plan, "o": org_id})
            s.execute(text("UPDATE organizations SET plan=:p WHERE id=CAST(:o AS uuid)"), {"p": plan, "o": org_id})
        elif t in ("customer.subscription.updated", "customer.subscription.deleted"):
            price = obj["items"]["data"][0]["price"]["id"] if obj.get("items") else None
            plan = s.execute(text("SELECT plan FROM plan_limits WHERE stripe_price_id=:p"), {"p": price}).scalar() if price else None
            status = obj["status"] if t.endswith("updated") else "canceled"
            eff = plan if status in ("active", "trialing") and plan else "free"
            s.execute(text("UPDATE subscriptions SET status=:st, plan=:pl, stripe_price_id=:pr, cancel_at_period_end=:c, current_period_end=to_timestamp(:pe) WHERE stripe_customer_id=:cu"),
                      {"st": status, "pl": eff, "pr": price, "c": obj.get("cancel_at_period_end", False), "pe": obj.get("current_period_end"), "cu": obj["customer"]})
            s.execute(text("UPDATE organizations o SET plan=:pl FROM subscriptions sb WHERE sb.org_id=o.id AND sb.stripe_customer_id=:cu"), {"pl": eff, "cu": obj["customer"]})
        elif t == "invoice.payment_failed":
            s.execute(text("UPDATE subscriptions SET status='past_due' WHERE stripe_customer_id=:cu"), {"cu": obj["customer"]})
            # TODO: notify org admins via notification channel
    return {"ok": True}


# ---- R75: Razorpay webhook ------------------------------------------------------------------------
# Signature: X-Razorpay-Signature = hex(HMAC-SHA256(webhook_secret, raw body)). Idempotency key:
# X-Razorpay-Event-Id. Subscription statuses: created → authenticated → active → (pending → halted) →
# cancelled | completed | expired. Entitlement is granted on `activated`/`charged`, revoked on cancelled/
# completed/expired, and marked past_due on pending/halted (Razorpay keeps retrying for the mandate).

_RP_ACTIVE = {"subscription.activated", "subscription.charged", "subscription.resumed"}
_RP_PAST_DUE = {"subscription.pending", "subscription.halted"}
_RP_ENDED = {"subscription.cancelled", "subscription.completed", "subscription.expired"}


def _verify_razorpay(payload: bytes, signature: str) -> bool:
    if not settings.razorpay_webhook_secret or not signature:
        return False
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


@router.post("/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(default=""), x_razorpay_event_id: str = Header(default="")):
    raw = await request.body()
    if not _verify_razorpay(raw, x_razorpay_signature): raise HTTPException(400, "bad signature")
    try:
        ev = json.loads(raw)
        ev_type = ev["event"]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, f"unparseable event: {e}") from e
    sub = ((ev.get("payload") or {}).get("subscription") or {}).get("entity")
    if not isinstance(sub, dict) or not sub.get("id"):
        return {"ok": True, "ignored": True}   # payment.*, invoice.*, refund.*: not subscription state; acknowledged so Razorpay stops retrying
    sub_id = sub["id"]
    ev_id = x_razorpay_event_id or hashlib.sha256(raw).hexdigest()   # older webhook configs may omit the header
    with system_session() as s:
        if s.execute(text("INSERT INTO razorpay_events (id, type) VALUES (:i, :t) ON CONFLICT DO NOTHING RETURNING 1"), {"i": ev_id, "t": ev_type}).first() is None:
            return {"ok": True, "duplicate": True}
        row = s.execute(text("SELECT org_id FROM subscriptions WHERE razorpay_subscription_id=:sid"), {"sid": sub_id}).first()
        if not row:
            # Not one of ours (created outside checkout): acknowledge so Razorpay stops retrying; nothing to grant.
            return {"ok": True, "ignored": True}
        notes = sub.get("notes") or {}
        plan = notes.get("plan") or s.execute(text("SELECT plan FROM plan_limits WHERE razorpay_plan_month=:p OR razorpay_plan_year=:p"), {"p": sub.get("plan_id")}).scalar()
        period_end = sub.get("current_end")
        if ev_type in _RP_ACTIVE and plan:
            s.execute(text("UPDATE subscriptions SET status='active', plan=:p, provider='razorpay', currency='inr', current_period_end=to_timestamp(:pe), cancel_at_period_end=false WHERE org_id=:o"),
                      {"p": plan, "pe": period_end, "o": row.org_id})
            s.execute(text("UPDATE organizations SET plan=:p WHERE id=:o"), {"p": plan, "o": row.org_id})
        elif ev_type in _RP_PAST_DUE:
            s.execute(text("UPDATE subscriptions SET status='past_due' WHERE org_id=:o"), {"o": row.org_id})
        elif ev_type in _RP_ENDED:
            s.execute(text("UPDATE subscriptions SET status='canceled', plan='free', current_period_end=to_timestamp(:pe) WHERE org_id=:o"), {"pe": period_end, "o": row.org_id})
            s.execute(text("UPDATE organizations SET plan='free' WHERE id=:o"), {"o": row.org_id})
        # subscription.authenticated / updated: nothing to change until money moves
    return {"ok": True}
