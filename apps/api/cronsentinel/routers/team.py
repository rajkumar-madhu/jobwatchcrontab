"""R69 — team invitations, organization security settings, and the public "Talk to sales" form.

Invitations: an admin invites an email with a role. The response carries the invite link once (it
holds a random token stored only as a hash). The invitee signs up or signs in with that email —
verified by the identity provider — and the membership is created in the OIDC callback. The link
itself grants nothing; it identifies the invitation so the sign-up page can show who invited them.

Security: `require_mfa` makes password sign-ins to this organization need an authenticator app
(Keycloak enforces it; see routers/auth.callback). It can only be switched on when the server can
check second factors (the Keycloak admin client is configured).
"""
import hashlib
import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from .. import ratelimit
from ..auth import ROLE_ORDER, Principal, audit, require_role
from ..config import settings
from ..db import system_session, tenant_session

router = APIRouter(prefix="/api/v1/org", tags=["org"])
public = APIRouter(tags=["public"])

INVITE_ROLES = [r for r in ROLE_ORDER if r != "owner"]
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}")
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com", "icloud.com",
             "me.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "yandex.com", "zoho.com", "rediffmail.com", "mail.com"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InviteIn(BaseModel):
    email: str = Field(max_length=254)
    role: str = "developer"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not EMAIL.fullmatch(v):
            raise ValueError("not an email address")
        return v.lower()

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in INVITE_ROLES:
            raise ValueError(f"role must be one of {', '.join(INVITE_ROLES)}")
        return v


class InviteOut(BaseModel):
    id: UUID
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    status: str                      # pending | accepted | expired | revoked
    invite_url: str | None = None    # only in the create response


class SecurityIn(BaseModel):
    require_mfa: bool


class SecurityOut(BaseModel):
    require_mfa: bool
    mfa_checkable: bool              # the server can read second factors (Keycloak admin client configured)
    sso_enforced: bool


def _status(r) -> str:
    if r.revoked_at:
        return "revoked"
    if r.accepted_at:
        return "accepted"
    return "expired" if r.expired else "pending"


