"""R67 — Sentry Crons-compatible check-ins.

Sentry is source-available; everything here follows its own code, not guesses:
  routes        getsentry/relay relay-server/src/endpoints/mod.rs
                  /api/{project_id}/cron/{monitor_slug}[/{sentry_key}][/]   GET or POST
                  /api/{project_id}/envelope/                                 POST (what the SDKs use)
  HTTP check-in relay-server/src/endpoints/monitor.rs — JSON body when Content-Type is
                application/json, otherwise query: status, check_in_id, environment, duration (seconds)
  payload       relay-monitors/src/lib.rs CheckIn: check_in_id (nil UUID when absent), monitor_slug,
                status ok|error|in_progress (missed/unknown are not accepted from clients), environment
                (≤64 chars), duration (seconds), monitor_config
  slug          slugify_monitor_slug (Django slugify, 50 chars) — Sentry matches slugs after this
  auth          relay-server/src/extractors/request_meta.rs: X-Sentry-Auth, Authorization: Sentry …,
                Basic (key as user), ?sentry_key=, or the key path segment; envelopes also carry a `dsn`
  envelope      relay-server/src/envelope: header line, then items of <item header>\\n<payload>, where the
                payload is `length` bytes, or up to the next newline when the header has no length

JobWatch serves all of this under /sentry on the ingest host, so a DSN of
https://<key>@<ingest>/sentry/<project id> makes an SDK post to <ingest>/sentry/api/<project id>/envelope/.
"""
import base64
import json
import re
import unicodedata
import zlib
from urllib.parse import parse_qs, urlsplit

try:                                  # sentry-python compresses with brotli when the module is installed
    import brotli  # type: ignore
except ImportError:                   # pragma: no cover - depends on the image
    brotli = None

STATUSES = {"in_progress": "start", "ok": "success", "error": "fail"}
SLUG_LENGTH = 50
ENVIRONMENT_LENGTH = 64
MAX_BODY = 1_000_000            # compressed bytes read from the request
MAX_DECODED = 2_000_000         # bytes after decompression (a check-in is a few hundred bytes)
MAX_CHECKINS_PER_ENVELOPE = 20
NIL_UUID = "00000000000000000000000000000000"
PROJECT_RE = re.compile(r"[0-9]{1,20}")
KEY_RE = re.compile(r"[0-9a-fA-F]{32}")


class BadRequest(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def slugify(slug: str) -> str:
    """Same result as Sentry's slugify_monitor_slug (the Rust port's test table is in our tests)."""
    out, sep = [], False
    for c in unicodedata.normalize("NFKD", slug or ""):
        if not c.isascii():
            continue
        if c == "-" or c in "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f ":
            if not sep:
                out.append("-"); sep = True
        elif c.isalnum() or c == "_":
            out.append(c.lower()); sep = False
    s = "".join(out).strip("-_")[:SLUG_LENGTH]
    return s.rstrip("-")


def token(project_id: str | int, public_key: str, slug: str) -> str:
    """The ping credential an imported Sentry monitor keeps (stored only as a hash)."""
    return f"sentry:{project_id}:{public_key.lower()}:{slugify(slug)}"


def _pairs(header_value: str) -> dict:
    v = header_value.strip()
    if v[:7].lower() == "sentry ":
        v = v[7:]
    out = {}
    for part in v.split(","):
        k, _, val = part.strip().partition("=")
        if k:
            out[k.strip().lower()] = val.strip().strip('"')
    return out


def key_from_request(headers, query: str, path_key: str | None = None) -> str | None:
    """Public key from the same places Relay accepts it, in Relay's order."""
    h = headers.get("x-sentry-auth")
    if h:
        return _pairs(h).get("sentry_key")
    a = headers.get("authorization") or ""
    if a[:7].lower() == "sentry ":
        return _pairs(a).get("sentry_key")
    if a[:6].lower() == "basic ":
        try:
            return base64.b64decode(a[6:]).decode().split(":", 1)[0] or None
        except Exception:
            return None
    if "sentry_" in (query or ""):
        k = parse_qs(query).get("sentry_key")
        if k:
            return k[0]
    return path_key


def key_from_dsn(dsn: str | None) -> str | None:
    try:
        return urlsplit(dsn).username if dsn else None
    except ValueError:
        return None


def decode_body(raw: bytes, encoding: str | None) -> bytes:
    enc = (encoding or "identity").strip().lower()
    if enc in ("identity", ""):
        out = raw
    elif enc in ("gzip", "x-gzip", "deflate"):
        d = zlib.decompressobj(16 + zlib.MAX_WBITS if enc != "deflate" else zlib.MAX_WBITS)
        try:
            out = d.decompress(raw, MAX_DECODED + 1)
        except zlib.error:
            if enc != "deflate":
                raise BadRequest(400, "body is not valid gzip") from None
            try:                       # some clients send raw deflate without the zlib header
                out = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw, MAX_DECODED + 1)
            except zlib.error:
                raise BadRequest(400, "body is not valid deflate") from None
    elif enc == "br":
        if brotli is None:
            raise BadRequest(415, "brotli bodies are not supported by this server; set the SDK's transport compression to gzip")
        try:
            d = brotli.Decompressor()
            try:                       # brotli ≥ 1.2 caps the output; older versions have no limit argument
                out = d.process(raw, output_buffer_limit=MAX_DECODED + 1)
            except TypeError:
                out = d.process(raw)
        except BadRequest:
            raise
        except Exception:
            raise BadRequest(400, "body is not valid brotli") from None
    else:
        raise BadRequest(415, f"unsupported Content-Encoding {enc}")
    if len(out) > MAX_DECODED:
        raise BadRequest(413, "envelope too large")
    return out


