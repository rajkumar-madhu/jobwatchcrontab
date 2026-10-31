"""R67 — import cron monitors from Sentry, keeping check-in URLs and SDK DSNs working.

Built from Sentry's source (getsentry/sentry), not only its docs:
  List      GET {base}/api/0/organizations/{org}/monitors/?project=-1  (Bearer auth token, scope
            org:read or alerts:read). Cursor paging: follow the Link header's rel="next" while
            results="true" (sentry/api/base.py).
  Monitor   MonitorSerializerResponse: id, name, slug, status ("active" | "disabled"), isMuted,
            config {schedule_type "crontab" | "interval", schedule "<cron>" | [n, unit],
            checkin_margin and max_runtime in minutes, timezone, failure_issue_threshold,
            recovery_threshold}, project {id, slug}, environments [...]
            Defaults when null (sentry/monitors/constants.py): checkin_margin 1, max_runtime 30.
  Keys      GET {base}/api/0/projects/{org}/{project}/keys/ (scope project:read): [{public, isActive}]
            The public key is what check-ins authenticate with; with it each job keeps
            "sentry:<project id>:<key>:<slug>" as its ping token, so only the host changes.

Mapping:
  crontab                    same expression and timezone
  interval n minute|hour|day|week   cron when the period divides the clock (as for Cronitor), with extra
                             grace of one period — Sentry anchors intervals to the first check-in
  interval 1 month | 1 year  first of the month / year at midnight, flagged for review
  checkin_margin             grace (minutes → seconds)
  max_runtime                expected runtime (minutes → seconds)
  status disabled            paused
  isMuted, thresholds > 1, several environments   reported in the note
"""
import re
from urllib.parse import urlsplit

from .. import netguard, schedule, sentrycompat
from .cronitor import _PERIOD_CRON

PAGE_SIZE = 100
MAX_MONITORS = 5000
DEFAULT_MARGIN_MIN = 1
DEFAULT_RUNTIME_MIN = 30
ORG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,63}")
_UNITS = {"minute": 60, "hour": 3600, "day": 86400, "week": 604800}
_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"\s*;\s*results="(true|false)"')


class ImportError_(Exception):
    pass


def _next_link(header: str | None) -> str | None:
    for m in _LINK.finditer(header or ""):
        return m.group(1) if m.group(2) == "true" else None
    return None


