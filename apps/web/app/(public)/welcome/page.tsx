"use client";
import Link from "next/link";
import { Building2, Check, Cloud, KeyRound, ShieldCheck, Workflow } from "lucide-react";
import { SiteNav, SiteFooter, ScheduleTape, Mark } from "@/components/marketing";
import { BeforeAfter, ClosingBand, CopilotSection, HeroProduct, Integrations, PlatformLayers, ProductTour, UseCases, WorksWith } from "./sections";
import { GROUPS, VENDORS } from "@/lib/compare";

const INGEST = "https://ingest.jobwatch.wecrew.in";

const WAYS: { title: string; body: string; code: string }[] = [
  { title: "Install the agent on a server", body: "It reads crontabs and systemd timers, read-only, and lists every job it finds. Wrap the ones you care about to get exit codes and output.",
    code: "curl -fsSL $JOBWATCH/install.sh \\\n  | sudo bash -s -- --server $JOBWATCH --token $BOOTSTRAP\n\n# then, in a crontab line\njobwatch-run -- /opt/jobs/backup.sh" },
  { title: "Add the chart to a cluster", body: "One agent per cluster watches CronJobs, Jobs and pods. Schedules come from the CronJob spec, so there is nothing to copy by hand.",
    code: "helm install jobwatch-agent ./infra/helm/cronsentinel-agent \\\n  --set server=$JOBWATCH \\\n  --set bootstrapToken=$BOOTSTRAP" },
  { title: "Or call one URL", body: "Anything that can make an HTTP request can report: CI pipelines, database jobs, Lambda functions, scripts on a laptop.",
    code: `# last line of the script\ncurl -fsS -m 10 --retry 5 \\\n  ${INGEST}/ping/<token>` },
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
  { icon: Cloud, title: "JobWatch Cloud", body: "We run it. Your organization is isolated in the database, and ingest runs on its own host with its own limits.",
    points: ["Start in minutes", "Upgrades and backups handled", "Single sign-on and SCIM on Business"] },
  { icon: Building2, title: "Self-hosted", body: "The whole platform in your Kubernetes cluster with the Helm chart. Every record stays in your network and your region.",
    points: ["Air-gapped friendly: no third-party requests", "Your database, your encryption keys", "Bring your own model for the copilot"] },
];

const PLANS: [string, string, string[]][] = [
  ["Free", "$0", ["5 jobs", "7 days of history", "Email alerts"]],
  ["Developer", "$19", ["50 jobs", "30 days of history", "Slack and webhooks"]],
  ["Team", "$79", ["500 jobs", "90 days of history", "Teams, Discord and Telegram", "PagerDuty and Opsgenie", "AI copilot"]],
  ["Business", "$299", ["5,000 jobs", "1 year of history", "Single sign-on and SCIM", "Everything in Team"]],
  ["Enterprise", "Custom", ["Unlimited jobs", "Self-hosted or private deployment", "Custom retention", "Security review support", "Priority support"]],
];

