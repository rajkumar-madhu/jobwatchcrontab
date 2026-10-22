"""R43: Keycloak Admin API client against a mock transport."""
import json

import httpx

from cronsentinel import keycloak_admin as kc
from cronsentinel.config import settings


def test_upsert_creates_then_updates_and_maps_saml_attributes(monkeypatch):
    monkeypatch.setattr(settings, "keycloak_issuer", "https://kc.test/realms/cronsentinel")
    monkeypatch.setattr(settings, "keycloak_admin_client_secret", "x")
    kc._token.clear()
    seen, exists = [], {"v": False}
    def h(req):
        seen.append((req.method, req.url.path))
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        if req.method == "GET" and req.url.path.endswith("/mappers"):
            return httpx.Response(200, json=[])
        if req.method == "GET":
            return httpx.Response(200 if exists["v"] else 404, json={})
        return httpx.Response(201 if req.method == "POST" else 204)
    c = httpx.Client(transport=httpx.MockTransport(h))
    cfg = {"entity_id": "urn:idp", "sso_url": "https://idp.test/sso", "signing_cert": "MIIB"}
    kc.upsert_idp("org-1", "saml", "ADFS", cfg, client=c)
    assert ("POST", "/admin/realms/cronsentinel/identity-provider/instances") in seen
    assert sum(1 for m, p in seen if m == "POST" and p.endswith("/mappers")) == 3
    exists["v"] = True; seen.clear()
    kc.upsert_idp("org-1", "saml", "ADFS", cfg, client=c)
    assert ("PUT", "/admin/realms/cronsentinel/identity-provider/instances/org-1") in seen
    assert kc.broker_redirect_uri("org-1") == "https://kc.test/realms/cronsentinel/broker/org-1/endpoint"


def test_oidc_representation_uses_discovered_endpoints_and_pkce():
    rep = kc.idp_representation("org-1", "oidc", "Okta", {"issuer": "https://acme.okta.test", "client_id": "c", "client_secret": "s",
                                 "authorization_url": "https://a", "token_url": "https://t", "jwks_url": "https://k"})
    cfg = rep["config"]
    assert (cfg["authorizationUrl"], cfg["tokenUrl"], cfg["jwksUrl"], cfg["useJwksUrl"]) == ("https://a", "https://t", "https://k", "true")
    assert cfg["pkceEnabled"] == "true" and cfg["validateSignature"] == "true" and rep["trustEmail"] is True
    json.dumps(rep)


def test_disabled_representation_keeps_the_idp():
    rep = kc.idp_representation("org-1", "oidc", "Okta", {"issuer": "https://i", "client_id": "c", "client_secret": "s"}, enabled=False)
    assert rep["enabled"] is False and rep["alias"] == "org-1"


def _kc(monkeypatch, handler):
    monkeypatch.setattr(settings, "keycloak_issuer", "https://kc.test/realms/cronsentinel")
    monkeypatch.setattr(settings, "keycloak_admin_client_secret", "x")
    kc._token.clear()
    def h(req):
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 60})
        return handler(req)
    return httpx.Client(transport=httpx.MockTransport(h))


def test_mfa_methods_reads_credentials(monkeypatch):   # R69
    c = _kc(monkeypatch, lambda req: httpx.Response(200, json=[{"type": "password"}, {"type": "otp"}, {"type": "webauthn"}]))
    assert kc.mfa_methods("u1", client=c) == {"otp", "webauthn"}
    c = _kc(monkeypatch, lambda req: httpx.Response(200, json=[{"type": "password"}]))
    assert kc.mfa_methods("u1", client=c) == set()
    c = _kc(monkeypatch, lambda req: httpx.Response(403, json={}))
    import pytest
    with pytest.raises(kc.KeycloakAdminError):
        kc.mfa_methods("u1", client=c)


def test_require_totp_setup_adds_the_action_once(monkeypatch):   # R69
    puts, state = [], {"actions": ["VERIFY_EMAIL"]}
    def h(req):
        if req.method == "GET":
            assert req.url.path == "/admin/realms/cronsentinel/users/u1"
            return httpx.Response(200, json={"id": "u1", "requiredActions": state["actions"]})
        puts.append(json.loads(req.content)); state["actions"] = puts[-1]["requiredActions"]
        return httpx.Response(204)
    c = _kc(monkeypatch, h)
    kc.require_totp_setup("u1", client=c)
    kc.require_totp_setup("u1", client=c)
    assert puts == [{"requiredActions": ["VERIFY_EMAIL", "CONFIGURE_TOTP"]}]