@router.get("/invites", response_model=list[InviteOut])
def list_invites(p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        rows = s.execute(text("""SELECT id, email, role, created_at, expires_at, accepted_at, revoked_at, expires_at <= now() AS expired
            FROM org_invites ORDER BY created_at DESC LIMIT 200""")).all()
    return [InviteOut(**{k: getattr(r, k) for k in ("id", "email", "role", "created_at", "expires_at")}, status=_status(r)) for r in rows]


@router.post("/invites", response_model=InviteOut, status_code=201)
def create_invite(body: InviteIn, request: Request, p: Principal = Depends(require_role("admin"))):
    if body.role == "admin" and p.role not in ("admin", "owner"):
        raise HTTPException(403, "only admins can invite admins")
    token = secrets.token_urlsafe(32)
    with tenant_session(p.org_id) as s:
        if s.execute(text("SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.org_id = :o AND lower(u.email) = :e"), {"o": str(p.org_id), "e": body.email}).first():
            raise HTTPException(409, "this person is already a member")
        if s.execute(text("""SELECT 1 FROM org_invites WHERE lower(email) = :e AND accepted_at IS NULL AND revoked_at IS NULL
                             AND expires_at > now()"""), {"e": body.email}).first():
            raise HTTPException(409, "an invitation for this email is already pending; revoke it to send a new one")
        # an expired open invite still holds the unique slot: close it before inserting a new one
        s.execute(text("UPDATE org_invites SET revoked_at = now() WHERE lower(email) = :e AND accepted_at IS NULL AND revoked_at IS NULL"), {"e": body.email})
        r = s.execute(text("""INSERT INTO org_invites (org_id, email, role, token_hash, invited_by) VALUES (:o, :e, :r, :h, :u)
            RETURNING id, email, role, created_at, expires_at"""),
            {"o": str(p.org_id), "e": body.email, "r": body.role, "h": _hash(token), "u": str(p.user_id) if p.user_id else None}).first()
        audit(s, p, "invite.create", "invite", str(r.id), {"email": body.email, "role": body.role}, request.client.host if request.client else None)
    url = f"{settings.web_public_url.rstrip('/')}/signup?invite={token}"
    return InviteOut(**dict(r._mapping), status="pending", invite_url=url)


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: UUID, request: Request, p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        r = s.execute(text("UPDATE org_invites SET revoked_at = now() WHERE id = :i AND accepted_at IS NULL AND revoked_at IS NULL RETURNING id"),
                      {"i": str(invite_id)}).first()
        if not r:
            raise HTTPException(404, "no pending invitation with this id")
        audit(s, p, "invite.revoke", "invite", str(invite_id), {}, request.client.host if request.client else None)


@router.get("/security", response_model=SecurityOut)
def get_security(p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        r = s.execute(text("""SELECT o.require_mfa, COALESCE(os.enforce AND os.enabled, false) AS sso
            FROM organizations o LEFT JOIN org_sso os ON os.org_id = o.id WHERE o.id = :o"""), {"o": str(p.org_id)}).first()
    return SecurityOut(require_mfa=bool(r and r.require_mfa), mfa_checkable=bool(settings.keycloak_admin_client_secret), sso_enforced=bool(r and r.sso))


@router.put("/security", response_model=SecurityOut)
def put_security(body: SecurityIn, request: Request, p: Principal = Depends(require_role("owner"))):
    if body.require_mfa and not settings.keycloak_admin_client_secret:
        raise HTTPException(409, "this server cannot check second factors: configure the Keycloak admin client "
                                 "(KEYCLOAK_ADMIN_CLIENT_SECRET) before requiring MFA")
    with tenant_session(p.org_id) as s:
        s.execute(text("UPDATE organizations SET require_mfa = :m WHERE id = :o"), {"m": body.require_mfa, "o": str(p.org_id)})
        audit(s, p, "security.require_mfa", "org", str(p.org_id), {"require_mfa": body.require_mfa}, request.client.host if request.client else None)
    return get_security(p)


# ---- public ---------------------------------------------------------------------------------------

@public.get("/auth/invite/{token}")
def invite_preview(token: str, request: Request):
    """What the sign-up page shows for an invite link: who invited you, to which organization, as what.
    Rate limited per address; an unknown, used or revoked token is a 404 without detail."""
    ratelimit.check(f"invite:{request.client.host if request.client else 'unknown'}", 30, request)
    if not (20 <= len(token) <= 100):
        raise HTTPException(404, "invitation not found")
    with system_session() as s:
        r = s.execute(text("""SELECT i.email, i.role, i.expires_at, i.expires_at <= now() AS expired, o.name AS org,
                                     COALESCE(u.name, u.email) AS inviter
            FROM org_invites i JOIN organizations o ON o.id = i.org_id LEFT JOIN users u ON u.id = i.invited_by
            WHERE i.token_hash = :h AND i.accepted_at IS NULL AND i.revoked_at IS NULL"""), {"h": _hash(token)}).first()
    if not r:
        raise HTTPException(404, "invitation not found")
    return {"email": r.email, "role": r.role, "organization": r.org, "invited_by": r.inviter, "expired": bool(r.expired),
            "expires_at": r.expires_at}


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    company: str = Field(min_length=1, max_length=200)
    team_size: str | None = Field(default=None, max_length=40)
    interest: list[str] = Field(default=[], max_length=8)
    message: str | None = Field(default=None, max_length=4000)
    website: str | None = None       # honeypot: real visitors never fill it

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not EMAIL.fullmatch(v):
            raise ValueError("not an email address")
        return v


@public.post("/public/contact", status_code=202)
def contact_sales(body: ContactIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    ratelimit.check(f"contact:{ip}", 5, request)
    if body.website:                  # bot: accept silently, store nothing
        return {"ok": True}
    with system_session() as s:
        s.execute(text("""INSERT INTO sales_inquiries (name, email, company, team_size, interest, message, source_ip)
            VALUES (:n, :e, :c, :t, :i, :m, :ip)"""),
            {"n": body.name.strip(), "e": body.email, "c": body.company.strip(), "t": body.team_size,
             "i": [x[:40] for x in body.interest], "m": body.message, "ip": ip})
    return {"ok": True}


def is_free_mail(email: str) -> bool:
    return email.rsplit("@", 1)[-1].lower() in FREE_MAIL


# ---- members --------------------------------------------------------------------------------------

class MemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str | None
    role: str
    joined_at: datetime
    managed_by_directory: bool       # provisioned over SCIM: role changes come from directory groups


class MemberPatch(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in INVITE_ROLES:
            raise ValueError(f"role must be one of {', '.join(INVITE_ROLES)} (ownership is transferred, not assigned)")
        return v


@router.get("/members", response_model=list[MemberOut])
def list_members(p: Principal = Depends(require_role("viewer"))):
    with tenant_session(p.org_id) as s:
        rows = s.execute(text("""SELECT u.id AS user_id, u.email, u.name, m.role::text AS role, m.created_at AS joined_at,
                EXISTS (SELECT 1 FROM scim_users su WHERE su.org_id = m.org_id AND su.user_id = u.id AND su.active) AS managed_by_directory
            FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.org_id = :o
            ORDER BY array_position(ARRAY['owner','admin','devops','sre','developer','viewer'], m.role::text), lower(u.email)"""), {"o": str(p.org_id)}).all()
    return [MemberOut(**dict(r._mapping)) for r in rows]


def _target(s, org_id, user_id):
    t = s.execute(text("SELECT role::text AS role FROM memberships WHERE org_id = :o AND user_id = :u"), {"o": str(org_id), "u": str(user_id)}).first()
    if not t:
        raise HTTPException(404, "not a member of this organization")
    return t


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_role(user_id: UUID, body: MemberPatch, request: Request, p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        t = _target(s, p.org_id, user_id)
        if t.role == "owner":
            raise HTTPException(403, "an owner's role cannot be changed here")
        if body.role == "admin" and p.role != "owner" and t.role != "admin":
            raise HTTPException(403, "only owners can make someone an admin")
        s.execute(text("UPDATE memberships SET role = :r WHERE org_id = :o AND user_id = :u"), {"r": body.role, "o": str(p.org_id), "u": str(user_id)})
        audit(s, p, "member.role", "user", str(user_id), {"from": t.role, "to": body.role}, request.client.host if request.client else None)
    return next(m for m in list_members(p) if m.user_id == user_id)


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: UUID, request: Request, p: Principal = Depends(require_role("admin"))):
    with tenant_session(p.org_id) as s:
        t = _target(s, p.org_id, user_id)
        if t.role == "owner":
            raise HTTPException(403, "owners cannot be removed; transfer ownership first")
        if t.role == "admin" and p.role != "owner":
            raise HTTPException(403, "only owners can remove admins")
        s.execute(text("DELETE FROM memberships WHERE org_id = :o AND user_id = :u"), {"o": str(p.org_id), "u": str(user_id)})
        audit(s, p, "member.remove", "user", str(user_id), {"role": t.role}, request.client.host if request.client else None)
