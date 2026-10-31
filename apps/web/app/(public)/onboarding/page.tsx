"use client";
/* R69 onboarding: organization → how jobs report → install → first signal → invite the team → alerts.
   Each step does the real thing through the API (bootstrap token, first job, invitations), and every
   step after the first can be skipped. */
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Activity, Check } from "lucide-react";
import { api, mutate, INGEST_URL } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
import { browserZone, parseCrontabLine, withPing } from "@/lib/crontab";

const API = process.env.NEXT_PUBLIC_API_URL; const INGEST = INGEST_URL;
const METHODS = [
  ["heartbeat", "A crontab line", "Paste the entry you most worry about. Nothing to install: one curl appended to it, and the schedule is read from the line."],
  ["agent", "Linux servers", "The agent finds crontabs and systemd timers and reports exit codes, duration, output and the host's state. Install it later, where it earns its place."],
  ["k8s", "Kubernetes", "A Helm-installed agent watches CronJobs and Jobs in the whole cluster or chosen namespaces."],
  ["api", "API", "Post status, duration and exit code as JSON from your own code."],
] as const;
const STEPS = ["Organization", "Connect", "Install", "First signal", "Team", "Alerts"];
const ROLES = [["developer", "Developer"], ["sre", "SRE"], ["devops", "DevOps"], ["viewer", "Viewer"], ["admin", "Admin"]] as const;

function Pre({ children }: { children: string }) {
  const [c, setC] = useState(false);
  return <div className="relative mt-3"><pre className="overflow-auto rounded-md border border-line bg-panel p-3 pr-20 font-mono text-xs">{children}</pre>
    <button type="button" className="btn absolute right-2 top-2 py-1 text-xs" onClick={async () => { try { await navigator.clipboard.writeText(children); setC(true); } catch { setC(false); } }}>{c ? "Copied" : "Copy"}</button></div>;
}

