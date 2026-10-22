"""Ingest tier. Token → job (Redis cached) → NATS publish. No auth header needed: token IS the auth."""
import json
from datetime import UTC, datetime

import redis
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import text

from .. import pingtokens, ratelimit
from ..config import settings
from ..db import system_session
from ..schemas import HeartbeatBody

router = APIRouter(tags=["heartbeat"])
_r = redis.Redis.from_url(settings.redis_url, decode_responses=True)


_MISS = "-"           # negative-cache marker
POSITIVE_TTL_S = 300
NEGATIVE_TTL_S = 60
UNKNOWN_TOKEN_PER_IP_PER_MIN = 60


def invalidate_token(token_hash: str | None) -> None:
    """Drop a token (by its hash) from the resolve cache. Call on pause, delete and rotation —
    otherwise a paused/deleted job (or a rotated-out token) kept being accepted for POSITIVE_TTL_S."""
    if token_hash:
        try:
            _r.delete(f"hb:{token_hash}")
        except redis.RedisError:
            pass


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


_NOT_FETCHED = object()


def _resolve(token: str, request: Request | None = None, cached=_NOT_FETCHED) -> tuple[str, str]:
    """`cached` lets the caller pass a value it already read from `hb:<hash>` in a pipeline."""
    if not token or len(token) > 200:
        raise HTTPException(404, "unknown heartbeat token")
    h = pingtokens.hash_token(token)   # R41: neither the DB nor the cache key holds the plaintext
    if cached is _NOT_FETCHED:
        cached = _r.get(f"hb:{h}")
    if cached == _MISS:
        raise HTTPException(404, "unknown heartbeat token")
    if cached:
        org, job = cached.split("|")
        return org, job
    # Unknown tokens are limited per source IP and negatively cached, so guessing costs a DB query
    # at most UNKNOWN_TOKEN_PER_IP_PER_MIN times a minute per IP.
    # R47: only *failed* lookups count. R39 charged every cache miss — including valid tokens not yet
    # cached — so one host (or NAT gateway) with more than 60 jobs got 429s each time the 5-minute
    # cache expired. Found by the ingest load test (tools/loadtest).
    miss_key = f"hbmiss:{_client_ip(request)}" if request is not None else None
    if miss_key and int(_r.get(miss_key) or 0) >= UNKNOWN_TOKEN_PER_IP_PER_MIN:
        raise HTTPException(429, "too many unknown heartbeat tokens from this address")
    with system_session() as s:
        row = s.execute(text("SELECT org_id, id FROM jobs WHERE heartbeat_token_hash=:h AND paused=false"), {"h": h}).first()
    if not row:
        _r.setex(f"hb:{h}", NEGATIVE_TTL_S, _MISS)
        if miss_key:
            if _r.incr(miss_key) == 1:      # first miss opens a 60 s window (works on Redis 6.2)
                _r.expire(miss_key, 60)
        raise HTTPException(404, "unknown heartbeat token")
    _r.setex(f"hb:{h}", POSITIVE_TTL_S, f"{row.org_id}|{row.id}")
    return str(row.org_id), str(row.id)


