"""R69: team invitations, members, organization security settings, and the public contact form."""
import uuid

import pytest
from sqlalchemy import text


@pytest.fixture
def team(org):
    from fastapi.testclient import TestClient

    from cronsentinel.auth import generate_api_key, hash_secret
    from cronsentinel.db import system_session
    from cronsentinel.main import app
    keys = {}
    with system_session() as s:
        for role in ("owner", "admin", "developer"):
            prefix, raw = generate_api_key()
            s.execute(text("INSERT INTO api_keys (org_id, name, prefix, key_hash, role) VALUES (:o, :n, :p, :h, :r)"),
                      {"o": org["id"], "n": role, "p": prefix, "h": hash_secret(raw), "r": role})
            keys[role] = {"X-API-Key": raw}
        users = {}
        for email, role in (("own@acme.test", "owner"), ("adm@acme.test", "admin"), ("dev@acme.test", "developer"), ("scim@acme.test", "viewer")):
            email = f"{uuid.uuid4().hex[:6]}-{email}"
            uid = s.execute(text("INSERT INTO users (email, name) VALUES (:e, :n) RETURNING id"), {"e": email, "n": email.split("@")[0]}).scalar()
            s.execute(text("INSERT INTO memberships (user_id, org_id, role) VALUES (:u, :o, :r)"), {"u": uid, "o": org["id"], "r": role})
            users[role] = (str(uid), email)
        s.execute(text("INSERT INTO scim_users (org_id, user_id, external_id, active) VALUES (:o, :u, 'ext-1', true)"),
                  {"o": org["id"], "u": users["viewer"][0]})
    yield TestClient(app, raise_server_exceptions=False), keys, users
    with system_session() as s:
        s.execute(text("DELETE FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": [u for u, _ in users.values()]})


def test_members_list_roles_and_directory_flag(team):
    c, k, u = team
    rows = c.get("/api/v1/org/members", headers=k["developer"]).json()
    assert [r["role"] for r in rows] == ["owner", "admin", "developer", "viewer"]          # owners first
    assert {r["email"]: r["managed_by_directory"] for r in rows}[u["viewer"][1]] is True


def test_role_changes_follow_the_hierarchy(team):
    c, k, u = team
    dev = u["developer"][0]
    assert c.patch(f"/api/v1/org/members/{dev}", headers=k["developer"], json={"role": "sre"}).status_code == 403
    assert c.patch(f"/api/v1/org/members/{dev}", headers=k["admin"], json={"role": "sre"}).json()["role"] == "sre"
    assert c.patch(f"/api/v1/org/members/{dev}", headers=k["admin"], json={"role": "admin"}).status_code == 403    # only owners make admins
    assert c.patch(f"/api/v1/org/members/{dev}", headers=k["owner"], json={"role": "admin"}).json()["role"] == "admin"
    assert c.patch(f"/api/v1/org/members/{u['owner'][0]}", headers=k["owner"], json={"role": "viewer"}).status_code == 403
    assert c.patch(f"/api/v1/org/members/{dev}", headers=k["owner"], json={"role": "owner"}).status_code == 422
    assert c.patch(f"/api/v1/org/members/{uuid.uuid4()}", headers=k["owner"], json={"role": "viewer"}).status_code == 404


def test_removal_rules_and_audit(team, org):
    c, k, u = team
    assert c.delete(f"/api/v1/org/members/{u['owner'][0]}", headers=k["owner"]).status_code == 403
    assert c.delete(f"/api/v1/org/members/{u['admin'][0]}", headers=k["admin"]).status_code == 403             # admins cannot remove admins
    assert c.delete(f"/api/v1/org/members/{u['developer'][0]}", headers=k["admin"]).status_code == 204
    assert u["developer"][1] not in {r["email"] for r in c.get("/api/v1/org/members", headers=k["admin"]).json()}
    from cronsentinel.db import system_session
    with system_session() as s:
        assert s.execute(text("SELECT count(*) FROM audit_logs WHERE org_id=:o AND action='member.remove'"), {"o": org["id"]}).scalar() == 1


