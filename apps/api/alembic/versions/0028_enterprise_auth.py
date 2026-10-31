"""R69 — enterprise sign-in: require MFA per organization, team invitations, contact-sales requests.

organizations.require_mfa   members who sign in with a Argus password must have an authenticator
                            app (TOTP) or security key; SSO members get MFA from their own IdP
org_invites                 invite a teammate by email with a role; the link is single use, expires
                            after 7 days and is stored only as a hash; accepted on the invitee's
                            first sign-in with that (verified) email
sales_inquiries             "Talk to sales" form on the public site; no org, system role only
"""
from alembic import op

revision = "0028"; down_revision = "0027"; branch_labels = None; depends_on = None


def upgrade():
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS require_mfa BOOLEAN NOT NULL DEFAULT false")
    op.execute("""
    CREATE TABLE org_invites (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      email TEXT NOT NULL,
      role TEXT NOT NULL CHECK (role IN ('viewer', 'developer', 'sre', 'devops', 'admin')),
      token_hash TEXT NOT NULL UNIQUE,
      invited_by UUID REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '7 days',
      accepted_at TIMESTAMPTZ, accepted_by UUID REFERENCES users(id) ON DELETE SET NULL,
      revoked_at TIMESTAMPTZ);
    CREATE UNIQUE INDEX org_invites_open ON org_invites (org_id, lower(email)) WHERE accepted_at IS NULL AND revoked_at IS NULL;
    ALTER TABLE org_invites ENABLE ROW LEVEL SECURITY; ALTER TABLE org_invites FORCE ROW LEVEL SECURITY;
    CREATE POLICY org_invites_tenant ON org_invites USING (org_id = app_org_id()) WITH CHECK (org_id = app_org_id());
    CREATE POLICY org_invites_system ON org_invites TO jobwatch_system USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE, DELETE ON org_invites TO jobwatch_app, jobwatch_system;

    CREATE TABLE sales_inquiries (
      id BIGSERIAL PRIMARY KEY,
      name TEXT NOT NULL, email TEXT NOT NULL, company TEXT NOT NULL,
      team_size TEXT, interest TEXT[] NOT NULL DEFAULT '{}', message TEXT,
      source_ip TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
    GRANT SELECT, INSERT ON sales_inquiries TO jobwatch_system;
    GRANT USAGE ON SEQUENCE sales_inquiries_id_seq TO jobwatch_system;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS sales_inquiries; DROP TABLE IF EXISTS org_invites")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS require_mfa")