async def _emit(request: Request, token: str, body: HeartbeatBody):
    # R22: token resolution (Redis, DB on a miss) and the rate-limit INCR are synchronous network
    # calls. Run on the event loop they serialise every request in the process behind them — tiny
    # against local Redis, a hard ceiling against a remote one. One threadpool hop for both.
    def _auth():
        # R47: one Redis round trip per ping instead of two — the resolve-cache read and the
        # rate-limit script are pipelined (profiled under load: the two sequential round trips were
        # most of the request's time). The limiter is keyed by the token's hash: never the plaintext
        # (the old key put every ping token into Redis) and known before the token is resolved.
        if not token or len(token) > 200:
            raise HTTPException(404, "unknown heartbeat token")
        h = pingtokens.hash_token(token)
        cached, allowed = ratelimit.check_pipelined(f"hbrate:{h}", settings.ingest_rate_per_min, f"hb:{h}", request)
        if not allowed:
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})
        return _resolve(token, request, cached=cached)
    org, job = await run_in_threadpool(_auth)
    ev = {
        "org_id": org, "job_id": job, "kind": body.status, "execution_id": body.execution_id,
        "sequence": body.sequence, "agent_ts": body.agent_ts.isoformat() if body.agent_ts else None,
        "server_ts": datetime.now(UTC).isoformat(), "duration_ms": body.duration_ms,
        "exit_code": body.exit_code, "host": body.host or _client_ip(request),
        "stdout_tail": body.stdout_tail, "stderr_tail": body.stderr_tail, "meta": body.meta,
        "metrics": body.metrics,
    }
    js = request.app.state.js
    if js is not None:
        await js.publish(f"exec.{org}", json.dumps(ev).encode())
    else:  # TODO: remove sync fallback once NATS is mandatory in all envs
        from ..processor import process
        def _inline():
            with system_session() as s:
                process(s, ev)
        await run_in_threadpool(_inline)
    return {"ok": True, "execution_id": body.execution_id}


@router.get("/ping/{token}")
async def ping(token: str, request: Request):
    """Simple mode: curl https://host/ping/<token> == success."""
    return await _emit(request, token, HeartbeatBody(status="success"))


@router.get("/heartbeat/{token}/{status}")
@router.post("/heartbeat/{token}/{status}")
async def heartbeat_path(token: str, status: str, request: Request):
    if status not in ("start", "success", "fail"):
        raise HTTPException(400, "status must be start|success|fail")
    return await _emit(request, token, HeartbeatBody(status=status))


@router.post("/api/v1/heartbeat/{token}")
async def heartbeat_json(token: str, body: HeartbeatBody, request: Request):
    return await _emit(request, token, body)


# ---- R48: Healthchecks.io-compatible ping paths -------------------------------------------------
# Jobs imported from Healthchecks keep their check UUID as the ping token, so migrating a script is a
# host change: https://hc-ping.com/<uuid>[/start|/fail|/log|/<exit status>] → https://<ingest>/hc/…
# Semantics follow Healthchecks' ping API: plain = success, /start, /fail, /<0-255> (0 = success),
# /log records nothing here (accepted so scripts don't fail), ?rid=<uuid> ties start and end of a run.

_HC_BODY_MAX = 100_000


@router.api_route("/hc/{token}", methods=["GET", "POST", "HEAD"], include_in_schema=False)
@router.api_route("/hc/{token}/{action}", methods=["GET", "POST", "HEAD"], include_in_schema=False)
async def healthchecks_compat(token: str, request: Request, action: str = "", rid: str | None = None):
    a = action.lower()
    if a in ("", "success"):
        status, code = "success", None
    elif a in ("start", "fail"):
        status, code = a, None
    elif a == "log":
        _resolve(token, request)                      # still a real check: unknown tokens get 404
        return Response("OK", media_type="text/plain")
    elif a.isdigit() and 0 <= int(a) <= 255:
        code = int(a)
        status = "success" if code == 0 else "fail"
    else:
        raise HTTPException(400, "unknown ping action")
    body = (await request.body())[:_HC_BODY_MAX].decode(errors="replace") if request.method == "POST" else None
    # With ?rid the start and the end share an execution id; the end needs a higher sequence or
    # de-duplication would drop it as a repeat of the start.
    hb = HeartbeatBody(status=status, exit_code=code, stdout_tail=body or None,
                       execution_id=f"hc-{rid}"[:128] if rid else None, sequence=0 if status == "start" else 1)
    await _emit(request, token, hb)
    return Response("OK", media_type="text/plain")   # Healthchecks answers "OK"; some scripts check for it


