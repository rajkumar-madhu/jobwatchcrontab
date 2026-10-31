import Link from "next/link";
import { SiteFooter, SiteNav } from "@/components/marketing";

export const metadata = { title: "Security · WeCrew Argus", description: "How Argus protects your organization: identity, isolation, secrets, auditing and deployment." };

// Set at build time to publish a security contact; otherwise reports go through the contact form.
const SECURITY_EMAIL = process.env.NEXT_PUBLIC_SECURITY_EMAIL || "";

type Item = [string, string];
const SECTIONS: { id: string; title: string; lead: string; items: Item[] }[] = [
  { id: "identity", title: "Identity and access", lead: "Your identity provider decides who gets in, and every action is checked against a role.", items: [
    ["Single sign-on", "SAML 2.0 and OpenID Connect with Okta, Microsoft Entra ID, Google Workspace, ADFS or any standard provider. People join only from email domains you have verified through DNS."],
    ["Enforced sign-in policy", "Require single sign-on for everyone except owners, who keep a password so a broken identity provider cannot lock the organization out."],
    ["Multi-factor sign-in", "Members who use a password can be required to add an authenticator app. Google and GitHub sign-in are then refused for that organization."],
    ["Directory sync", "SCIM 2.0 provisioning from Okta and Entra ID. Deactivated people lose access on their next request; directory groups map to roles."],
    ["Six roles", "Viewer, developer, SRE, DevOps, admin and owner, enforced on every API call. API keys carry a role too and can be revoked at any time."],
    ["Invitations", "Invite links work once, expire after seven days, are stored only as a hash and only join the email address they were sent to."],
  ]},
  { id: "data", title: "Data protection", lead: "Isolation is enforced by the database, and secrets are never stored in a form that can be read back.", items: [
    ["Tenant isolation", "Every tenant table uses PostgreSQL row-level security bound to your organization. The database refuses to return another organization's rows even if application code asks for them."],
    ["Hashed credentials", "Ping tokens, API keys, agent keys and invitation tokens are stored only as hashes and shown once."],
    ["Encrypted integration secrets", "Alert-channel credentials, identity-provider secrets and integration keys are encrypted at rest and never returned by the API."],
    ["Redaction", "Passwords, tokens, keys, connection strings and private keys are removed from job output before it is stored, alerted on or shown to the AI copilot."],
    ["Data export and deletion", "Owners can export the organization's data and delete it completely."],
  ]},
  { id: "application", title: "Application security", lead: "Controls that keep the service itself from becoming a path into your network.", items: [
    ["Sessions", "httpOnly, Secure, SameSite cookies; a CSRF token on every state-changing browser request; signed sessions."],
    ["Outbound requests", "Webhooks, SMTP servers, SIEM endpoints and import sources are resolved and checked before connecting, so Argus cannot be pointed at internal addresses. TLS certificates are verified."],
    ["Rate limits", "Per-address limits on the app and API, per-job limits on pings, and limits on guessing tokens."],
    ["Agents", "The installer verifies release checksums. Agents report environment variable names, never values. The Kubernetes agent has read-only cluster access."],
    ["AI copilot", "Read-only. It sees redacted, pseudonymised telemetry and suggests commands as text; nothing is executed. It can use a model you host."],
  ]},
  { id: "audit", title: "Auditing", lead: "A record of who changed what, delivered to the systems your security team already watches.", items: [
    ["Audit log", "Sign-ins, role changes, invitations, configuration changes and deletions, with actor, time and source address."],
    ["Streaming to your SIEM", "Deliver every audit event as it happens to Splunk (HTTP Event Collector), Datadog Logs or a signed webhook, in order and at least once."],
  ]},
  { id: "deployment", title: "Deployment and residency", lead: "Run Argus on our cloud, or entirely inside your own network.", items: [
    ["Self-hosted", "The whole platform runs in your Kubernetes cluster with the Helm chart. Fonts and assets are bundled; it makes no third-party requests unless you connect an integration."],
    ["Your region, your keys", "Self-hosted, your data stays in the region and cluster you choose, encrypted with keys you hold."],
    ["Separated hosts", "The app and the ingest endpoint run on separate hosts with separate limits, so a flood of pings cannot affect the dashboard or sign-in."],
  ]},
];

