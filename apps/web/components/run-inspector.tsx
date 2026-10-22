"use client";
/* R70 — one run, inspected the way an engineer debugs it: what happened (status, exit code and what
   it means), where (the host and how it looked while the run was going), the evidence (stderr),
   then the full output in a log viewer with search, error highlighting, copy and download. */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api, downloadText, type Execution, type ExecutionDetail, type HostContext, type HostMetricPoint, type Job } from "@/lib/api";

type Exec = Execution & Record<string, any>;
type Ev = { sequence: number; kind: string; agent_ts?: string | null; server_ts: string; payload?: any };
import { RunCheckResult } from "@/components/run-checks";
import { GAUGES, tone } from "@/components/host-panel";
import { ago, dur, ts, statusLabel } from "@/lib/format";
import { Status, Skeleton, ErrorBox } from "@/components/ui";

/** Lines that usually carry the reason a job failed. */
// R72: word-start boundary so "errors: 0" / "0 errors" / "noerror" are not errors; "error" at a
// word start still catches Error, ERROR:, BackupError (via "Exception"/"Error" suffix below).
const ERR_CORE = /(\b(error|errors?:|fatal|traceback|exception|panic|killed|denied|refused|oom|segfault|unreachable)\b|no space|out of memory|time(d )?out|\bfail(ed|ure)\b|cannot|could not|not found)/i;
const ERR_CLASS = /\b[A-Z]\w*(Error|Exception)\b/;   // BackupError, OperationalError — case-sensitive on purpose
const BENIGN_RE = /\b(0|no|zero)\s+(errors?|failures?|warnings?)\b|\berrors?:\s*0\b|\bwithout\s+errors?\b/i;
export const ERROR_RE = { test: (s: string) => (ERR_CORE.test(s) || ERR_CLASS.test(s)) && !BENIGN_RE.test(s) };
const WARN_RE = /\b(warn|warning|retry|retrying|slow|deprecated)\b/i;

const KIND_LABEL: Record<string, string> = { scheduled: "Scheduled", start: "Started", started: "Started", progress: "Still running", success: "Completed", fail: "Failed" };

/** The last few stderr lines that look like an error, else simply the last lines. */
export function evidence(stderr: string, n = 3): string[] {
  const lines = stderr.split("\n").map((l) => l.trimEnd()).filter(Boolean);
  const errs = lines.filter((l) => ERROR_RE.test(l));
  const pick = errs.length ? errs : lines;
  // the first error is usually the cause and the last one the symptom; keep both
  return pick.length <= n ? pick : [...pick.slice(0, n - 1), pick[pick.length - 1]];
}

export function peakDuring(points: HostMetricPoint[], cpus?: number | null) {
  const out: { g: (typeof GAUGES)[number]; v: number; t: "ok" | "warn" | "bad" | "mute" }[] = [];
  for (const g of GAUGES) {
    const vals = points.map((p) => p[g.key] as number | null).filter((v): v is number => v != null);
    if (!vals.length) continue;
    const v = Math.max(...vals);
    out.push({ g, v, t: tone(g.key, v, cpus) });
  }
  return out;
}