const FAQ: [string, string][] = [
  ["Does the agent change my crontabs?", "No. Discovery is read-only. You decide per job whether to wrap it with jobwatch-run for exit codes and output."],
  ["What happens if a server loses its network?", "The agent keeps events on disk and sends them in order when it reconnects. The server de-duplicates, so nothing is counted twice."],
  ["Moving from Healthchecks.io or Cronitor?", "Import your checks with an API key. Ping URLs keep working: change hc-ping.com or cronitor.link to your JobWatch ingest host and the same paths, including start/fail signals, exit codes and Cronitor's state, series and metric parameters, keep working."],
  ["Can I use it without installing anything?", "Yes. Every job has a ping URL. One curl at the end of a script detects failures and missed runs."],
  ["What if JobWatch itself has an outage?", "Runs that fell inside our outage are marked unobserved instead of missed, and you are not alerted for them. The dashboard tells you it happened."],
  ["Where does my data live?", "In your own deployment if you self-host, or in an isolated tenant on ours. Environment variable values are never collected."],
  ["Does the AI change anything on my systems?", "No. It reads telemetry and suggests what to check. Every action stays with a person."],
  ["Do you support single sign-on, SCIM and MFA?", "Yes: SAML 2.0 and OpenID Connect from verified domains, with optional enforcement; SCIM provisioning with groups mapped to roles; and organization-wide multi-factor sign-in for password users."],
  ["Is JobWatch SOC 2 certified?", "Not yet. We answer security questionnaires and walk your team through the controls, and you can self-host the whole platform so no data leaves your network. See the security page."],
  ["How are Enterprise plans bought?", "Through sales: the deployment, payment method and contract terms are agreed with you."],
];

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
              JobWatch expects every run before it is due: cron, systemd timers, Kubernetes CronJobs, backups and pipelines.
              Silence turns into an alert on time, and failures arrive with the output that explains them.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link href="/signup" className="btn btn-primary px-6 py-3 text-[15px]">Start monitoring free</Link>
              <Link href="/contact" className="btn px-6 py-3 text-[15px]">Talk to sales</Link>
            </div>
            <p className="mt-4 text-sm text-mute">5 jobs free, no card. Or self-host the whole platform with Helm. <Link href="/product" className="underline hover:text-ink">Take the product tour</Link></p>
            <ul className="mx-auto mt-8 flex max-w-[760px] flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-mute" aria-label="Enterprise controls">
              {["SAML and OIDC single sign-on", "SCIM", "Multi-factor sign-in", "Audit log streaming", "Row-level tenant isolation", "Self-hosted with Helm"].map((t) => (
                <li key={t} className="flex items-center gap-1.5"><Check size={13} className="text-ok" aria-hidden />{t}</li>))}
            </ul>
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
        <h2 className="font-display text-3xl font-semibold">Three ways to connect, mixed freely</h2>
        <p className="mt-3 max-w-[640px] text-mute">Most teams use all three: the agent on servers, the chart in clusters, and a ping URL for everything else.</p>
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
            </div>
            <div className="flex flex-wrap gap-2"><Link href="/contact" className="btn btn-primary">Talk to sales</Link><Link href="/security" className="btn">Security overview</Link></div>
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
              <p className="mt-3 max-w-[640px] text-mute">From each vendor&apos;s public pricing and documentation, October 2026. The full table also lists where JobWatch is behind.</p>
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

      <section className="mx-auto max-w-[1200px] px-6 py-20" id="pricing">
        <h2 className="font-display text-3xl font-semibold">Pricing</h2>
        <p className="mt-3 text-mute">Every plan includes unlimited team members. Team is free for 14 days on every new workspace.</p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {PLANS.map(([name, price, feats], i) => (
            <div key={name} className={`card flex flex-col p-5 ${i === 2 ? "border-2 border-accent" : ""}`}>
              <div className="flex items-center justify-between"><h3 className="font-medium">{name}</h3>{i === 2 && <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] text-accent">Most teams</span>}</div>
              <div className="mt-3 font-display text-3xl font-semibold">{price}{price.startsWith("$") && price !== "$0" && <span className="text-sm font-normal text-mute"> /month</span>}</div>
              <ul className="mt-4 flex-1 space-y-2 text-sm text-mute">{feats.map((f) => <li key={f} className="flex gap-2"><Check size={14} className="mt-0.5 shrink-0 text-ok" aria-hidden />{f}</li>)}</ul>
              <Link href={i === 4 ? "/contact" : "/signup"} className={`btn mt-6 w-full ${i === 2 ? "btn-primary" : ""}`}>{i === 4 ? "Talk to sales" : `Start ${name}`}</Link>
            </div>))}
        </div>
        <p className="mt-4 text-xs text-mute">Prices in US dollars, excluding taxes. Card billing opens soon: start free today and choose a plan when it does — your jobs and history stay.</p>
      </section>

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