export default function SecurityPage() {
  return (
    <div className="min-h-screen">
      <SiteNav />
      <header className="border-b border-line bg-panel/50">
        <div className="mx-auto max-w-[1200px] px-6 py-14">
          <p className="text-sm text-mute">Security</p>
          <h1 className="mt-2 max-w-[760px] font-display text-[40px] font-semibold leading-tight text-balance sm:text-5xl">Built to pass your security review</h1>
          <p className="mt-4 max-w-[680px] text-lg text-mute">Argus sees your schedules, hostnames and job output. This page describes the controls that protect them, as they work today.</p>
          <div className="mt-6 flex flex-wrap gap-3"><Link href="/contact?topic=security-review" className="btn btn-primary">Request a security review</Link><Link href="/docs/security" className="btn">Read the technical overview</Link></div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1200px] gap-12 px-6 py-14 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="hidden lg:block" aria-label="On this page"><ul className="sticky top-24 space-y-2 text-sm">
          {SECTIONS.map((s) => <li key={s.id}><a href={`#${s.id}`} className="text-mute hover:text-ink">{s.title}</a></li>)}
          <li><a href="#compliance" className="text-mute hover:text-ink">Compliance</a></li>
          <li><a href="#disclosure" className="text-mute hover:text-ink">Reporting a vulnerability</a></li></ul></nav>
        <div className="min-w-0 space-y-16">
          {SECTIONS.map((s) => (
            <section key={s.id} id={s.id} className="scroll-mt-24" aria-labelledby={`${s.id}-h`}>
              <h2 id={`${s.id}-h`} className="font-display text-2xl font-semibold">{s.title}</h2>
              <p className="mt-2 max-w-[680px] text-mute">{s.lead}</p>
              <dl className="mt-6 grid gap-x-10 gap-y-6 md:grid-cols-2">{s.items.map(([t, d]) => (
                <div key={t} className="border-t border-line pt-4"><dt className="font-medium">{t}</dt><dd className="mt-1.5 text-sm text-mute">{d}</dd></div>))}</dl>
            </section>))}
          <section id="compliance" className="scroll-mt-24" aria-labelledby="compliance-h">
            <h2 id="compliance-h" className="font-display text-2xl font-semibold">Compliance</h2>
            <div className="mt-4 max-w-[720px] space-y-3 text-mute">
              <p>Argus has not yet completed a SOC 2 or ISO 27001 audit. We will say so here when one is done, not before.</p>
              <p>For a security review, we will answer your questionnaire (SIG Lite, CAIQ or your own) and walk your team through the controls on this page. Teams that cannot send data to a vendor can self-host the whole platform, which keeps every record inside their own environment.</p>
            </div>
          </section>
          <section id="disclosure" className="scroll-mt-24 rounded-lg border border-line bg-panel p-6" aria-labelledby="disclosure-h">
            <h2 id="disclosure-h" className="font-display text-xl font-semibold">Reporting a vulnerability</h2>
            <p className="mt-2 max-w-[680px] text-sm text-mute">If you find a security issue, tell us privately before disclosing it. We will reply, and keep you informed until it is fixed.</p>
            <p className="mt-3 text-sm">{SECURITY_EMAIL ? <>Email <span className="select-all font-mono">{SECURITY_EMAIL}</span></> : <>Use the <Link href="/contact?topic=vulnerability" className="text-accent underline">contact form</Link> and choose “Report a vulnerability”.</>}</p>
          </section>
        </div>
      </div>
      <SiteFooter />
    </div>
  );
}
