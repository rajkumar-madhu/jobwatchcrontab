"use client";
import Link from "next/link";
import { useState } from "react";
import { Building2, Check, Cloud, KeyRound, ShieldCheck, Workflow } from "lucide-react";
import { SiteNav, SiteFooter, ScheduleTape, Mark } from "@/components/marketing";
import { BeforeAfter, ClosingBand, CopilotSection, HeroProduct, Integrations, PlatformLayers, ProductTour, UseCases, WorksWith } from "./sections";
import { GROUPS, VENDORS } from "@/lib/compare";
import { BOOKING_URL, TALK } from "@/lib/site";

const INGEST = "https://ingest.jobwatch.wecrew.in";

// R74: the first-run path is one line in a crontab; the agent is the upgrade, not the entry fee.
const SIXTY = `# the job you would least like to find out about in a week
15 2 * * *  /opt/jobs/pg-backup.sh

# the same line, monitored: missed or failed → alert at 02:20
15 2 * * *  /opt/jobs/pg-backup.sh && curl -fsS -m 10 --retry 5 \\
            ${INGEST}/ping/<token>`;

const WAYS: { title: string; body: string; code: string }[] = [
  { title: "Start with one line", body: "Paste a crontab entry at sign-up: Argus takes the schedule from it and gives the line back with a ping appended. Nothing to install, nothing running as root.",
    code: `15 2 * * *  /opt/jobs/pg-backup.sh \\\n  && curl -fsS -m 10 --retry 5 \\\n     ${INGEST}/ping/<token>` },
  { title: "Add the agent where it earns its place", body: "When a failure needs more than \"it didn't run\": exit codes, stdout and stderr, duration, and what the host's disk, memory and load looked like during the run. Read-only on your crontabs; queues on disk when offline.",
    code: "curl -fsSL $JOBWATCH/install.sh \\\n  | sudo bash -s -- --server $JOBWATCH --token $BOOTSTRAP\n\n# then wrap a job\njobwatch-run -- /opt/jobs/backup.sh" },
  { title: "Or the chart, for a cluster", body: "One agent per cluster watches CronJobs, Jobs and pods. Schedules come from the CronJob spec, so there is nothing to copy by hand.",
    code: "helm install jobwatch-agent ./infra/helm/cronsentinel-agent \\\n  --set server=$JOBWATCH \\\n  --set bootstrapToken=$BOOTSTRAP" },
];


const ENTERPRISE: { icon: typeof KeyRound; title: string; items: [string, string][] }[] = [
  { icon: KeyRound, title: "Identity and access", items: [
    ["Single sign-on, enforced", "SAML 2.0 or OpenID Connect with Okta, Entra ID or Google Workspace, from verified domains. Require it for everyone but owners."],
    ["Multi-factor sign-in", "Require an authenticator app for password sign-in across the organization."],
    ["SCIM directory sync", "People are added and removed by your directory; groups map to six roles."]] },
  { icon: ShieldCheck, title: "Data protection", items: [
    ["Isolation in the database", "Postgres row-level security on every tenant table: a bug in an API handler cannot read another organization's rows."],
    ["Secrets that cannot leak from a backup", "Tokens and keys are stored as hashes; integration secrets are encrypted; job output is redacted."],
    ["An AI copilot that cannot act", "Read-only, on redacted and pseudonymised data, with a model you can host yourself."]] },
  { icon: Workflow, title: "Operations at scale", items: [
    ["Audit log to your SIEM", "Every change streamed to Splunk, Datadog or a signed webhook, in order."],
    ["On-call and escalation", "Rotations, overrides and escalation policies, or hand off to PagerDuty and Opsgenie."],
    ["Configuration as code", "A Terraform and OpenTofu provider, Kubernetes annotations and a full REST API."]] },
];

const DEPLOY: { icon: typeof Cloud; title: string; body: string; points: string[] }[] = [
  { icon: Cloud, title: "Argus Cloud", body: "We run it. Your organization is isolated in the database, and ingest runs on its own host with its own limits.",
    points: ["Start in minutes", "Upgrades and backups handled", "Single sign-on and SCIM on Business"] },
  { icon: Building2, title: "Self-hosted", body: "The whole platform in your Kubernetes cluster with the Helm chart. Every record stays in your network and your region.",
    points: ["Air-gapped friendly: no third-party requests", "Your database, your encryption keys", "Bring your own model for the copilot"] },
];