function FailureSummary({ d, job, host }: { d: ExecutionDetail; job?: Job; host?: HostContext | null }) {
  const e = d.execution as Exec;
  const failed = e.status === "failed" || e.status === "timeout" || e.status === "missed";
  if (!failed) return null;
  const ev = evidence(d.logs.stderr || "");
  const peaks = peakDuring(d.host?.metrics_during ?? [], (d.host?.facts?.cpus as number | undefined) ?? (host?.server.facts?.cpus as number | undefined));
  const hot = peaks.filter((p) => p.t === "bad");
  const list = (xs: string[]) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
  const agent = host?.agent;
  return (
    <section className="border-b border-line bg-bad/[.04] px-4 py-3 text-sm" aria-labelledby="why-h" data-testid="failure-summary">
      <h3 id="why-h" className="mb-2 text-xs font-semibold uppercase tracking-wide text-bad">Why it {e.status === "missed" ? "did not run" : "failed"}</h3>
      <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
        {e.status === "missed" ? (<>
          <dt className="text-mute">What</dt>
          <dd>No start was reported by the deadline{job?.grace_s ? ` (${job.grace_s}s after the scheduled time)` : ""}.
            {agent?.state === "offline" && <span className="text-bad"> The agent on {host?.server.hostname} is offline, so the job may have run unobserved.</span>}
            {agent?.state === "online" && <span> The agent on {host?.server.hostname} is online, so cron itself did not start the job: check the crontab, the user's permissions and whether the schedule changed.</span>}</dd>
        </>) : (<>
          <dt className="text-mute">What</dt>
          <dd>{e.status === "timeout" ? <>Ran past the time limit{job?.expected_runtime_s ? ` of ${dur(job.expected_runtime_s * 1000)}` : ""}.</> : <>Exit code <span className="font-mono font-semibold">{e.exit_code ?? "unknown"}</span>{d.exit_meaning && <> — {d.exit_meaning}</>}</>}
            {e.failure_reason && <span className="text-mute"> ({String(e.failure_reason)})</span>}</dd>
        </>)}
        {(d.host?.hostname || host) && <>
          <dt className="text-mute">Where</dt>
          <dd><span className="font-mono">{d.host?.hostname ?? host?.server.hostname}</span>
            {peaks.length > 0 ? <> — during the run: {peaks.map((p, i) => <span key={p.g.key}>{i ? " · " : ""}<span className={p.t === "bad" ? "font-semibold text-bad" : p.t === "warn" ? "text-warn" : ""}>{p.g.label.toLowerCase()} {p.g.fmt(p.v)}</span></span>)}
              {hot.length > 0 && <span className="text-bad">. {list(hot.map((p) => p.g.label.toLowerCase()))} {hot.length > 1 ? "were" : "was"} critically high while this ran.</span>}</>
              : <span className="text-mute"> — no host samples for that window.</span>}</dd>
        </>}
        {ev.length > 0 && <>
          <dt className="text-mute">Evidence</dt>
          <dd><pre className="whitespace-pre-wrap break-words font-mono text-xs text-bad" data-testid="evidence">{ev.join("\n")}</pre></dd>
        </>}
      </dl>
      {job && <div className="mt-2 text-xs"><Link href={`/copilot?job_id=${job.id}&q=${encodeURIComponent(`Why did ${job.name} fail at ${ts(e.agent_ts_start ?? e.scheduled_ts)}?`)}`} className="text-accent hover:underline">Ask Copilot about this run</Link></div>}
    </section>
  );
}

function HostDuring({ points, cpus }: { points: HostMetricPoint[]; cpus?: number | null }) {
  if (!points.length) return null;
  const cols = GAUGES.filter((g) => points.some((p) => p[g.key] != null));
  return (
    <details className="border-b border-line px-4 py-2 text-sm" data-testid="host-during">
      <summary className="cursor-pointer text-xs text-mute">Host samples during this run ({points.length})</summary>
      <table className="mt-2 w-full text-xs"><thead><tr className="text-mute"><th className="text-left font-normal">Time</th>{cols.map((g) => <th key={g.key} className="text-right font-normal">{g.label}</th>)}</tr></thead>
        <tbody>{points.map((p) => <tr key={p.ts} className="border-t border-line/60"><td className="py-1 font-mono">{ts(p.ts)}</td>
          {cols.map((g) => { const v = p[g.key] as number | null; const t = tone(g.key, v, cpus); return <td key={g.key} className={`py-1 text-right font-mono ${t === "bad" ? "text-bad" : t === "warn" ? "text-warn" : ""}`}>{v == null ? "—" : g.fmt(v)}</td>; })}</tr>)}</tbody></table>
    </details>
  );
}

type Stream = "stdout" | "stderr" | "both";

export function LogViewer({ logs, bytes, executionId }: { logs: { stdout: string; stderr: string }; bytes?: Record<string, number>; executionId: string }) {
  const has = { stdout: !!logs.stdout, stderr: !!logs.stderr };
  const [stream, setStream] = useState<Stream>(has.stderr ? "stderr" : "stdout");
  const [q, setQ] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [wrap, setWrap] = useState(true);
  const [copied, setCopied] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);
  const lines = useMemo(() => {
    const mk = (s: "stdout" | "stderr") => (logs[s] || "").replace(/\n$/, "").split("\n").map((text, i) => ({ s, n: i + 1, text }));
    const all = stream === "both" ? [...mk("stdout"), ...mk("stderr")] : mk(stream);
    return all.filter((l) => l.text !== "" || all.length === 1);
  }, [logs, stream]);
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return lines.filter((l) => (!errorsOnly || ERROR_RE.test(l.text)) && (!needle || l.text.toLowerCase().includes(needle)));
  }, [lines, q, errorsOnly]);
  const errCount = lines.filter((l) => ERROR_RE.test(l.text)).length;
  if (!has.stdout && !has.stderr) return <div className="px-4 py-3 text-sm text-mute">No output was captured for this run. Wrap the command with <code className="font-mono">jobwatch-run</code>, or post output to the ping URL, to see stdout and stderr here.</div>;
  const copy = async () => { try { await navigator.clipboard.writeText(shown.map((l) => l.text).join("\n")); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ } };
  const total = (bytes?.stdout ?? 0) + (bytes?.stderr ?? 0);
  return (
    <section aria-labelledby="logs-h" data-testid="log-viewer">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-xs">
        <h3 id="logs-h" className="sr-only">Output</h3>
        <div className="flex rounded-md border border-line" role="tablist" aria-label="Stream">
          {(["stderr", "stdout", "both"] as Stream[]).map((s) => (
            <button key={s} role="tab" aria-selected={stream === s} disabled={s !== "both" && !has[s]} onClick={() => setStream(s)}
                    className={`px-2.5 py-1 font-mono first:rounded-l-md last:rounded-r-md disabled:opacity-40 ${stream === s ? "bg-raised font-semibold" : "text-mute hover:text-ink"}`}>
              {s}</button>))}
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find in output…" aria-label="Find in output" className="input w-44 py-1 text-xs" />
        <label className="flex items-center gap-1.5 text-mute"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />Errors only{errCount > 0 && <span className="rounded-full bg-bad/15 px-1.5 text-[11px] text-bad">{errCount}</span>}</label>
        <label className="flex items-center gap-1.5 text-mute"><input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} />Wrap</label>
        <span className="ml-auto text-mute">{q || errorsOnly ? `${shown.length} of ${lines.length} lines` : `${lines.length} lines`}</span>
        <button className="btn py-1 text-xs" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
        <button className="btn py-1 text-xs" onClick={() => { setDlError(null); downloadText(`/api/v1/executions/${executionId}/logs?stream=${stream}`, `run-${executionId}-${stream}.log`).catch((e: Error) => setDlError(e.message || "Download failed")); }}>Download</button>
        {dlError && <span role="alert" className="basis-full text-bad">Download failed: {dlError}</span>}
      </div>
      <div className="max-h-[420px] overflow-auto bg-bg/60" data-testid="log-lines">
        {shown.length === 0 ? <p className="px-4 py-6 text-center text-xs text-mute">No lines match.</p> : (
          <ol className={`py-1 font-mono text-xs leading-5 ${wrap ? "" : "w-max min-w-full"}`}>
            {shown.map((l) => {
              const err = ERROR_RE.test(l.text), warn = !err && WARN_RE.test(l.text);
              return (
                <li key={`${l.s}${l.n}`} className={`grid grid-cols-[3.5rem_1fr] gap-3 px-3 ${err ? "bg-bad/10 text-bad" : warn ? "text-warn" : l.s === "stderr" ? "text-ink" : "text-ink/90"}`}>
                  <span className="select-none text-right text-mute/70">{stream === "both" && <span className="mr-1 text-[10px]">{l.s === "stderr" ? "E" : "O"}</span>}{l.n}</span>
                  <span className={wrap ? "whitespace-pre-wrap break-all" : "whitespace-pre"}>{highlight(l.text, q)}</span>
                </li>);
            })}
          </ol>)}
      </div>
      <div className="flex flex-wrap justify-between gap-2 border-t border-line px-3 py-1.5 text-[11px] text-mute">
        <span>The agent keeps the last 32 KiB of each stream; secrets are redacted before storage.</span>
        {total > 0 && <span>{fmtBytes(total)} stored</span>}
      </div>
    </section>
  );
}

