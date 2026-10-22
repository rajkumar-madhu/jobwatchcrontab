import Link from "next/link";
import { ArrowRight, Download, KeyRound } from "lucide-react";
import { APP_BASE, INGEST_BASE, apiReference } from "@/lib/api-reference";
import { Snippet } from "@/components/api-code";

export const dynamic = "force-static";
export const metadata = { title: "API reference · JobWatch docs", description: "The JobWatch REST API: authentication, roles, errors, pagination, rate limits and every endpoint." };

const ROLES: [string, string][] = [
  ["Viewer", "Read jobs, runs, incidents, analytics and configuration."],
  ["Developer", "Create and change jobs, acknowledge and resolve incidents, ask the copilot, manage dependencies."],
  ["SRE", "Everything a developer can do."],
  ["DevOps", "Alert channels, rules, maintenance windows, on-call, agents, integrations; delete jobs and rotate ping URLs."],
  ["Admin", "Members and invitations, API keys, single sign-on, imports, status pages, metric exports, data export."],
  ["Owner", "Sign-in policy, SSO enforcement, SCIM tokens and group roles, audit streams, deleting the organization."],
];

const ERRORS: [string, string][] = [
  ["400", "The request is not valid for this resource, for example an unknown channel type."],
  ["401", "No credentials, or the API key, token or session is invalid or expired."],
  ["403", "Authenticated, but the role is too low, or the organization requires single sign-on."],
  ["404", "No such resource in this organization. Resources of other organizations are always 404."],
  ["409", "The request conflicts with the current state, for example a duplicate name."],
  ["422", "A field is missing or has the wrong type or format. `detail` lists each problem with its location."],
  ["429", "Too many requests. Wait for the number of seconds in `Retry-After`."],
  ["5xx", "Something failed on our side. Safe to retry GET, PUT and DELETE with backoff."],
];

const LIMITS: [string, string, string][] = [
  ["REST API", "1,200 requests per minute", "Per API key, or per user for bearer tokens and sessions."],
  ["AI copilot", "20 questions per minute", "Per user."],
  ["Pings", "600 per minute", "Per job, on the ingest host. Extra pings get 429 and are not recorded."],
  ["Per address (self-hosted defaults)", "50 req/s app · 1,000 req/s ingest", "Applied by the ingress; set in the Helm values."],
];