// R75: prices from the go-to-market research (docs/BILLING.md). usd/inr are monthly; yearly is two months free.
// INR prices are what Indian teams pay through Razorpay (UPI AutoPay, cards, net banking), GST extra.
type Plan = { name: string; usd: number | null; inr: number | null; inrYear?: number; floor?: string; feats: string[] };
const PLANS: Plan[] = [
  { name: "Free", usd: 0, inr: 0, feats: ["5 jobs", "7 days of history", "Email, Slack and webhook alerts", "Unlimited team members"] },
  { name: "Developer", usd: 19, inr: 799, inrYear: 7999, feats: ["100 jobs", "30 days of history", "Email, Slack and webhooks", "Unlimited team members"] },
  { name: "Team", usd: 79, inr: 3299, inrYear: 32999, feats: ["1,000 jobs", "12 months of history", "Teams, Discord, Telegram, PagerDuty, Opsgenie", "On-call schedules and escalation", "AI copilot, agent fleet view, status page"] },
  { name: "Business", usd: 299, inr: 12499, inrYear: 124999, feats: ["Unlimited jobs", "2 years of history", "Single sign-on, SCIM and MFA", "Audit log streaming", "Invoice billing", "Everything in Team"] },
  { name: "Enterprise", usd: null, inr: null, floor: "from $6,000 /year", feats: ["Self-hosted or private deployment", "Licence for the enterprise features", "Custom retention", "Security review support", "Support SLA"] },
];

const FAQ: [string, string][] = [
  ["Does the agent change my crontabs?", "No. Discovery is read-only. You decide per job whether to wrap it with jobwatch-run for exit codes and output."],
  ["What happens if a server loses its network?", "The agent keeps events on disk and sends them in order when it reconnects. The server de-duplicates, so nothing is counted twice."],
  ["Moving from Healthchecks.io or Cronitor?", "Import your checks with an API key. Ping URLs keep working: change hc-ping.com or cronitor.link to your Argus ingest host and the same paths, including start/fail signals, exit codes and Cronitor's state, series and metric parameters, keep working."],
  ["Can I use it without installing anything?", "Yes. Every job has a ping URL. One curl at the end of a script detects failures and missed runs."],
  ["What if Argus itself has an outage?", "Runs that fell inside our outage are marked unobserved instead of missed, and you are not alerted for them. The dashboard tells you it happened."],
  ["Where does my data live?", "In your own deployment if you self-host, or in an isolated tenant on ours. Environment variable values are never collected."],
  ["Does the AI change anything on my systems?", "No. It reads telemetry and suggests what to check. Every action stays with a person."],
  ["Do you support single sign-on, SCIM and MFA?", "Yes: SAML 2.0 and OpenID Connect from verified domains, with optional enforcement; SCIM provisioning with groups mapped to roles; and organization-wide multi-factor sign-in for password users."],
  ["Is Argus SOC 2 certified?", "Not yet. We answer security questionnaires and walk your team through the controls, and you can self-host the whole platform so no data leaves your network. See the security page."],
  ["How are Enterprise plans bought?", "Through sales: the deployment, payment method and contract terms are agreed with you."],
];

