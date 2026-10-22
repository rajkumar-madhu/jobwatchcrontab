"""A stand-in for Sentry's monitor and project-key APIs, written to Sentry's source (getsentry/sentry):
MonitorSerializer (sentry/monitors/serializers.py), ProjectKeySerializer
(sentry/api/serializers/models/project_key.py) and cursor paging links (sentry/api/base.py:
'<uri&cursor=…>; rel="next"; results="true|false"; cursor="…"'). The R67 importer is tested against it.

Tokens: READ_TOKEN has org:read + project:read; NO_PROJECT_TOKEN lacks project:read (keys → 403);
NO_ORG_TOKEN lacks org:read (monitors → 403). Organization slug: ORG.
"""
from fastapi import FastAPI, Header, HTTPException, Request, Response

ORG = "acme"
READ_TOKEN = "sntrys_read_0123456789abcdef"
NO_PROJECT_TOKEN = "sntrys_noproj_0123456789ab"
NO_ORG_TOKEN = "sntrys_noorg_0123456789abc"

BACKEND = {"id": "4505", "slug": "backend", "name": "Backend", "platform": "python"}
BATCH = {"id": "4506", "slug": "batch", "name": "Batch", "platform": "python"}
BACKEND_KEY = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
KEYS = {
    "backend": [{"id": BACKEND_KEY, "name": "Default", "public": BACKEND_KEY, "secret": "s" * 32, "projectId": 4505,
                 "isActive": True, "dsn": {"public": f"https://{BACKEND_KEY}@o1.ingest.sentry.io/4505"}}],
    "batch": [{"id": "0" * 32, "name": "Revoked", "public": "0" * 32, "projectId": 4506, "isActive": False},
              {"id": "f" * 32, "name": "Default", "public": "f" * 32, "projectId": 4506, "isActive": True},
              {"id": "e" * 32, "name": "Second", "public": "e" * 32, "projectId": 4506, "isActive": True}],
}


def _mon(slug, name, cfg, project=BACKEND, status="active", muted=False, envs=("production",)):
    return {"id": f"guid-{slug}", "slug": slug, "name": name, "status": status, "isMuted": muted, "isUpserting": False,
            "config": {"schedule_type": "crontab", "schedule": "0 * * * *", "checkin_margin": None, "max_runtime": None,
                       "timezone": None, "failure_issue_threshold": None, "recovery_threshold": None, "alert_rule_id": None, **cfg},
            "dateCreated": "2026-01-01T00:00:00Z", "project": project,
            "environments": [{"name": e, "status": "ok", "isMuted": muted} for e in envs], "owner": None}


MONITORS = [
    _mon("nightly-backup", "Nightly backup", {"schedule": "0 2 * * *", "timezone": "Asia/Kolkata", "checkin_margin": 15, "max_runtime": 120}),
    _mon("queue-drain", "Queue drain", {"schedule_type": "interval", "schedule": [5, "minute"]}),
    _mon("monthly-invoices", "Monthly invoices", {"schedule_type": "interval", "schedule": [1, "month"]}, project=BATCH),
    _mon("odd-interval", "Odd interval", {"schedule_type": "interval", "schedule": [90, "minute"]}, project=BATCH),
    _mon("old-report", "Old report", {}, status="disabled"),
    _mon("noisy", "Noisy", {"failure_issue_threshold": 3}, muted=True, envs=("production", "staging")),
] + [_mon(f"filler-{i:03d}", f"Filler {i:03d}", {"schedule": "*/15 * * * *"}) for i in range(100)]

app = FastAPI()
calls: list[str] = []
FOREIGN_NEXT = {"on": False}   # a hostile page whose "next" link points at another host


def _token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication credentials were not provided.")
    t = authorization[7:]
    if t not in (READ_TOKEN, NO_PROJECT_TOKEN, NO_ORG_TOKEN):
        raise HTTPException(401, "Invalid token")
    return t


@app.get("/api/0/organizations/{org}/monitors/")
def monitors(org: str, request: Request, response: Response, cursor: str | None = None, per_page: int = 100,
             authorization: str | None = Header(None)):
    t = _token(authorization)
    calls.append(f"monitors {cursor or '0:0:0'} project={request.query_params.get('project')}")
    if t == NO_ORG_TOKEN:
        raise HTTPException(403, "You do not have permission to perform this action.")
    if org != ORG:
        raise HTTPException(404, "The requested resource does not exist")
    per_page = min(per_page, 100)
    offset = int((cursor or "0:0:0").split(":")[1])
    chunk = MONITORS[offset:offset + per_page]
    more = offset + per_page < len(MONITORS)
    base = str(request.url).split("&cursor=")[0]
    if FOREIGN_NEXT["on"]:
        base = "http://169.254.169.254/latest/meta-data/?x=1"
    nxt = f"0:{offset + per_page}:0"
    prev = f"0:{max(offset - per_page, 0)}:1"
    response.headers["Link"] = (f'<{base}&cursor={prev}>; rel="previous"; results="{"true" if offset else "false"}"; cursor="{prev}", '
                                f'<{base}&cursor={nxt}>; rel="next"; results="{"true" if more else "false"}"; cursor="{nxt}"')
    return chunk


@app.get("/api/0/projects/{org}/{project}/keys/")
def keys(org: str, project: str, authorization: str | None = Header(None)):
    t = _token(authorization)
    calls.append(f"keys {project}")
    if t != READ_TOKEN:
        raise HTTPException(403, "You do not have permission to perform this action.")
    if org != ORG or project not in KEYS:
        raise HTTPException(404, "The requested resource does not exist")
    return KEYS[project]
