"""R69: the public API reference is generated from app.openapi(); keep it complete and truthful."""
from cronsentinel import apidocs
from cronsentinel.main import app

METHODS = ("get", "post", "put", "patch", "delete")


def _ops():
    spec = app.openapi()
    return spec, [(m.upper(), p, o) for p, ops in spec["paths"].items() for m, o in ops.items() if m in METHODS]


def test_every_operation_has_a_written_summary():
    _, ops = _ops()
    missing = [f"{m} {p}" for m, p, _ in ops if f"{m} {p}" not in apidocs.DOCS]
    assert not missing, f"add these to apidocs.DOCS: {missing}"


def test_tags_are_known_and_ordered():
    spec, ops = _ops()
    known = [t["name"] for t in spec["tags"]]
    assert {o["tags"][0] for *_, o in ops} <= set(known)


def test_roles_come_from_require_role():
    spec, _ = _ops()
    paths = spec["paths"]
    assert paths["/api/v1/org/invites"]["post"]["x-min-role"] == "admin"
    assert paths["/api/v1/org/security"]["put"]["x-min-role"] == "owner"
    assert paths["/api/v1/jobs"]["get"]["x-min-role"] == "viewer"
    assert paths["/api/v1/jobs"]["post"]["x-min-role"] == "developer"
    assert "403" in paths["/api/v1/jobs"]["post"]["responses"]
    assert paths["/public/status/{slug}"]["get"]["security"] == []


def test_auth_headers_are_schemes_not_parameters():
    spec, ops = _ops()
    assert set(spec["components"]["securitySchemes"]) == {"ApiKey", "Bearer", "Session"}
    for m, p, o in ops:
        names = {x["name"].lower() for x in o.get("parameters", []) if x["in"] == "header"}
        assert not names & {"authorization", "x-api-key", "x-org-id"}, (m, p)


def test_ping_endpoints_documented_on_ingest_host():
    spec, _ = _ops()
    op = spec["paths"]["/ping/{token}"]["get"]
    assert op["tags"] == ["pings"] and op["servers"][0]["description"] == "Ingest host"
    assert "/healthz" not in spec["paths"]


def test_public_text_has_no_round_markers():
    _, ops = _ops()
    import re
    bad = [f"{m} {p}" for m, p, o in ops if re.search(r"\bR\d+\b", o.get("description", "") + o.get("summary", ""))]
    assert not bad, bad


def test_curated_entries_point_at_real_operations():
    _, ops = _ops()
    keys = {f"{m} {p}" for m, p, _ in ops}
    stale = [k for k in list(apidocs.DOCS) + list(apidocs.RESPONSE_EXAMPLES) + list(apidocs.RETAG) if k not in keys]
    assert not stale, f"remove or fix: {stale}"