export default function ApiOverview() {
  const groups = apiReference();
  const count = groups.reduce((n, g) => n + g.ops.length, 0);
  return (
    <div className="min-w-0">
      <nav aria-label="Breadcrumb" className="text-sm text-mute"><Link href="/docs" className="hover:text-ink">Docs</Link> <span aria-hidden>/</span> <span className="text-ink">API reference</span></nav>
      <h1 className="mt-2 font-display text-4xl font-semibold">JobWatch API</h1>
      <p className="mt-3 max-w-[760px] text-[17px] text-mute">
        Everything in the app is available over a JSON REST API: jobs, runs, incidents, alerting, on-call, analytics, access control and audit.
        {" "}{count} endpoints in {groups.length} areas, generated from the API&apos;s own OpenAPI description so the reference always matches the server.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link href="/settings" className="btn btn-primary"><KeyRound size={15} aria-hidden />Create an API key</Link>
        <a href="/docs/api/openapi.json" className="btn"><Download size={15} aria-hidden />OpenAPI 3.1 description</a>
      </div>

      <dl className="mt-8 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 xl:grid-cols-4">
        {[["Base URL", `${APP_BASE.replace("https://", "")}/api/v1`], ["Authentication", "X-API-Key header"], ["Format", "JSON, UTF-8, UTC timestamps"], ["Identifiers", "UUID"]].map(([k, v]) => (
          <div key={k} className="bg-panel px-4 py-3"><dt className="text-xs text-mute">{k}</dt><dd className="mt-0.5 font-mono text-[13px]">{v}</dd></div>))}
      </dl>

      <div className="mt-10 grid items-start gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <div className="doc-content min-w-0">
          <h2 id="quick-start" className="!mt-0">Quick start</h2>
          <p>Create a key under <b>Settings → API keys</b> with the role it needs, keep it in a secret store, and send it in the <code>X-API-Key</code> header.
            The example lists the jobs that are failing.</p>
          <p>Code samples on these pages use <code>app.example.com</code>; choose <b>Use your JobWatch hosts</b> above to show your own.</p>
        </div>
        <Snippet label="List failing jobs" code={`curl "${APP_BASE}/api/v1/jobs?status=failed" \\\n  -H "X-API-Key: $JOBWATCH_API_KEY"`} />
      </div>

      <div className="doc-content mt-4 max-w-[860px]">
        <h2 id="base-urls">Base URLs</h2>
        <div className="table-wrap"><table><thead><tr><th>Host</th><th>Used for</th></tr></thead><tbody>
          <tr><td className="whitespace-nowrap"><code>{APP_BASE}/api/v1</code></td><td>The REST API in this reference. Self-hosted, it is your app host.</td></tr>
          <tr><td className="whitespace-nowrap"><code>{INGEST_BASE}</code></td><td>Pings and heartbeats from your jobs, and agents. A separate host with its own limits, so a flood of pings cannot slow the API. See <Link href="/docs/api/pings">Pings</Link>.</td></tr>
          <tr><td className="whitespace-nowrap"><code>{APP_BASE}/scim/v2</code></td><td>SCIM 2.0 for your identity provider. See <Link href="/docs/scim">Directory sync</Link>.</td></tr>
        </tbody></table></div>

        <h2 id="authentication">Authentication</h2>
        <p>Every endpoint except pings and public status pages needs credentials. Use one of:</p>
        <ul>
          <li><b>API key</b> in <code>X-API-Key</code>: for scripts, CI and Terraform. Each key has a role, is stored only as a hash, is shown once, and can be revoked at any time. Keys cannot be given the owner role or a role above their creator&apos;s.</li>
          <li><b>Bearer token</b>: a Keycloak access token for a person, in <code>Authorization: Bearer …</code>, with the organization&apos;s id in <code>X-Org-Id</code>. Use it to act as a signed-in user from your own tools.</li>
          <li><b>Session cookie</b>: what the web app uses. Requests that change something must also send the <code>X-CSRF-Token</code> header; not intended for API clients.</li>
        </ul>
        <p>If your organization enforces single sign-on, people must use the identity provider; API keys keep working.</p>
      </div>
      <div className="mt-4 grid max-w-[860px] gap-4 md:grid-cols-2">
        <Snippet label="API key" code={`curl ${APP_BASE}/api/v1/me \\\n  -H "X-API-Key: $JOBWATCH_API_KEY"`} />
        <Snippet label="Bearer token" code={`curl ${APP_BASE}/api/v1/me \\\n  -H "Authorization: Bearer $TOKEN" \\\n  -H "X-Org-Id: $ORG_ID"`} />
      </div>

      <div className="doc-content mt-4 max-w-[860px]">
        <h2 id="roles">Roles</h2>
        <p>Every endpoint shows the lowest role that may call it. Each role can do everything the roles above it in this table can.</p>
        <div className="table-wrap"><table><thead><tr><th>Role</th><th>Adds</th></tr></thead><tbody>
          {ROLES.map(([r, d]) => <tr key={r}><td className="whitespace-nowrap font-medium">{r}</td><td>{d}</td></tr>)}</tbody></table></div>

        <h2 id="errors">Errors</h2>
        <p>Errors use standard HTTP status codes and a JSON body with a <code>detail</code> field. For <code>422</code>, <code>detail</code> is a list with the location and message of each problem.</p>
        <div className="table-wrap"><table><thead><tr><th>Status</th><th>Meaning</th></tr></thead><tbody>
          {ERRORS.map(([c, d]) => <tr key={c}><td><code>{c}</code></td><td dangerouslySetInnerHTML={{ __html: d.replace(/`([^`]+)`/g, "<code>$1</code>") }} /></tr>)}</tbody></table></div>
      </div>
      <div className="mt-4 grid max-w-[860px] gap-4 md:grid-cols-2">
        <Snippet label="403" code={`{\n  "detail": "requires role >= devops"\n}`} />
        <Snippet label="422" code={`{\n  "detail": [\n    {"type": "missing", "loc": ["body", "name"],\n     "msg": "Field required"}\n  ]\n}`} />
      </div>

      <div className="doc-content mt-4 max-w-[860px]">
        <h2 id="pagination">Pagination</h2>
        <p><code>GET /api/v1/jobs</code> is paginated with a cursor: it returns <code>items</code> and <code>next_cursor</code>. Pass <code>next_cursor</code> as <code>cursor</code> to get the next page;
          it is <code>null</code> on the last page. <code>limit</code> sets the page size (default 50, at most 200).</p>
        <p>Other lists (runs, incidents, audit events, alerts sent, deliveries) return the most recent items, newest first, up to <code>limit</code>.</p>
      </div>
      <div className="mt-4 max-w-[860px]">
        <Snippet label="Python: every job" code={`import os, requests\n\nurl = "${APP_BASE}/api/v1/jobs"\nheaders = {"X-API-Key": os.environ["JOBWATCH_API_KEY"]}\njobs, cursor = [], None\nwhile True:\n    page = requests.get(url, headers=headers, params={"limit": 200, "cursor": cursor}, timeout=10).json()\n    jobs += page["items"]\n    cursor = page["next_cursor"]\n    if not cursor:\n        break`} />
      </div>

      <div className="doc-content mt-4 max-w-[860px]">
        <h2 id="rate-limits">Rate limits</h2>
        <p>Responses carry <code>X-RateLimit-Remaining</code>. Over the limit, the API returns <code>429</code> with <code>Retry-After</code> in seconds; back off and retry.</p>
        <div className="table-wrap"><table><thead><tr><th>What</th><th>Limit</th><th>Counted</th></tr></thead><tbody>
          {LIMITS.map(([a, b, c]) => <tr key={a}><td className="font-medium">{a}</td><td className="whitespace-nowrap">{b}</td><td>{c}</td></tr>)}</tbody></table></div>

        <h2 id="versioning">Versioning and compatibility</h2>
        <ul>
          <li>The version is in the path: <code>/api/v1</code>. Breaking changes ship as a new version; <code>v1</code> keeps working.</li>
          <li>Within a version we add endpoints, optional request fields and response fields without notice. Ignore fields you do not recognise.</li>
          <li>Timestamps are ISO 8601 in UTC. Identifiers are UUIDs. Secrets (ping URLs, keys, tokens, invitation links) appear only in the response that creates them.</li>
          <li>Every change made through the API is recorded in the <Link href="/docs/api/audit">audit log</Link> with the key or user that made it.</li>
        </ul>
        <p>Managing JobWatch as code? The <Link href="/docs/terraform">Terraform provider</Link> and <Link href="/docs/kubernetes">Kubernetes annotations</Link> use this API.</p>
      </div>

      <h2 id="resources" className="mt-12 font-display text-[1.45rem] font-semibold">Endpoints by area</h2>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {groups.map((g) => (
          <li key={g.slug}><Link href={`/docs/api/${g.slug}`} className="group flex h-full flex-col rounded-lg border border-line bg-panel p-4 transition hover:border-accent/60">
            <span className="flex items-center justify-between font-medium">{g.name}<ArrowRight size={14} className="text-mute transition group-hover:translate-x-0.5 group-hover:text-accent" aria-hidden /></span>
            <span className="mt-1 flex-1 text-sm text-mute">{g.description}</span>
            <span className="mt-3 text-xs text-mute">{g.ops.length} endpoint{g.ops.length === 1 ? "" : "s"}</span></Link></li>))}
      </ul>
    </div>
  );
}