export default function Onboarding() {
  const sess = useQuery({ queryKey: ["session"], queryFn: () => api<{ user: { email: string }; org_id: string | null }>("/auth/session"), retry: false });
  const [step, setStep] = useState(1); const [org, setOrg] = useState(""); const [method, setMethod] = useState<string>("heartbeat");
  const [job, setJob] = useState<any>(null); const [tok, setTok] = useState<any>(null);
  const [cluster, setCluster] = useState("production");
  const [cronLine, setCronLine] = useState("");                       // R74: the pasted crontab entry
  const entry = parseCrontabLine(cronLine);
  const [invites, setInvites] = useState([{ email: "", role: "developer" }]);
  const [sent, setSent] = useState<{ email: string; url?: string | null }[]>([]);
  const createOrg = useMutation({ mutationFn: () => mutate("/auth/orgs" as any, "post", { body: { name: org } } as any) as Promise<{ org_id: string }>, onSuccess: () => { sess.refetch(); setStep(2); } });
  const mkJob = useMutation({ mutationFn: async () => {
    const ws = await api<{ id: string }[]>("/api/v1/workspaces");
    // R74: with a pasted crontab line the job carries the schedule, so the first missing run is detected
    // at its deadline — nothing to infer. Without one it is a plain heartbeat job (failures only).
    const body = entry
      ? { workspace_id: ws[0].id, name: entry.name, description: entry.command.slice(0, 500), schedule_expr: entry.schedule, tz: browserZone(), grace_s: 300, tags: ["crontab"] }
      : { workspace_id: ws[0].id, name: "my-first-job", grace_s: 300 };
    return mutate("/api/v1/jobs", "post", { body: body as any });
  }, onSuccess: (j) => { setJob(j); setStep(4); } });
  const mkTok = useMutation({ mutationFn: () => mutate("/api/v1/agents/bootstrap-token" as any, "post", { body: {} } as any), onSuccess: (t) => { setTok(t); setStep(4); } });
  const sendInvites = useMutation({ mutationFn: async () => {
    const out: { email: string; url?: string | null }[] = [];
    for (const i of invites.filter((x) => x.email.trim())) {
      const r = await mutate("/api/v1/org/invites" as any, "post", { body: i } as any) as { email: string; invite_url?: string | null };
      out.push({ email: r.email, url: r.invite_url });
    }
    return out;
  }, onSuccess: (r) => setSent(r) });
  const jobs = useQuery({ queryKey: ["jobs", "onb"], queryFn: () => api<{ items: any[] }>("/api/v1/jobs?limit=5"), enabled: step === 4, refetchInterval: 3000 });
  const detected = (jobs.data?.items ?? []).filter((j) => j.last_run_at || j.source === "agent" || j.source === "k8s");

  if (sess.isError) return <Wrap step={0}><h1 className="text-xl font-semibold">Sign in to continue</h1><p className="mt-1 text-sm text-mute">Setting up an organization needs a signed-in account.</p><a className="btn btn-primary mt-4" href={`${API}/auth/login?next=/onboarding`}>Sign in</a></Wrap>;
  if (sess.data?.org_id && step === 1) setStep(2);
  const token = tok?.token ?? tok?.bootstrap_token ?? "csb_…";

  return (
    <Wrap step={step}>
      {step === 1 && <><h1 className="text-xl font-semibold">Name your organization</h1><p className="mt-1 text-sm text-mute">Usually your company. Teams, environments and workspaces live inside it, and you can add more later.</p>
        <form onSubmit={(e) => { e.preventDefault(); createOrg.mutate(); }}>
          <label className="mt-5 block text-sm font-medium" htmlFor="org-name">Organization name</label>
          <input id="org-name" className="input mt-1.5" placeholder="Acme Ops" value={org} onChange={(e) => setOrg(e.target.value)} autoFocus />
          <button className="btn btn-primary mt-4" type="submit" disabled={!org.trim() || createOrg.isPending}>Create organization</button></form>
        {createOrg.error && <div className="mt-3"><ErrorBox error={createOrg.error} /></div>}</>}
      {step === 2 && <><h1 className="text-xl font-semibold">How do your jobs run?</h1><p className="mt-1 text-sm text-mute">Pick one to start. You can connect the others later.</p>
        <div className="mt-5 grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Connection method">{METHODS.map(([k, t, d]) => (
          <button key={k} type="button" role="radio" aria-checked={method === k} onClick={() => setMethod(k)} className={`flex flex-col items-start justify-start rounded-lg border p-4 text-left ${method === k ? "border-accent bg-accent/5" : "border-line hover:border-mute/60"}`}><div className="font-medium">{t}</div><div className="mt-1 text-sm text-mute">{d}</div></button>))}</div>
        <button className="btn btn-primary mt-5" onClick={() => setStep(3)}>Continue</button></>}
      {step === 3 && <><h1 className="text-xl font-semibold">Install</h1>
        {method === "agent" && <><p className="mt-1 text-sm text-mute">Generate a one-time install command (valid 24 hours), then run it on each server as root.</p><button className="btn btn-primary mt-4" disabled={mkTok.isPending} onClick={() => mkTok.mutate()}>Generate install command</button></>}
        {method === "k8s" && <><p className="mt-1 text-sm text-mute">Name the cluster as it should appear in alerts, then generate a one-time token (valid 24 hours) for the Helm install.</p>
          <label className="mt-4 block text-sm font-medium" htmlFor="cluster">Cluster name</label><input id="cluster" className="input mt-1.5 max-w-xs" value={cluster} onChange={(e) => setCluster(e.target.value)} />
          <button className="btn btn-primary mt-4 block" disabled={mkTok.isPending || !cluster.trim()} onClick={() => mkTok.mutate()}>Generate Helm command</button></>}
        {method === "heartbeat" && <><p className="mt-1 text-sm text-mute">Paste one line from <code className="font-mono">crontab -l</code>, the job you would least like to find out about in a week. We take its schedule, name the job after the command, and give the line back with one curl appended.</p>
          <label className="mt-4 block text-sm font-medium" htmlFor="cronline">Crontab line</label>
          <textarea id="cronline" className="input mt-1.5 h-20 w-full font-mono text-xs" placeholder="15 2 * * *  /opt/jobs/pg-backup.sh" value={cronLine} onChange={(e) => setCronLine(e.target.value)} spellCheck={false} />
          <p className="mt-1.5 text-xs" aria-live="polite" data-testid="cron-parse">{entry
            ? <span className="text-ok">Job <b>{entry.name}</b>, schedule <code className="font-mono">{entry.schedule}</code>, in your zone {browserZone()}.</span>
            : cronLine.trim() ? <span className="text-warn">Not a crontab entry: expected five schedule fields (or @daily) and a command. You can continue without one; the job then detects failures but not missed runs.</span>
            : <span className="text-mute">Or leave it empty for a plain ping URL you call from anywhere.</span>}</p>
          <button className="btn btn-primary mt-4" disabled={mkJob.isPending} onClick={() => mkJob.mutate()}>{entry ? "Create the job" : "Create a ping URL"}</button></>}
        {method === "api" && <><p className="mt-1 text-sm text-mute">We will create a first job and give you its URL.</p><button className="btn btn-primary mt-4" disabled={mkJob.isPending} onClick={() => mkJob.mutate()}>Create my first job</button></>}
        {(mkTok.error || mkJob.error) && <div className="mt-3"><ErrorBox error={mkTok.error ?? mkJob.error} /></div>}</>}
      {step === 4 && <><h1 className="text-xl font-semibold">Waiting for the first signal</h1>
        {tok && method === "agent" && (tok.install ? <Pre>{tok.install}</Pre>
          : <p className="mt-3 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm">The installer cannot be served yet: {tok.install_problem ?? "the server's agent download settings are incomplete"}. See <Link className="underline" href="/docs/linux-agent">Linux agent</Link> for a manual install with token <code className="font-mono">{token}</code>.</p>)}
        {tok && method === "k8s" && <Pre>{`helm upgrade --install jobwatch-agent infra/helm/cronsentinel-agent -n jobwatch --create-namespace \\\n  --set server=${INGEST} \\\n  --set clusterName=${cluster.trim() || "production"} \\\n  --set bootstrapToken=${token}`}</Pre>}
        {job && method === "heartbeat" && entry && <><p className="mt-1 text-sm text-mute">Replace the line in <code className="font-mono">crontab -e</code> with this one. <code className="font-mono">&amp;&amp;</code> means a failing command never pings, so a failure and a run that never happened both show as the job missing its deadline.</p>
          <Pre>{withPing(entry, `${INGEST}/ping/${job.heartbeat_token}`)}</Pre></>}
        {job && !(method === "heartbeat" && entry) && <Pre>{method === "api"
          ? `curl -X POST ${INGEST}/api/v1/heartbeat/${job.heartbeat_token} \\\n  -H 'Content-Type: application/json' \\\n  -d '{"status":"success","duration_ms":1240,"exit_code":0}'`
          : `# add to the end of your script or pipeline step\ncurl -fsS ${INGEST}/ping/${job.heartbeat_token}`}</Pre>}
        {job && <p className="mt-2 text-xs text-mute">Copy this now. The token is stored hashed and shown only once; you can issue a new one from the job page.</p>}
        <p className="mt-4 text-sm" aria-live="polite">{detected.length ? <span className="text-ok">✓ {detected.length} job{detected.length > 1 ? "s" : ""} detected: {detected.map((j) => j.name).join(", ")}</span> : <span className="text-mute">Listening… this page updates by itself.</span>}</p>
        <div className="mt-5 flex gap-2"><button className="btn btn-primary" disabled={!detected.length} onClick={() => setStep(5)}>Continue</button><button className="btn" onClick={() => setStep(5)}>Skip for now</button></div></>}
      {step === 5 && <><h1 className="text-xl font-semibold">Invite your team</h1><p className="mt-1 text-sm text-mute">They join when they sign up or sign in with the invited email. With single sign-on, people on your verified domain can also join on their own.</p>
        {!sent.length ? <form className="mt-5 space-y-2" onSubmit={(e) => { e.preventDefault(); sendInvites.mutate(); }}>
          {invites.map((inv, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              <input aria-label={`Teammate ${i + 1} email`} className="input min-w-0 flex-1 basis-56" type="email" placeholder="name@company.com" value={inv.email}
                onChange={(e) => setInvites(invites.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} />
              <select aria-label={`Teammate ${i + 1} role`} className="input w-36" value={inv.role} onChange={(e) => setInvites(invites.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))}>
                {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </div>))}
          {invites.length < 10 && <button type="button" className="text-sm text-accent hover:underline" onClick={() => setInvites([...invites, { email: "", role: "developer" }])}>Add another</button>}
          {sendInvites.error && <ErrorBox error={sendInvites.error} />}
          <div className="flex gap-2 pt-3"><button className="btn btn-primary" type="submit" disabled={sendInvites.isPending || !invites.some((x) => x.email.trim())}>Send invitations</button>
            <button type="button" className="btn" onClick={() => setStep(6)}>Skip</button></div>
        </form> : <div className="mt-5 space-y-3">
          <p className="text-sm text-ok">✓ {sent.length} invitation{sent.length > 1 ? "s" : ""} created. Send each person their link; links are shown once and expire in 7 days.</p>
          {sent.map((x) => <div key={x.email}><div className="text-sm font-medium">{x.email}</div>{x.url && <Pre>{x.url}</Pre>}</div>)}
          <button className="btn btn-primary" onClick={() => setStep(6)}>Continue</button></div>}</>}
      {step === 6 && <><h1 className="text-xl font-semibold">Where should alerts go?</h1><p className="mt-1 text-sm text-mute">Connect Slack, Microsoft Teams, email, PagerDuty or a webhook, then add a rule such as "any production job failed".</p>
        <div className="mt-5 flex gap-2"><Link className="btn btn-primary" href="/alerting">Set up alerting</Link><Link className="btn" href="/">Go to the dashboard</Link></div></>}
    </Wrap>
  );
}

function Wrap({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-bg">
      <header className="border-b border-line bg-panel"><div className="mx-auto flex max-w-3xl items-center gap-2 px-5 py-4 font-display font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-accent/15 text-accent"><Activity size={15} aria-hidden /></span>Set up WeCrew Argus</div></header>
      <div className="mx-auto max-w-3xl px-5 py-10">
        {step > 0 && <ol className="mb-10 grid grid-cols-3 gap-2 sm:grid-cols-6" aria-label="Setup steps">{STEPS.map((s, i) => {
          const n = i + 1, done = n < step, cur = n === step;
          return <li key={s} aria-current={cur ? "step" : undefined} className="flex items-center gap-2 text-xs">
            <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold ${done ? "border-ok bg-ok text-[rgb(var(--bg))]" : cur ? "border-accent text-accent" : "border-line text-mute"}`}>{done ? <Check size={12} aria-hidden /> : n}</span>
            <span className={cur ? "font-medium" : "text-mute"}>{s}</span></li>;
        })}</ol>}
        <div className="rounded-lg border border-line bg-panel p-6 sm:p-8">{children}</div>
      </div>
    </main>
  );
}
