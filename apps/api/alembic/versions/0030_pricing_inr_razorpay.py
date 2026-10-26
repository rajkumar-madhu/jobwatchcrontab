"""R75 — pricing from the go-to-market research, INR plans, and a second billing provider.

Tiers (docs/BILLING.md): the per-job price was twice the market's anchor, so the caps move and the
dollars stay. Developer 50 → 100 jobs ($0.19/job, parity with Healthchecks.io and Dead Man's
Snitch); Team 500 → 1,000 jobs with 12-month retention; Business unlimited jobs. Free keeps 5 jobs
but gains Slack and webhooks, so a free user sees an alert fire. Enterprise gets a published floor
(yearly_usd) instead of "contact sales".

INR: flat Indian prices (monthly_inr / yearly_inr, GST extra), paid through Razorpay subscriptions
(UPI AutoPay, cards, net banking). Starting points from the research — 40–60 % of US sticker — not
tested prices. plan_limits.razorpay_plan_* hold the Razorpay Plan ids created in the dashboard.

subscriptions.provider says which processor owns the row; one org has one provider at a time.
razorpay_events mirrors stripe_events for webhook idempotency.
"""
from alembic import op

revision = "0030"; down_revision = "0029"; branch_labels = None; depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE plan_limits
      ADD COLUMN IF NOT EXISTS yearly_usd NUMERIC(8,2),
      ADD COLUMN IF NOT EXISTS monthly_inr NUMERIC(10,2),
      ADD COLUMN IF NOT EXISTS yearly_inr NUMERIC(10,2),
      ADD COLUMN IF NOT EXISTS razorpay_plan_month TEXT,
      ADD COLUMN IF NOT EXISTS razorpay_plan_year TEXT,
      ADD COLUMN IF NOT EXISTS stripe_price_id_year TEXT;
    UPDATE plan_limits SET max_jobs = 100,  retention_days = 30,  yearly_usd = 190,  monthly_inr = 799,   yearly_inr = 7999   WHERE plan = 'developer';
    UPDATE plan_limits SET max_jobs = 1000, retention_days = 365, yearly_usd = 790,  monthly_inr = 3299,  yearly_inr = 32999  WHERE plan = 'team';
    UPDATE plan_limits SET max_jobs = NULL, retention_days = 730, yearly_usd = 2990, monthly_inr = 12499, yearly_inr = 124999 WHERE plan = 'business';
    UPDATE plan_limits SET yearly_usd = 0, monthly_inr = 0, yearly_inr = 0,
           features = (SELECT array_agg(DISTINCT f) FROM unnest(features || '{slack,webhook}'::text[]) f) WHERE plan = 'free';
    UPDATE plan_limits SET yearly_usd = 6000 WHERE plan = 'enterprise';   -- the published floor: "from $6,000 a year"

    ALTER TABLE subscriptions
      ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'stripe',
      ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'usd',
      ADD COLUMN IF NOT EXISTS billing_interval TEXT NOT NULL DEFAULT 'month',
      ADD COLUMN IF NOT EXISTS razorpay_customer_id TEXT,
      ADD COLUMN IF NOT EXISTS razorpay_subscription_id TEXT;
    CREATE INDEX IF NOT EXISTS subscriptions_razorpay_sub_idx ON subscriptions (razorpay_subscription_id) WHERE razorpay_subscription_id IS NOT NULL;

    CREATE TABLE IF NOT EXISTS razorpay_events (
      id TEXT PRIMARY KEY, type TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS razorpay_events;
    DROP INDEX IF EXISTS subscriptions_razorpay_sub_idx;
    ALTER TABLE subscriptions DROP COLUMN IF EXISTS razorpay_subscription_id, DROP COLUMN IF EXISTS razorpay_customer_id,
      DROP COLUMN IF EXISTS billing_interval, DROP COLUMN IF EXISTS currency, DROP COLUMN IF EXISTS provider;
    UPDATE plan_limits SET max_jobs = 50,   retention_days = 30  WHERE plan = 'developer';
    UPDATE plan_limits SET max_jobs = 500,  retention_days = 90  WHERE plan = 'team';
    UPDATE plan_limits SET max_jobs = 5000, retention_days = 365 WHERE plan = 'business';
    UPDATE plan_limits SET features = '{email}' WHERE plan = 'free';
    ALTER TABLE plan_limits DROP COLUMN IF EXISTS stripe_price_id_year, DROP COLUMN IF EXISTS razorpay_plan_year, DROP COLUMN IF EXISTS razorpay_plan_month,
      DROP COLUMN IF EXISTS yearly_inr, DROP COLUMN IF EXISTS monthly_inr, DROP COLUMN IF EXISTS yearly_usd;
    """)