function PricingSection() {
  const [cur, setCur] = useState<"usd" | "inr">("usd");
  const [yearly, setYearly] = useState(true);
  const fmt = (p: Plan) => {
    if (p.usd == null) return p.floor ?? "Custom";
    const m = cur === "inr" ? p.inr! : p.usd;
    if (m === 0) return cur === "inr" ? "₹0" : "$0";
    const v = yearly ? (cur === "inr" ? p.inrYear ?? m * 10 : m * 10) : m;   // INR yearly figures are the flat plan prices in plan_limits
    return (cur === "inr" ? "₹" : "$") + v.toLocaleString(cur === "inr" ? "en-IN" : "en-US");
  };
  return (
    <section className="mx-auto max-w-[1200px] px-6 py-20" id="pricing">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h2 className="font-display text-3xl font-semibold">Pricing</h2>
          <p className="mt-3 text-mute">Priced by jobs, never by seats: every plan includes unlimited team members. Team is free for 14 days on every new workspace.</p></div>
        <div className="flex flex-wrap gap-2 text-sm" data-testid="pricing-toggles">
          <div role="radiogroup" aria-label="Currency" className="inline-flex rounded-md border border-line bg-panel">
            {(["usd", "inr"] as const).map((c) => <button key={c} type="button" role="radio" aria-checked={cur === c} onClick={() => setCur(c)} className={`px-3 py-1.5 ${cur === c ? "text-accent" : "text-mute"}`}>{c === "usd" ? "USD" : "INR"}</button>)}
          </div>
          <div role="radiogroup" aria-label="Billing interval" className="inline-flex rounded-md border border-line bg-panel">
            <button type="button" role="radio" aria-checked={!yearly} onClick={() => setYearly(false)} className={`px-3 py-1.5 ${!yearly ? "text-accent" : "text-mute"}`}>Monthly</button>
            <button type="button" role="radio" aria-checked={yearly} onClick={() => setYearly(true)} className={`px-3 py-1.5 ${yearly ? "text-accent" : "text-mute"}`}>Yearly <span className="text-xs text-mute">· 2 months free</span></button>
          </div>
        </div>
      </div>
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {PLANS.map((p, i) => (
          <div key={p.name} className={`card flex flex-col p-5 ${i === 2 ? "border-2 border-accent" : ""}`}>
            <div className="flex items-center justify-between"><h3 className="font-medium">{p.name}</h3>{i === 2 && <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-accent">Most teams</span>}</div>
            <div className={`mt-3 font-display font-semibold ${p.usd == null ? "text-xl leading-9" : "text-3xl"}`}>{fmt(p)}{p.usd != null && p.usd !== 0 && <span className="text-sm font-normal text-mute"> /{yearly ? "year" : "month"}</span>}</div>
            <ul className="mt-4 flex-1 space-y-2 text-sm text-mute">{p.feats.map((f) => <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-ok" aria-hidden />{f}</li>)}</ul>
            {i === 4 ? <a href={BOOKING_URL} className="btn mt-6 w-full">{TALK}</a> : <Link href="/signup" className={`btn mt-6 w-full ${i === 2 ? "btn-primary" : ""}`}>Start {p.name}</Link>}
          </div>))}
      </div>
      <p className="mt-4 text-xs text-mute">{cur === "inr" ? "Indian rupee prices exclude 18% GST and are paid through Razorpay (UPI AutoPay, cards, net banking); a GST invoice is issued for every charge." : "US dollar prices exclude taxes and are paid by card through Stripe."} Start free today; your jobs and history stay when you pick a plan. Enterprise is a self-hosted or private deployment with a licence for the enterprise features and a support SLA, from the stated annual figure.</p>
    </section>
  );
}

export default function Landing() {
  const summary = GROUPS.filter((g) => g.summary).flatMap((g) => g.rows);
  return (
    <div className="min-h-screen">
      <Link href="/signup" className="block border-b border-line bg-accent/[.08] px-6 py-2 text-center text-sm hover:bg-accent/[.12]">
        <span className="font-medium text-accent">New</span><span className="mx-2 text-mute">|</span>Moving from Healthchecks.io or Cronitor? Import in minutes and keep your ping URLs.
      </Link>
      <SiteNav />

      <section className="relative overflow-hidden border-b border-line">
        <div className="relative mx-auto max-w-[1200px] px-6 pb-20 pt-16 lg:pt-24">
          <div className="mx-auto max-w-[860px] text-center">
            <h1 className="font-display text-[42px] font-semibold leading-[1.03] sm:text-[64px]">Know the moment a scheduled job doesn&apos;t run.</h1>
            <p className="mx-auto mt-6 max-w-[640px] text-[17px] leading-relaxed text-mute sm:text-lg">
              Argus expects every run before it is due: cron, systemd timers, Kubernetes CronJobs, backups and pipelines.
              Silence turns into an alert on time, and failures arrive with the output that explains them.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link href="/signup" className="btn btn-primary px-6 py-3 text-[15px]">Start monitoring free</Link>
              <a href={BOOKING_URL} className="btn px-6 py-3 text-[15px]" {...(BOOKING_URL.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>{TALK}</a>
            </div>
            <p className="mt-4 text-sm text-mute">5 jobs free, no card, nothing to install. Open source (AGPL), self-host it with Helm. <Link href="/product" className="underline hover:text-ink">Take the product tour</Link></p>
            <pre className="mx-auto mt-8 max-w-[720px] overflow-x-auto rounded-lg border border-line bg-panel/70 p-4 text-left font-mono text-[12.5px] leading-relaxed text-ink/90" aria-label="One line in a crontab" data-testid="sixty-seconds">{SIXTY}</pre>
            <p className="mt-2 text-xs text-mute">Sixty seconds, no agent. <code className="font-mono">&amp;&amp;</code> means a failing job never pings; a job that never ran never pings; both alert at the deadline.</p>
          </div>
          <div className="relative mx-auto mt-14 max-w-[1100px]">
            <HeroProduct />
            <div className="mt-6 lg:absolute lg:-bottom-14 lg:-right-10 lg:mt-0 lg:w-[728px]"><ScheduleTape callout={false} /></div>
          </div>
        </div>
      </section>

      <WorksWith />
      <BeforeAfter />
      <PlatformLayers />
      <ProductTour />
      <CopilotSection />
      <UseCases />
      <Integrations />

      <section className="mx-auto max-w-[1200px] px-6 py-20" id="start">
        <h2 className="font-display text-3xl font-semibold">Start with one line. Add the agent when you want more.</h2>
        <p className="mt-3 max-w-[640px] text-mute">Most teams end up with all three: a ping on anything that can run curl, the agent on the servers whose failures need explaining, and the chart in clusters.</p>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          {WAYS.map((w) => (
            <div key={w.title} className="card flex min-w-0 flex-col p-5">
              <h3 className="font-display text-lg font-medium">{w.title}</h3>
              <p className="mt-2 text-sm text-mute">{w.body}</p>
              <pre className="mt-5 flex-1 overflow-x-auto rounded-md border border-line bg-bg p-3 font-mono text-[12px] leading-relaxed text-ink/90">{w.code}</pre>
            </div>))}
        </div>
      </section>


      <section className="border-y border-line bg-panel/40" id="enterprise">
        <div className="mx-auto max-w-[1200px] px-6 py-20">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <p className="text-sm font-medium text-accent">Enterprise</p>
              <h2 className="mt-2 font-display text-3xl font-semibold sm:text-4xl">Built to pass your security review</h2>
              <p className="mt-3 max-w-[640px] text-mute">Monitoring sees your schedules, hostnames and job output. These controls keep it from becoming the weak point, on our cloud or yours.</p>
              <ul className="mt-5 flex max-w-[760px] flex-wrap gap-x-5 gap-y-2 text-xs text-mute" aria-label="Enterprise controls">
                {["SAML and OIDC single sign-on", "SCIM", "Multi-factor sign-in", "Audit log streaming", "Row-level tenant isolation", "Self-hosted with Helm", "Source available to read, AGPL"].map((t) => (
                  <li key={t} className="flex items-center gap-1.5"><Check size={13} className="text-ok" aria-hidden />{t}</li>))}
              </ul>
            </div>
            <div className="flex flex-wrap gap-2"><a href={BOOKING_URL} className="btn btn-primary">{TALK}</a><Link href="/security" className="btn">Security overview</Link></div>
          </div>
          <div className="mt-12 grid gap-8 lg:grid-cols-3">
            {ENTERPRISE.map(({ icon: Icon, title, items }) => (
              <div key={title} className="min-w-0">
                <div className="flex items-center gap-2.5"><span className="grid h-8 w-8 place-items-center rounded-md bg-accent/15 text-accent"><Icon size={16} aria-hidden /></span><h3 className="font-display text-lg font-semibold">{title}</h3></div>
                <dl className="mt-5 space-y-5">{items.map(([t, d]) => (
                  <div key={t} className="border-t border-line pt-4"><dt className="font-medium">{t}</dt><dd className="mt-1.5 text-sm text-mute">{d}</dd></div>))}</dl>
              </div>))}
          </div>
          <div className="mt-14 grid gap-4 md:grid-cols-2">
            {DEPLOY.map(({ icon: Icon, title, body, points }) => (
              <div key={title} className="card flex min-w-0 flex-col p-6">
                <div className="flex items-center gap-2.5"><Icon size={18} className="text-accent" aria-hidden /><h3 className="font-display text-lg font-semibold">{title}</h3></div>
                <p className="mt-2 text-sm text-mute">{body}</p>
                <ul className="mt-4 space-y-2 text-sm">{points.map((pt) => <li key={pt} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-ok" aria-hidden />{pt}</li>)}</ul>
              </div>))}
          </div>
        </div>
      </section>

      <section className="border-y border-line bg-panel/40" id="compare">
        <div className="mx-auto max-w-[1200px] px-6 py-20">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="font-display text-3xl font-semibold">How it compares</h2>
              <p className="mt-3 max-w-[640px] text-mute">From each vendor&apos;s public pricing and documentation, October 2026. The full table also lists where Argus is behind.</p>
            </div>
            <Link href="/compare" className="btn">See the full comparison</Link>
          </div>
          <div className="card mt-8 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead><tr className="border-b border-line text-left text-xs text-mute">
                <th className="px-4 py-3 font-normal">Capability</th>
                {VENDORS.map((v) => <th key={v.key} className={`px-3 py-3 text-center font-normal ${v.key === "jw" ? "text-accent" : ""}`}>{v.name}</th>)}
              </tr></thead>
              <tbody>{summary.map((r) => (
                <tr key={r.label} className="border-b border-line last:border-0">
                  <td className="px-4 py-3">{r.label}</td>
                  {VENDORS.map((v) => <td key={v.key} className={`px-3 py-3 ${v.key === "jw" ? "bg-accent/[.05]" : ""}`}><div className="flex justify-center"><Mark c={r.cells[v.key]} /></div></td>)}
                </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <PricingSection />

      <section className="border-t border-line bg-panel/40">
        <div className="mx-auto grid max-w-[1200px] gap-12 px-6 py-20 lg:grid-cols-[1fr_2fr]">
          <h2 className="font-display text-3xl font-semibold">Questions teams ask before installing</h2>
          <div className="divide-y divide-line">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">{q}<span className="text-mute transition group-open:rotate-45" aria-hidden>+</span></summary>
                <p className="mt-2 max-w-[640px] text-sm text-mute">{a}</p>
              </details>))}
          </div>
        </div>
      </section>

      <ClosingBand />

      <SiteFooter />
    </div>
  );
}