def parse_envelope(data: bytes) -> tuple[dict, list[tuple[dict, bytes]]]:
    """Envelope → (header, [(item header, payload)]). Raises BadRequest on malformed input."""
    nl = data.find(b"\n")
    head_raw = data if nl < 0 else data[:nl]
    try:
        header = json.loads(head_raw or b"{}")
    except ValueError:
        raise BadRequest(400, "envelope header is not JSON") from None
    if not isinstance(header, dict):
        raise BadRequest(400, "envelope header is not an object")
    items: list[tuple[dict, bytes]] = []
    pos = len(data) if nl < 0 else nl + 1
    while pos < len(data):
        if data[pos:pos + 1] == b"\n":           # tolerate blank lines between items
            pos += 1; continue
        end = data.find(b"\n", pos)
        line = data[pos:] if end < 0 else data[pos:end]
        try:
            ih = json.loads(line)
        except ValueError:
            raise BadRequest(400, "envelope item header is not JSON") from None
        if not isinstance(ih, dict):
            raise BadRequest(400, "envelope item header is not an object")
        pos = len(data) if end < 0 else end + 1
        length = ih.get("length")
        if isinstance(length, int) and length >= 0:
            payload = data[pos:pos + length]
            if len(payload) < length:
                raise BadRequest(400, "envelope item is shorter than its length")
            pos += length
            if data[pos:pos + 1] == b"\n":
                pos += 1
        else:
            end = data.find(b"\n", pos)
            payload = data[pos:] if end < 0 else data[pos:end]
            pos = len(data) if end < 0 else end + 1
        items.append((ih, payload))
        if len(items) > 1000:
            raise BadRequest(400, "too many envelope items")
    return header, items


def checkin_fields(payload: dict) -> dict | None:
    """A Sentry check-in → HeartbeatBody keyword arguments, or None if it carries nothing JobWatch
    records (missed/unknown status, which Sentry also refuses from clients)."""
    status = STATUSES.get(str(payload.get("status") or "").lower())
    if status is None:
        return None
    cid = str(payload.get("check_in_id") or "").replace("-", "").lower()
    cid = None if not cid or cid == NIL_UUID or not re.fullmatch(r"[0-9a-f]{32}", cid) else cid
    dur = payload.get("duration")
    try:
        duration_ms = int(float(dur) * 1000) if dur is not None and 0 <= float(dur) < 31 * 86400 else None
    except (TypeError, ValueError):
        duration_ms = None
    env = payload.get("environment")
    meta = {"source": "sentry"}
    if isinstance(env, str) and env:
        meta["env"] = env[:ENVIRONMENT_LENGTH]
    release = payload.get("release")
    if isinstance(release, str) and release:
        meta["release"] = release[:200]
    return {"status": status, "duration_ms": duration_ms, "meta": meta,
            "execution_id": f"se-{cid}" if cid else None, "sequence": 0 if status == "start" else 1}