# ---- R50: Cronitor-compatible telemetry paths --------------------------------------------------
# Jobs imported from Cronitor with the telemetry key keep "<telemetry key>/<monitor key>" as their ping
# token (hashed), so scripts change only the host:
#   https://cronitor.link/p/<key>/<monitor>?state=run  →  https://<ingest>/cronitor/p/<key>/<monitor>?state=run
# Semantics from Cronitor's Telemetry API docs: state run|complete|fail|tick|ok (none = tick), series
# pairs run with complete/fail, metric=name:value (duration in seconds, count, error_count, custom),
# message (≤2000 chars), status_code, host, env. POST bodies are ignored, as Cronitor does.
# One deliberate difference: Cronitor auto-creates a monitor for an unknown key; JobWatch answers 404.

_CR_STATES = {"run": "start", "complete": "success", "fail": "fail", "tick": "success", "ok": "success", "": "success"}


async def _cronitor(api_key: str, monitor_key: str, request: Request):
    q = request.query_params
    state = q.get("state", "").lower()
    if state not in _CR_STATES:
        raise HTTPException(400, "state must be run, complete, fail, tick or ok")
    status = _CR_STATES[state]
    duration_ms, meta, metrics = None, {}, {}
    for raw in q.getlist("metric"):
        k, sep, v = raw.partition(":") if ":" in raw else raw.partition("=")
        try:
            val = float(v)
        except ValueError:
            continue
        if k == "duration":
            duration_ms = int(val * 1000)
        else:
            metrics[k.lower()[:40]] = val      # R54: real run metrics, evaluated by job assertions
    for k in ("env", "host"):
        if q.get(k):
            meta[k] = q.get(k)[:100]
    code = q.get("status_code")
    series = q.get("series")
    hb = HeartbeatBody(status=status, exit_code=int(code) if code and code.lstrip("-").isdigit() and abs(int(code)) <= 1024 else None,
                       duration_ms=duration_ms, stdout_tail=(q.get("message") or None) and q.get("message")[:2000],
                       host=(q.get("host") or None) and q.get("host")[:255], meta=meta,
                       execution_id=f"cr-{series}"[:128] if series else None, sequence=0 if status == "start" else 1,
                       metrics=metrics)
    await _emit(request, f"{api_key}/{monitor_key}", hb)
    return Response("OK", media_type="text/plain")


@router.api_route("/cronitor/p/{api_key}/{monitor_key}", methods=["GET", "POST", "HEAD"], include_in_schema=False)
async def cronitor_p(api_key: str, monitor_key: str, request: Request):
    return await _cronitor(api_key, monitor_key, request)


@router.api_route("/cronitor/ping/{api_key}/{monitor_key}", methods=["GET", "POST", "HEAD"], include_in_schema=False)
async def cronitor_ping_legacy(api_key: str, monitor_key: str, request: Request):
    return await _cronitor(api_key, monitor_key, request)


# ---- R67: Sentry Crons-compatible check-ins -----------------------------------------------------
# Jobs imported from Sentry keep "sentry:<project id>:<public key>:<monitor slug>" as their ping token
# (hashed). Sentry's own paths are served under /sentry, so:
#   HTTP check-ins  https://o1.ingest.sentry.io/api/<pid>/cron/<slug>/<key>/?status=ok
#                →  https://<ingest>/sentry/api/<pid>/cron/<slug>/<key>/?status=ok
#   SDKs            DSN https://<key>@o1.ingest.sentry.io/<pid>  →  https://<key>@<ingest>/sentry/<pid>
# Formats are taken from Sentry's source (see cronsentinel/sentrycompat.py). Differences: unknown monitors
# are never auto-created from monitor_config (HTTP answers 404; envelopes ignore them, as SDKs do not read
# the response), and only check-in items are read from an envelope — errors, transactions and sessions
# sent to this DSN are dropped, so give crons their own DSN or keep your app's DSN on Sentry.

from fastapi.responses import JSONResponse  # noqa: E402

from .. import sentrycompat as sc  # noqa: E402