def test_invite_lifecycle_and_preview(team, org):
    c, k, u = team
    assert c.post("/api/v1/org/invites", headers=k["developer"], json={"email": "new@acme.test"}).status_code == 403
    r = c.post("/api/v1/org/invites", headers=k["admin"], json={"email": "New@Acme.test", "role": "sre"})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["email"] == "new@acme.test" and inv["status"] == "pending" and "/signup?invite=" in inv["invite_url"]
    token = inv["invite_url"].split("invite=")[1]
    p = c.get(f"/auth/invite/{token}").json()
    assert p["email"] == "new@acme.test" and p["role"] == "sre" and p["organization"].startswith("it-") and p["expired"] is False
    assert c.get(f"/auth/invite/{'x' * 43}").status_code == 404
    assert c.post("/api/v1/org/invites", headers=k["admin"], json={"email": "new@acme.test"}).status_code == 409            # already pending
    assert c.post("/api/v1/org/invites", headers=k["admin"], json={"email": u["developer"][1]}).status_code == 409         # already a member
    assert c.post("/api/v1/org/invites", headers=k["admin"], json={"email": "x@acme.test", "role": "owner"}).status_code == 422
    assert c.post("/api/v1/org/invites", headers=k["admin"], json={"email": "not-an-email"}).status_code == 422
    listed = c.get("/api/v1/org/invites", headers=k["admin"]).json()
    assert [x["email"] for x in listed] == ["new@acme.test"] and "invite_url" not in listed[0] or listed[0]["invite_url"] is None
    assert c.delete(f"/api/v1/org/invites/{inv['id']}", headers=k["admin"]).status_code == 204
    assert c.get(f"/auth/invite/{token}").status_code == 404                                                          # revoked: link dead
    assert c.get("/api/v1/org/invites", headers=k["admin"]).json()[0]["status"] == "revoked"
    assert c.post("/api/v1/org/invites", headers=k["admin"], json={"email": "new@acme.test"}).status_code == 201          # can re-invite
    from cronsentinel.db import system_session
    with system_session() as s:
        stored = s.execute(text("SELECT token_hash FROM org_invites WHERE org_id=:o"), {"o": org["id"]}).scalars().all()
    assert token not in stored                                                                                         # only the hash is kept


def test_require_mfa_setting(team, monkeypatch):
    c, k, _ = team
    from cronsentinel.config import settings
    assert c.get("/api/v1/org/security", headers=k["admin"]).json()["require_mfa"] is False
    assert c.put("/api/v1/org/security", headers=k["admin"], json={"require_mfa": True}).status_code == 403            # owners only
    monkeypatch.setattr(settings, "keycloak_admin_client_secret", "")
    r = c.put("/api/v1/org/security", headers=k["owner"], json={"require_mfa": True})
    assert r.status_code == 409 and "KEYCLOAK_ADMIN_CLIENT_SECRET" in r.text                                          # cannot enforce what cannot be checked
    monkeypatch.setattr(settings, "keycloak_admin_client_secret", "set")
    r = c.put("/api/v1/org/security", headers=k["owner"], json={"require_mfa": True}).json()
    assert r == {"require_mfa": True, "mfa_checkable": True, "sso_enforced": False}


def test_contact_form(team):
    c, _, _ = team
    body = {"name": "Priya", "email": "priya@bigbank.test", "company": "BigBank", "team_size": "1000+", "interest": ["sso", "self-hosted"],
            "message": "We run 4,000 cron jobs."}
    assert c.post("/public/contact", json=body).status_code == 202
    assert c.post("/public/contact", json={**body, "website": "http://spam"}).status_code == 202                        # honeypot: accepted, not stored
    assert c.post("/public/contact", json={**body, "email": "nope"}).status_code == 422
    from cronsentinel.db import system_session
    with system_session() as s:
        rows = s.execute(text("SELECT company, interest FROM sales_inquiries WHERE email='priya@bigbank.test'")).all()
        s.execute(text("DELETE FROM sales_inquiries WHERE email='priya@bigbank.test'"))
    assert [(r.company, list(r.interest)) for r in rows] == [("BigBank", ["sso", "self-hosted"])]
    codes = [c.post("/public/contact", json=body).status_code for _ in range(6)]
    assert 429 in codes                                                                                                # 5 a minute per address
    with system_session() as s:
        s.execute(text("DELETE FROM sales_inquiries WHERE email='priya@bigbank.test'"))
