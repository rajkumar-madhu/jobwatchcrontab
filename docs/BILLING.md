# Billing (R75)

Two processors, one subscription per organisation:

| | Currency | Processor | Pays with | Where it is configured |
|---|---|---|---|---|
| Global | USD | Stripe Checkout + Billing Portal | card | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `plan_limits.stripe_price_id` / `stripe_price_id_year` |
| India | INR | Razorpay Subscriptions (hosted page) | UPI AutoPay, cards, net banking | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `plan_limits.razorpay_plan_month` / `razorpay_plan_year` |

`POST /api/v1/billing/checkout?plan=team&currency=inr&interval=year` returns the URL to send the browser
to. `subscriptions.provider` records who bills the org; switching currency requires cancelling the
other subscription first (409 otherwise).

## Prices

Set by migration 0030 from the October 2026 go-to-market research (`reports/Argus B2B go to market.md`
in the founder's files). Priced by jobs, never by seats.

| Plan | Jobs | History | USD / month | USD / year | INR / month | INR / year |
|---|---|---|---|---|---|---|
| Free | 5 | 7 days | 0 | 0 | 0 | 0 |
| Developer | 100 | 30 days | 19 | 190 | 799 | 7,999 |
| Team | 1,000 | 12 months | 79 | 790 | 3,299 | 32,999 |
| Business | unlimited | 2 years | 299 | 2,990 | 12,499 | 1,24,999 |
| Enterprise | unlimited | custom | — | from 6,000 (published floor) | — | — |

Why these numbers: the market anchor for the entry tier is $19–20 for 100 jobs ($0.19–0.20 per job:
Healthchecks.io, Dead Man's Snitch), so Developer moved from 50 to 100 jobs at the same price. Team
matches Healthchecks Business Plus ($80 / 1,000) and adds on-call, 12-month history and the agent fleet.
Business is unlimited plus the enterprise features. The Enterprise floor is published because an
open-ended "contact sales" from an unknown vendor converts worse than a number. INR is 40–60 % of US
sticker, flat, yearly-first (UPI AutoPay avoids the 3-D Secure failures of international cards); these
are **starting points, not tested prices**. Free gained Slack and webhooks so a free user sees a real
alert fire; the 5-job cap is the conversion lever (Healthchecks' data: people upgrade on the job limit,
almost never on seats).

Changing a price: `UPDATE plan_limits SET monthly_usd=…, yearly_usd=…, monthly_inr=…, yearly_inr=…`, then
create the matching Price / Plan in the processor and store its id in the same row. The pricing page
(`apps/web/app/(public)/welcome/page.tsx`, `PLANS`) is static copy and must be changed by hand to match.

## Razorpay setup

1. Razorpay dashboard → Subscriptions → Plans: one plan per (tier × interval), amount in paise, period
   `monthly` / `yearly`. Put the ids in `plan_limits.razorpay_plan_month` / `razorpay_plan_year`.
2. Settings → API keys: live key id and secret → `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`.
3. Settings → Webhooks: URL `https://<api>/api/v1/billing/razorpay/webhook`, a secret →
   `RAZORPAY_WEBHOOK_SECRET`, events `subscription.activated`, `subscription.charged`,
   `subscription.pending`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`,
   `subscription.resumed`. The handler verifies `X-Razorpay-Signature` (HMAC-SHA256 over the raw body)
   and de-duplicates on `X-Razorpay-Event-Id` (`razorpay_events`).
4. GST: Razorpay issues the payment receipt; the GST tax invoice to the customer is still the merchant's
   to raise (Razorpay Invoices or your accountant's tool). Domestic INR sales carry 18 % GST; USD sales to
   foreign customers are zero-rated exports of services under an annual LUT (not legal or tax advice —
   confirm with your CA; CBIC's export-of-services conditions are the primary text).

State machine: `activated` / `charged` / `resumed` → plan granted, status `active`; `pending` / `halted` →
`past_due`, plan kept while Razorpay retries the mandate; `cancelled` / `completed` / `expired` → `free`.
Events for subscriptions Argus did not create are acknowledged and ignored.

## Stripe setup

Unchanged from R7 apart from the yearly Price (`stripe_price_id_year`). Note for an Indian entity:
Stripe India is invite-only and for registered businesses; it settles in INR and requires a purpose code
and the customer's name and address on every export charge. If that is not workable, a merchant of record
(Paddle, Lemon Squeezy, Dodo) can front the USD side at roughly 5 % + FX; the API's `provider` column is
where a third processor would go.
