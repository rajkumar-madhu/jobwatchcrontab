"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, mutate } from "@/lib/api";
import { ago } from "@/lib/format";
import { Page, Skeleton, ErrorBox } from "@/components/ui";

// R35: plan_limits.features keys → what the customer reads. Keys not listed render raw, which is a
// signal to add a label (or to ask whether the feature exists at all — see migration 0015).
const FEATURE_LABEL: Record<string, string> = { slack: "Slack", webhook: "Webhooks", teams: "Microsoft Teams", discord: "Discord",
  telegram: "Telegram", ai: "AI copilot", kubernetes: "Kubernetes agent", pagerduty: "PagerDuty", opsgenie: "Opsgenie", sso: "Single sign-on", audit_stream: "Audit log streaming",
  datadog: "Datadog", metrics_export: "Metrics export", oncall: "On-call schedules", escalation: "Escalation policies" };

export default function BillingPage() {
  const q = useQuery({ queryKey: ["billing"], queryFn: () => api<any>("/api/v1/billing") });
  // R75: USD through Stripe, INR through Razorpay (UPI AutoPay, cards, net banking); monthly or yearly
  const [currency, setCurrency] = useState<"usd" | "inr">(() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone === "Asia/Calcutta" || Intl.DateTimeFormat().resolvedOptions().timeZone === "Asia/Kolkata" ? "inr" : "usd"; } catch { return "usd"; } });
  const [interval, setInterval_] = useState<"month" | "year">("year");
  const checkout = useMutation({ mutationFn: (plan: string) => mutate("/api/v1/billing/checkout", "post", { query: { plan, currency, interval } as any }) as Promise<{ url: string }>, onSuccess: (d) => (location.href = d.url) });
  const portal = useMutation({ mutationFn: () => mutate("/api/v1/billing/portal", "post", {}) as Promise<{ url: string }>, onSuccess: (d) => (location.href = d.url) });
  if (q.error) return <Page title="Billing"><ErrorBox error={q.error} /></Page>;
  if (!q.data) return <Page title="Billing"><Skeleton /></Page>;
  const { subscription: s, plans, usage, limits, configured, configured_inr } = q.data;
  const ready = currency === "inr" ? configured_inr : configured;
  const price = (p: any) => {
    const v = currency === "inr" ? (interval === "year" ? p.yearly_inr : p.monthly_inr) : (interval === "year" ? p.yearly_usd : p.monthly_usd);
    if (p.plan === "enterprise") return p.yearly_usd ? `from $${Number(p.yearly_usd).toLocaleString("en-US")}/yr` : "Custom";
    if (v == null) return "Custom";
    if (Number(v) === 0) return currency === "inr" ? "₹0" : "$0";
    return currency === "inr" ? `₹${Number(v).toLocaleString("en-IN")}/${interval === "year" ? "yr" : "mo"}` : `$${Number(v).toLocaleString("en-US")}/${interval === "year" ? "yr" : "mo"}`;
  };
  const pct = limits?.max_jobs ? Math.min(100, Math.round(100 * usage.jobs / limits.max_jobs)) : 0;
  return (
    <Page title="Billing">
      {(checkout.error || portal.error) && <div className="mb-3"><ErrorBox error={checkout.error || portal.error} /></div>}
      <div className="mb-8 grid gap-6 sm:grid-cols-2">
        <div className="card bg-panel p-4 text-sm"><h2 className="font-medium">Current plan</h2>
          <p className="mt-1 text-2xl font-semibold capitalize">{s?.effective_plan ?? "free"}</p>
          <p className="text-mute">{s?.status}{s?.trial_ends_at && new Date(s.trial_ends_at) > new Date() && <> · trial ends {ago(s.trial_ends_at)}</>}{s?.current_period_end && <> · renews {ago(s.current_period_end)}</>}{s?.cancel_at_period_end && <span className="text-warn"> · cancels at period end</span>}</p>
          {s?.has_customer && <button className="btn mt-3" onClick={() => portal.mutate()}>Manage payment & invoices</button>}</div>
        <div className="card bg-panel p-4 text-sm"><h2 className="font-medium">Usage this month</h2>
          <p className="mt-1">{usage.jobs} of {limits?.max_jobs ?? "∞"} jobs</p><div className="mt-1 h-1.5 rounded bg-line"><div className={`h-full rounded ${pct >= 90 ? "bg-bad" : "bg-accent"}`} style={{ width: `${pct}%` }} /></div>
          <p className="mt-2 text-mute">{usage.executions_this_month} executions · {(usage.log_bytes / 1e6).toFixed(1)} MB logs · {limits?.retention_days ?? "custom"}-day retention</p></div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm" data-testid="billing-toggles">
        <div role="radiogroup" aria-label="Currency" className="inline-flex rounded-md border border-line">
          {(["usd", "inr"] as const).map((c) => <button key={c} type="button" role="radio" aria-checked={currency === c} onClick={() => setCurrency(c)} className={`px-3 py-1 ${currency === c ? "bg-accent/10 text-accent" : "text-mute"}`}>{c === "usd" ? "USD · card" : "INR · UPI, card"}</button>)}
        </div>
        <div role="radiogroup" aria-label="Billing interval" className="inline-flex rounded-md border border-line">
          {(["month", "year"] as const).map((i) => <button key={i} type="button" role="radio" aria-checked={interval === i} onClick={() => setInterval_(i)} className={`px-3 py-1 ${interval === i ? "bg-accent/10 text-accent" : "text-mute"}`}>{i === "month" ? "Monthly" : "Yearly · 2 months free"}</button>)}
        </div>
        {currency === "inr" && <span className="text-xs text-mute">Prices exclude 18% GST. Paid through Razorpay; yearly plans avoid card re-authentication.</span>}
        {s?.provider && s.effective_plan !== "free" && <span className="text-xs text-mute">Billed through {s.provider === "razorpay" ? "Razorpay (INR)" : "Stripe (USD)"}.</span>}
      </div>
      {!ready && <p className="mb-4 rounded-md border border-warn/40 bg-warn/5 px-3 py-2 text-sm">{currency === "inr" ? <>INR billing is not configured on this deployment yet. Set <code className="font-mono">RAZORPAY_KEY_ID</code>, <code className="font-mono">RAZORPAY_KEY_SECRET</code> and plan ids in <code className="font-mono">plan_limits</code>, or pay in USD.</> : <>Stripe is not configured on this deployment — plan changes are disabled. Set <code className="font-mono">STRIPE_SECRET_KEY</code> and price IDs in <code className="font-mono">plan_limits</code>.</>}</p>}
      <div className="grid items-stretch gap-3 md:grid-cols-5">{plans.map((p: any) => { const cur = p.plan === (s?.effective_plan ?? "free"); return (
        <div key={p.plan} className={`flex flex-col rounded-lg border p-4 text-sm ${cur ? "border-accent" : "border-line"}`}><h3 className="font-medium capitalize">{p.plan}</h3><p className="text-xl font-semibold">{price(p)}</p>
          <ul className="mt-2 space-y-0.5 text-mute"><li>{p.max_jobs ?? "Unlimited"} jobs</li><li>{p.retention_days ?? "Custom"}{p.retention_days ? "-day" : ""} history</li>{p.features.filter((f: string) => !["email", "all"].includes(f)).map((f: string) => <li key={f}>{FEATURE_LABEL[f] ?? f}</li>)}</ul>
          {cur ? <span className="mt-auto block pt-3 text-xs text-accent">Current</span> : p.plan === "enterprise" ? <a className="btn mt-auto w-full justify-center" href="/contact?topic=enterprise">Talk to a human</a> : <button className="btn btn-primary mt-auto w-full justify-center" disabled={!ready || checkout.isPending} onClick={() => checkout.mutate(p.plan)}>{plans.findIndex((x: any) => x.plan === p.plan) > plans.findIndex((x: any) => x.plan === (s?.effective_plan ?? "free")) ? "Upgrade" : "Downgrade"}</button>}</div>); })}</div>
    </Page>
  );
}