const fmtBytes = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB` : `${(n / 1048576).toFixed(1)} MiB`);

function highlight(text: string, q: string) {
  const needle = q.trim();
  if (!needle) return text;
  const parts = text.split(new RegExp(`(${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"));
  return parts.map((p, i) => (p.toLowerCase() === needle.toLowerCase() ? <mark key={i} className="rounded-sm bg-accent/30 text-ink">{p}</mark> : p));
}

export function RunInspector({ id, job, host, onCompare }: { id: string; job?: Job; host?: HostContext | null; onCompare?: (id: string) => void }) {
  const q = useQuery({ queryKey: ["exec", id], queryFn: () => api<ExecutionDetail>(`/api/v1/executions/${id}`) });
  if (q.isLoading) return <div className="card bg-panel p-4"><Skeleton rows={5} /></div>;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data!;
  const e = d.execution as Exec; const timeline = d.timeline as Ev[];
  const t0 = new Date(timeline[0]?.agent_ts ?? timeline[0]?.server_ts ?? e.scheduled_ts).getTime();
  const over = e.duration_ms && job?.expected_runtime_s && e.duration_ms > job.expected_runtime_s * 1000;
  return (
    <div className="card bg-panel" data-testid="run-inspector">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line px-4 py-3 text-sm">
        <Status s={e.status} />
        <span className="text-mute">{ts(e.agent_ts_start ?? e.scheduled_ts)} <span className="text-mute/70">({ago(e.agent_ts_start ?? e.scheduled_ts)})</span></span>
        <span>Took <b className="tnum">{dur(e.duration_ms)}</b>{over && <span className="ml-1 text-warn">— over expected {dur(job!.expected_runtime_s! * 1000)}</span>}</span>
        <span title={d.exit_meaning ?? undefined}>Exit <span className={`font-mono ${e.exit_code ? "font-semibold text-bad" : ""}`}>{e.exit_code ?? "—"}</span></span>
        {(d.host?.hostname ?? e.host) && <span title={job?.server_id ? "The server the agent discovered this job on" : "Host name as reported by the run itself"}>on <span className="font-mono">{d.host?.hostname ?? e.host}</span>{!job?.server_id && <span className="ml-1 text-xs text-mute">(reported)</span>}</span>}
        {e.skew_ms ? <span className="text-mute">clock skew {e.skew_ms} ms</span> : null}
        {onCompare && <button className="btn ml-auto py-1 text-xs" onClick={() => onCompare(id)}>Compare with previous</button>}
      </div>
      <FailureSummary d={d} job={job} host={host} />
      <RunCheckResult metrics={e.metrics as Record<string, number> | undefined} failures={e.meta?.assertion_failures} anomalies={e.meta?.anomalies} failed={e.status === "failed"} />
      <ol className="border-b border-line px-4 py-3" aria-label="Timeline">
        {timeline.map((t) => {
          const at = new Date(t.agent_ts ?? t.server_ts).getTime();
          return (
            <li key={t.sequence} className="grid grid-cols-[90px_80px_1fr] gap-3 py-1 text-sm">
              <span className="font-mono text-xs text-mute">{ts(t.agent_ts ?? t.server_ts)}</span>
              <span className="font-mono text-xs text-mute">+{dur(at - t0)}</span>
              <span>{KIND_LABEL[t.kind] ?? t.kind}
                {t.payload?.command && <span className="ml-2 break-all font-mono text-xs text-mute">{t.payload.command}</span>}
                {t.payload?.passive && <span className="ml-2 text-xs text-warn">passive · exit code unknown</span>}</span>
            </li>);
        })}
        {timeline.length === 0 && <li className="text-sm text-mute">No events — {statusLabel[e.status] ?? e.status} was recorded by the scheduler.</li>}
      </ol>
      <HostDuring points={d.host?.metrics_during ?? []} cpus={(d.host?.facts?.cpus as number | undefined) ?? (host?.server.facts?.cpus as number | undefined)} />
      {/* key: a new run gets fresh tab/search/filter state instead of inheriting the previous run's */}
      <LogViewer key={id} logs={{ stdout: d.logs.stdout ?? "", stderr: d.logs.stderr ?? "" }} bytes={d.log_bytes} executionId={id} />
    </div>
  );
}
