"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, mutate, type Job, type Execution, type JobHost, INGEST_URL } from "@/lib/api";
import { RunChecks, UnusualRuns } from "@/components/run-checks";
import { HostPanel } from "@/components/host-panel";
import { RunInspector } from "@/components/run-inspector";
import { ago, dur, ts, statusLabel } from "@/lib/format";
import { Page, Status, Strip, Skeleton, ErrorBox, Empty } from "@/components/ui";

function Compare({ a, b, onClose }: { a: string; b: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["compare", a, b], queryFn: () => api<{ a: any; b: any; delta: { duration_ms: number; pct: number } | null }>(`/api/v1/executions/${a}/compare/${b}`) });
  if (!q.data) return null;
  const rows: [string, (x: any) => string][] = [["Status", (x) => statusLabel[x.status] ?? x.status], ["Duration", (x) => dur(x.duration_ms)], ["Exit code", (x) => String(x.exit_code ?? "—")], ["Host", (x) => x.host ?? "—"], ["Started", (x) => ts(x.agent_ts_start)]];
  return (
    <div className="mb-4 rounded-lg border border-line bg-panel p-4">
      <div className="mb-2 flex items-center justify-between text-sm"><b>Comparison</b>{q.data.delta && <span className={q.data.delta.pct > 20 ? "text-warn" : "text-mute"}>{q.data.delta.pct > 0 ? "+" : ""}{q.data.delta.pct}% duration vs previous</span>}<button className="btn" onClick={onClose}>Close</button></div>
      <table className="w-full text-sm"><tbody>{rows.map(([l, f]) => (
        <tr key={l} className="border-t border-line"><td className="py-1.5 text-mute">{l}</td><td className="font-mono text-xs">{f(q.data!.b)}</td><td className="font-mono text-xs">{f(q.data!.a)}</td></tr>))}</tbody>
        <thead><tr className="text-xs text-mute"><th /><th className="text-left font-normal">previous</th><th className="text-left font-normal">selected</th></tr></thead></table>
    </div>
  );
}

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["job", id], queryFn: () => api<Job>(`/api/v1/jobs/${id}`) });
  const execs = useQuery({ queryKey: ["execs", id, 100], queryFn: () => api<Execution[]>(`/api/v1/jobs/${id}/executions?limit=100`) });
  const next = useQuery({ queryKey: ["next", id], queryFn: () => api<{ human: string | null; runs: string[] }>(`/api/v1/jobs/${id}/next-runs?n=3`) });
  // R70: the server this job runs on — agent state, facts, 24 h of samples, sibling jobs
  const host = useQuery({ queryKey: ["job-host", id], queryFn: () => api<JobHost>(`/api/v1/jobs/${id}/host`), refetchInterval: 60_000 });
  const [sel, setSel] = useState<string | null>(null);
  const [cmp, setCmp] = useState<[string, string] | null>(null);
  const impact = useQuery({ queryKey: ["impact", id], queryFn: () => api<{ upstream: any[]; downstream: any[] }>(`/api/v1/jobs/${id}/impact`) });
  const allJobs = useQuery({ queryKey: ["jobs", "all"], queryFn: () => api<{ items: Job[] }>("/api/v1/jobs?limit=200") });
  const [depSel, setDepSel] = useState("");
  const addDep = useMutation({ mutationFn: () => mutate("/api/v1/dependencies", "post", { body: { job_id: id, depends_on_job_id: depSel } }), onSuccess: () => { setDepSel(""); qc.invalidateQueries({ queryKey: ["impact", id] }); } });
  const rmDep = useMutation({ mutationFn: (d: string) => mutate("/api/v1/dependencies", "delete", { query: { job_id: id, depends_on_job_id: d } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["impact", id] }) });
  const pause = useMutation({ mutationFn: (paused: boolean) => mutate("/api/v1/jobs/{job_id}", "patch", { path: { job_id: id }, body: { paused } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["job", id] }) });
  // R40: replace a leaked ping URL without losing the job's history. The old token stops working immediately.
  // R41: tokens are stored hashed, so the full URL exists only in this response. Keep it in memory
  // for this page view and say plainly that it will not be shown again.
  const [freshTok, setFreshTok] = useState<string | null>(null);
  const rotate = useMutation({ mutationFn: () => mutate("/api/v1/jobs/{job_id}/rotate-token", "post", { path: { job_id: id } }),
    onSuccess: (r: any) => { setFreshTok(r?.heartbeat_token ?? null); qc.invalidateQueries({ queryKey: ["job", id] }); } });
  if (job.error) return <Page title="Job"><ErrorBox error={job.error} /></Page>;
  if (!job.data) return <Page title="Job"><Skeleton /></Page>;
  const j = job.data; const INGEST = INGEST_URL;
  const tok = freshTok ?? `<token ending ${j.heartbeat_token_hint}>`; const list = execs.data ?? []; const selected = sel ?? list[0]?.id;
  const compare = (eid: string) => { const i = list.findIndex((e) => e.id === eid); if (i >= 0 && list[i + 1]) setCmp([list[i + 1].id, eid]); };
  const rate = list.length ? Math.round(100 * list.filter((e) => e.status === "success").length / list.filter((e) => e.status !== "running" && e.status !== "scheduled").length || 0) : null;

  return (
    <Page title={<span className="flex items-center gap-3">{j.name}<Status s={j.status} /></span>}
          actions={<div className="flex gap-2"><Link href={`/copilot?job_id=${id}&q=${encodeURIComponent(`Why is ${j.name} ${j.status}?`)}`} className="btn">Ask Copilot</Link><button className="btn" onClick={() => pause.mutate(!j.paused)}>{j.paused ? "Resume monitoring" : "Pause monitoring"}</button><button className="btn" disabled={rotate.isPending} onClick={() => { if (confirm("Issue a new ping URL? The current one stops working immediately, so update every script that uses it.")) rotate.mutate(); }}>New ping URL</button></div>}>
      {freshTok && <div className="mb-5 rounded-md border border-accent/50 bg-accent/[.07] px-4 py-3 text-sm" role="status">
        <div className="font-medium">Copy the new ping URL now. It is stored hashed and will not be shown again.</div>
        <div className="mt-2 flex flex-wrap items-center gap-2"><code className="min-w-0 flex-1 break-all rounded border border-line bg-bg px-2 py-1 font-mono text-xs">{`${INGEST}/ping/${freshTok}`}</code>
          <button className="btn" onClick={() => navigator.clipboard?.writeText(`${INGEST}/ping/${freshTok}`)}>Copy</button></div>
      </div>}
      <dl className="mb-5 grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-5">
        <div><dt className="text-mute">Schedule</dt><dd>{j.schedule_human ?? "Heartbeat only"}{j.schedule_expr && <span className="ml-2 font-mono text-xs text-mute">{j.schedule_expr} · {j.tz}</span>}</dd></div>
        <div><dt className="text-mute">Next expected</dt><dd>{next.data?.runs[0] ? `${ts(next.data.runs[0])} (${ago(next.data.runs[0])})` : "—"}</dd></div>
        <div><dt className="text-mute">Last run</dt><dd>{j.last_run_at ? `${ago(j.last_run_at)} · ${statusLabel[j.last_status ?? ""] ?? j.last_status}` : "Never"}</dd></div>
        <div><dt className="text-mute">Success rate (last {list.length})</dt><dd>{rate == null ? "—" : `${rate}%`}</dd></div>
        <div><dt className="text-mute">Expected runtime</dt><dd>{j.expected_runtime_s ? dur(j.expected_runtime_s * 1000) : "not set"} · grace {j.grace_s}s</dd></div>
      </dl>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          <div>
            <div className="mb-1 flex items-baseline justify-between text-xs text-mute"><span>Run history — bar height = duration, click to inspect</span><span>older → newer</span></div>
            {execs.isLoading ? <div className="skeleton h-6" /> : list.length === 0 ? <Empty title="No runs recorded yet" hint={`Ping this job: curl ${INGEST}/ping/${tok}`} />
              : <div className="rounded-md border border-line px-3 py-2"><Strip execs={list} onPick={setSel} /></div>}
          </div>
          {cmp && <Compare a={cmp[0]} b={cmp[1]} onClose={() => setCmp(null)} />}
          {selected ? <RunInspector id={selected} onCompare={compare} job={j} host={host.data?.context} /> : list.length > 0 && <p className="text-sm text-mute">Select a run.</p>}
          <div className="tbl card" data-testid="run-table">
            {/* R68: four short columns fit the panel; the 640 px scrolling minimum hid Took and Exit */}
            <div className="row grid-cols-[110px_1fr_70px_50px] th" style={{ minWidth: 0 }}><span>Started</span><span>Status</span><span className="text-right">Took</span><span className="text-right">Exit</span></div>
            <div className="max-h-[320px] overflow-auto">
              {list.map((e) => (
                <button key={e.id} onClick={() => setSel(e.id)} style={{ minWidth: 0 }} aria-current={selected === e.id ? "true" : undefined} className={`row w-full grid-cols-[110px_1fr_70px_50px] text-left ${selected === e.id ? "bg-accent/5" : ""}`}>
                  <span className="font-mono text-xs">{ts(e.agent_ts_start ?? e.scheduled_ts)}</span>
                  <span className="flex min-w-0 flex-wrap items-center gap-x-1.5"><Status s={e.status} />{!!e.anomalies?.length && <span className="whitespace-nowrap rounded-full bg-warn/15 px-1.5 text-[11px] text-warn" title={e.anomalies.map((a: any) => a.message).join("; ")}>Unusual</span>}</span>
                  <span className="text-right font-mono text-xs">{dur(e.duration_ms)}</span><span className={`text-right font-mono text-xs ${e.exit_code ? "text-bad" : ""}`}>{e.exit_code ?? "—"}</span>
                </button>))}
            </div>
          </div>
          <RunChecks jobId={j.id} rules={j.assertions ?? []} canEdit />
          <UnusualRuns jobId={j.id} sensitivity={j.anomaly_sensitivity ?? "normal"} action={j.anomaly_action ?? "warn"} />
        </div>
        <div className="min-w-0 lg:sticky lg:top-20 lg:self-start">
          {host.isLoading ? <div className="card bg-panel p-4"><Skeleton rows={5} /></div> : host.error ? <ErrorBox error={host.error} /> : <HostPanel ctx={host.data?.context} source={host.data?.source ?? "ping"} lastHost={host.data?.last_host} currentJobId={id} />}
        </div>
      </div>

      <section className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
        <div className="card p-3"><div className="mb-1 font-medium">Depends on</div>
          {impact.data?.upstream.length ? impact.data.upstream.map((u) => <div key={u.id} className="flex items-center justify-between py-1"><Link href={`/jobs/${u.id}`} className="flex items-center gap-2 hover:underline"><span className={`dot dot-${u.status}`} />{u.name}</Link><button className="text-xs text-mute hover:text-bad" onClick={() => rmDep.mutate(u.id)}>remove</button></div>) : <p className="text-mute">Runs independently.</p>}
          <div className="mt-2 flex gap-2"><select className="flex-1 rounded-md border border-line bg-panel px-2 py-1" value={depSel} onChange={(e) => setDepSel(e.target.value)}><option value="">Add upstream job…</option>{allJobs.data?.items.filter((x) => x.id !== id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select><button className="btn" disabled={!depSel} onClick={() => addDep.mutate()}>Add</button></div>
          {addDep.error && <p className="mt-1 text-xs text-bad">{(addDep.error as Error).message}</p>}</div>
        <div className="card p-3"><div className="mb-1 font-medium">Downstream impact if this fails</div>
          {impact.data?.downstream.length ? impact.data.downstream.map((u) => <Link key={u.id} href={`/jobs/${u.id}`} className="flex items-center gap-2 py-1 hover:underline"><span className={`dot dot-${u.status}`} /><span className="text-mute">{"→".repeat(u.depth)}</span>{u.name}</Link>) : <p className="text-mute">Nothing depends on this job.</p>}</div>
      </section>
      <details className="mt-6 text-sm"><summary className="cursor-pointer text-mute">Integration snippets</summary>
        <pre className="mt-2 overflow-auto rounded-md border border-line bg-panel p-3 font-mono text-xs">{`# simple
curl -fsS ${INGEST}/ping/${tok}

# start/finish with exit code (bash)
H=${INGEST}/heartbeat/${tok}
curl -fsS $H/start; ./your-job.sh && curl -fsS $H/success || curl -fsS $H/fail

# agent wrapper (captures logs, duration, exit code)
jobwatch-run --job ${tok} -- ./your-job.sh`}</pre>
        {!freshTok && <p className="mt-2 text-xs text-mute">The full ping URL was shown once when this job was created. Lost it? Choose New ping URL above.</p>}</details>
    </Page>
  );
}