def fetch(auth_token: str, organization: str, base_url: str = "https://sentry.io") -> tuple[list[dict], dict[str, str | None], list[str]]:
    """→ (monitors, {project id: active public key or None}, warnings)."""
    base = (base_url or "https://sentry.io").rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise ImportError_("base_url must be an http(s) URL")
    if not ORG_RE.fullmatch(organization or ""):
        raise ImportError_("organization must be the organization slug from your Sentry URL")
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(base))
    headers = {"Authorization": f"Bearer {auth_token}", "Accept": "application/json"}
    monitors: list[dict] = []
    keys: dict[str, str | None] = {}
    warnings: list[str] = []
    try:
        netguard.check_url(base + "/api/0/")
        with netguard.client(timeout=20) as c:
            url: str | None = f"{base}/api/0/organizations/{organization}/monitors/?project=-1&per_page={PAGE_SIZE}"
            for _ in range(MAX_MONITORS // PAGE_SIZE + 2):
                r = c.get(url, headers=headers)
                if r.status_code == 401:
                    raise ImportError_("Sentry rejected the auth token")
                if r.status_code == 403:
                    raise ImportError_("the auth token cannot read monitors (it needs the org:read or alerts:read scope)")
                if r.status_code == 404:
                    raise ImportError_(f"Sentry has no organization '{organization}' for this token")
                if r.status_code == 429:
                    raise ImportError_("Sentry is rate limiting this token; try again in a minute")
                if r.status_code != 200:
                    raise ImportError_(f"Sentry API returned {r.status_code}")
                batch = r.json()
                if not isinstance(batch, list):
                    raise ImportError_("unexpected response from the Sentry API")
                monitors.extend(m for m in batch if isinstance(m, dict))
                url = _next_link(r.headers.get("link"))
                # only ever follow paging links back to the same Sentry host
                if not url or not url.startswith(origin + "/") or len(monitors) >= MAX_MONITORS:
                    break
            projects = {}
            for m in monitors:
                p = m.get("project") or {}
                if p.get("id") is not None and p.get("slug"):
                    projects[str(p["id"])] = str(p["slug"])
            for pid, pslug in projects.items():
                r = c.get(f"{base}/api/0/projects/{organization}/{pslug}/keys/", headers=headers)
                if r.status_code != 200:
                    keys[pid] = None
                    warnings.append(f"could not read the client keys of project {pslug} (Sentry answered {r.status_code}; "
                                    "the token needs project:read) — its jobs get new ping URLs")
                    continue
                active = [k for k in (r.json() or []) if isinstance(k, dict) and k.get("isActive", True)
                          and isinstance(k.get("public"), str) and sentrycompat.KEY_RE.fullmatch(k["public"])]
                keys[pid] = active[0]["public"].lower() if active else None
                if len(active) > 1:
                    warnings.append(f"project {pslug} has {len(active)} active client keys; check-ins must use the first one "
                                    f"(…{active[0]['public'][-4:]}) to reach Argus")
                elif not active:
                    warnings.append(f"project {pslug} has no active client key — its jobs get new ping URLs")
    except netguard.BlockedDestination as e:
        raise ImportError_(f"base_url: {e}") from None
    except ImportError_:
        raise
    except Exception:
        raise ImportError_("could not reach the Sentry API") from None
    return monitors[:MAX_MONITORS], keys, warnings


def translate_schedule(schedule_type: str | None, value) -> tuple[str | None, int, str | None]:
    """Sentry config schedule → (cron or None, extra grace seconds, note)."""
    if schedule_type == "crontab" and isinstance(value, str):
        e = value.strip()
        if schedule.validate(e):
            return e, 0, None
        return None, 0, f"crontab '{e}' could not be read; imported without a schedule"
    if schedule_type == "interval" and isinstance(value, list | tuple) and len(value) == 2:
        try:
            n, unit = int(value[0]), str(value[1]).lower()
        except (TypeError, ValueError):
            return None, 0, "interval schedule could not be read; imported without a schedule"
        label = f"every {n} {unit}{'s' if n != 1 else ''}"
        if unit in _UNITS:
            period = n * _UNITS[unit]
            cron = _PERIOD_CRON.get(period)
            if cron:
                return cron, period, f"'{label}' became '{cron}' with extra grace {period} s; review the schedule"
        elif n == 1 and unit in ("month", "year"):
            cron = "0 0 1 * *" if unit == "month" else "0 0 1 1 *"
            return cron, 86400, f"'{label}' became '{cron}' with extra grace 1 day; review the schedule"
        return None, 0, f"'{label}' has no cron equivalent; imported without a schedule — set one to detect missed runs"
    return None, 0, "no schedule in Sentry"


def map_monitor(mon: dict, public_key: str | None) -> dict:
    """One Sentry monitor → the shape routers/imports._apply expects."""
    slug = str(mon.get("slug") or "")
    name = str(mon.get("name") or slug or "unnamed monitor")[:200]
    cfg = mon.get("config") or {}
    notes: list[str] = []
    cron, extra, n = translate_schedule(cfg.get("schedule_type"), cfg.get("schedule"))
    if n:
        notes.append(n)

    def _minutes(field: str, default: int) -> int:
        v = cfg.get(field)
        try:
            return max(int(v), 0) if v is not None else default
        except (TypeError, ValueError):
            return default
    grace = _minutes("checkin_margin", DEFAULT_MARGIN_MIN) * 60
    runtime = _minutes("max_runtime", DEFAULT_RUNTIME_MIN) * 60
    if mon.get("isMuted"):
        notes.append("muted in Sentry; imported active — pause it in Argus to keep it quiet")
    try:
        fails = int(cfg.get("failure_issue_threshold") or 1)
    except (TypeError, ValueError):
        fails = 1
    if fails > 1:
        notes.append(f"Sentry waited for {fails} failed check-ins before alerting; Argus alerts on the first")
    envs = [e.get("name") for e in (mon.get("environments") or []) if isinstance(e, dict) and e.get("name")]
    if len(envs) > 1:
        notes.append(f"Sentry tracked {len(envs)} environments ({', '.join(envs[:4])}); in Argus all check-ins go to this job")
    project = mon.get("project") or {}
    pid = project.get("id")
    tags = ["sentry"] + ([f"project:{project['slug']}"[:60]] if project.get("slug") else [])
    tok = (sentrycompat.token(pid, public_key, slug)
           if public_key and pid is not None and sentrycompat.PROJECT_RE.fullmatch(str(pid)) and sentrycompat.slugify(slug) else None)
    status = "imported" if cron and not any("became" in x for x in notes) else ("converted" if cron else "needs_schedule")
    return {"job": {"name": name, "description": None, "tags": tags, "kind": "heartbeat",
                    "paused": mon.get("status") == "disabled", "tz": cfg.get("timezone") or "UTC", "schedule_expr": cron,
                    "grace_s": grace + extra, "expected_runtime_s": runtime or None, "assertions": []},
            "token": tok, "status": status, "note": "; ".join(notes) or None}