async def _sentry_body(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > sc.MAX_BODY:
            raise HTTPException(413, "body too large")
    try:
        return sc.decode_body(bytes(raw), request.headers.get("content-encoding"))
    except sc.BadRequest as e:
        raise HTTPException(e.status, e.detail) from None


def _sentry_key(request: Request, path_key: str | None, dsn: str | None = None) -> str:
    key = sc.key_from_request(request.headers, request.url.query, path_key) or sc.key_from_dsn(dsn)
    if not key or not sc.KEY_RE.fullmatch(key):
        raise HTTPException(401, "missing or malformed sentry_key")
    return key


async def _sentry_http(project_id: str, monitor_slug: str, request: Request, sentry_key: str | None = None):
    if not sc.PROJECT_RE.fullmatch(project_id):
        raise HTTPException(404, "unknown project")
    key = _sentry_key(request, sentry_key)
    if (request.headers.get("content-type") or "").startswith("application/json"):
        try:
            payload = json.loads(await _sentry_body(request) or b"{}")
        except ValueError:
            raise HTTPException(400, "body is not JSON") from None
        if not isinstance(payload, dict):
            raise HTTPException(400, "body must be a JSON object")
    else:
        payload = dict(request.query_params)
    fields = sc.checkin_fields(payload)
    if fields is None:
        raise HTTPException(400, "status must be in_progress, ok or error")
    slug = sc.slugify(monitor_slug)
    if not slug:
        raise HTTPException(400, "the monitor slug is empty or invalid")
    await _emit(request, sc.token(project_id, key, slug), HeartbeatBody(**fields))
    return Response(status_code=202)            # Relay answers 202 Accepted with no body


for _p in ("/sentry/api/{project_id}/cron/{monitor_slug}/{sentry_key}", "/sentry/api/{project_id}/cron/{monitor_slug}/{sentry_key}/"):
    router.add_api_route(_p, _sentry_http, methods=["GET", "POST"], include_in_schema=False)


async def _sentry_http_nokey(project_id: str, monitor_slug: str, request: Request):
    return await _sentry_http(project_id, monitor_slug, request)

for _p in ("/sentry/api/{project_id}/cron/{monitor_slug}", "/sentry/api/{project_id}/cron/{monitor_slug}/"):
    router.add_api_route(_p, _sentry_http_nokey, methods=["GET", "POST"], include_in_schema=False)


async def sentry_envelope(project_id: str, request: Request):
    if not sc.PROJECT_RE.fullmatch(project_id):
        raise HTTPException(404, "unknown project")
    try:
        header, items = sc.parse_envelope(await _sentry_body(request))
    except sc.BadRequest as e:
        raise HTTPException(e.status, e.detail) from None
    key = _sentry_key(request, None, header.get("dsn") if isinstance(header.get("dsn"), str) else None)
    seen = 0
    for ih, payload in items:
        if ih.get("type") != "check_in":
            continue
        seen += 1
        if seen > sc.MAX_CHECKINS_PER_ENVELOPE:
            break
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(p, dict):
            continue
        fields, slug = sc.checkin_fields(p), sc.slugify(str(p.get("monitor_slug") or ""))
        if fields is None or not slug:
            continue
        try:
            await _emit(request, sc.token(project_id, key, slug), HeartbeatBody(**fields))
        except HTTPException as e:
            if e.status_code == 429:            # SDKs honour X-Sentry-Rate-Limits per category
                return JSONResponse({"detail": e.detail}, status_code=429,
                                    headers={"Retry-After": "60", "X-Sentry-Rate-Limits": "60:monitor:organization"})
            continue                            # unknown monitor: ignored, like any item we do not record
    eid = header.get("event_id")
    return JSONResponse({"id": eid} if isinstance(eid, str) and len(eid) <= 64 else {})


for _p in ("/sentry/api/{project_id}/envelope/", "/sentry/api/{project_id}/envelope"):
    router.add_api_route(_p, sentry_envelope, methods=["POST"], include_in_schema=False)
