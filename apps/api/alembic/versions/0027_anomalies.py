"""R68 — unusual-run detection settings per job (cronsentinel/anomaly.py).

anomaly_sensitivity: off | low | normal | high (default normal). Detection only records findings on
the run and, in warn mode, emits the `anomaly` alert condition — nothing pages unless an alert rule
for that condition exists, so turning this on for existing jobs changes no one's alerts.
anomaly_action: warn (run stays successful, rule condition `anomaly`) | fail (run becomes a failure).
"""
from alembic import op

revision = "0027"; down_revision = "0026"; branch_labels = None; depends_on = None


def upgrade():
    op.execute("""ALTER TABLE jobs
        ADD COLUMN IF NOT EXISTS anomaly_sensitivity TEXT NOT NULL DEFAULT 'normal'
            CHECK (anomaly_sensitivity IN ('off', 'low', 'normal', 'high')),
        ADD COLUMN IF NOT EXISTS anomaly_action TEXT NOT NULL DEFAULT 'warn'
            CHECK (anomaly_action IN ('warn', 'fail'))""")


def downgrade():
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS anomaly_sensitivity, DROP COLUMN IF EXISTS anomaly_action")
