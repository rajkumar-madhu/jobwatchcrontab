"""R70 — host context on the job page: what the server a job runs on looks like.

servers.facts             what the agent reports with each heartbeat (os, kernel, arch, cpus,
                          mem_total_mb, disk_total_gb, uptime_s, load5/15, timezone, virt);
                          rarely changing, so a JSONB column rather than a time series
servers.facts_updated_at  when the agent last reported them
(host_metrics already has PRIMARY KEY (server_id, ts), which serves the per-server range reads.)
"""
from alembic import op

revision = "0029"; down_revision = "0028"; branch_labels = None; depends_on = None


def upgrade():
    op.execute("ALTER TABLE servers ADD COLUMN IF NOT EXISTS facts JSONB NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE servers ADD COLUMN IF NOT EXISTS facts_updated_at TIMESTAMPTZ")


def downgrade():
    op.execute("ALTER TABLE servers DROP COLUMN IF EXISTS facts_updated_at, DROP COLUMN IF EXISTS facts")
