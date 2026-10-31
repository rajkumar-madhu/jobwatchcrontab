"use client";
/* R70 — the server a job runs on, Datadog-host-style: agent state, facts, four gauges with 24 h
   sparklines, and the other jobs sharing the box. Used by the job page (side panel) and the agent
   page (header). Everything shown comes from GET /jobs/{id}/host or GET /agents/{id}. */
import Link from "next/link";
import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";
import type { HostContext, HostMetricPoint } from "@/lib/api";
import { ago, ts } from "@/lib/format";

export const AGENT_STATE: Record<string, { label: string; cls: string; dot: string }> = {
  online: { label: "Agent online", cls: "text-ok", dot: "dot-healthy" },
  offline: { label: "Agent offline", cls: "text-bad", dot: "dot-failed" },
  revoked: { label: "Agent revoked", cls: "text-mute", dot: "dot-paused" },
  never: { label: "Agent never seen", cls: "text-mute", dot: "dot-unknown" },
};

export const fmtMB = (mb?: number | null) => (mb == null ? "—" : mb >= 1024 ? `${(mb / 1024).toFixed(mb >= 10240 ? 0 : 1)} GB` : `${mb} MB`);
export const fmtGB = (gb?: number | null) => (gb == null ? "—" : gb >= 1000 ? `${(gb / 1000).toFixed(1)} TB` : `${Math.round(gb)} GB`);
export const fmtUptime = (s?: number | null) => { if (s == null) return "—"; const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600); return d ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`; };

/** Threshold tone for a percentage-style measure. Load is judged against the CPU count. */
export function tone(key: keyof HostMetricPoint, v: number | null | undefined, cpus?: number | null): "ok" | "warn" | "bad" | "mute" {
  if (v == null) return "mute";
  if (key === "load1") { const n = cpus || 1; return v >= n * 2 ? "bad" : v >= n ? "warn" : "ok"; }
  if (key === "io_wait_pct") return v >= 20 ? "bad" : v >= 8 ? "warn" : "ok";
  return v >= 90 ? "bad" : v >= 75 ? "warn" : "ok";
}
const TONE = { ok: "text-ok", warn: "text-warn", bad: "text-bad", mute: "text-mute" };
const STROKE = { ok: "rgb(var(--accent))", warn: "rgb(var(--warn))", bad: "rgb(var(--bad))", mute: "rgb(var(--mute))" };
const FILL = { ok: "rgb(var(--accent) / .14)", warn: "rgb(var(--warn) / .16)", bad: "rgb(var(--bad) / .16)", mute: "rgb(var(--mute) / .1)" };

export const GAUGES: { key: keyof HostMetricPoint; label: string; fmt: (v: number) => string; max?: number }[] = [
  { key: "cpu_pct", label: "CPU", fmt: (v) => `${Math.round(v)}%`, max: 100 },
  { key: "mem_pct", label: "Memory", fmt: (v) => `${Math.round(v)}%`, max: 100 },
  { key: "disk_pct", label: "Disk", fmt: (v) => `${Math.round(v)}%`, max: 100 },
  { key: "load1", label: "Load (1m)", fmt: (v) => v.toFixed(1) },
  { key: "io_wait_pct", label: "I/O wait", fmt: (v) => `${v.toFixed(v < 10 ? 1 : 0)}%`, max: 100 },
  { key: "inode_pct", label: "Inodes", fmt: (v) => `${Math.round(v)}%`, max: 100 },
];

export function Gauge({ g, latest, series, cpus, compact }: { g: (typeof GAUGES)[number]; latest: HostMetricPoint | null | undefined; series: HostMetricPoint[]; cpus?: number | null; compact?: boolean }) {
  const v = latest?.[g.key] as number | null | undefined;
  const t = tone(g.key, v, cpus);
  const data = series.map((p) => ({ ts: p.ts, v: p[g.key] as number | null }));
  const peak = data.reduce((m, p) => (p.v != null && p.v > m ? p.v : m), -Infinity);
  return (
    <div className={`rounded-md border border-line bg-bg/40 ${compact ? "px-2.5 py-2" : "px-3 py-2.5"}`} data-testid={`gauge-${g.key}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-mute">{g.label}</span>
        <span className={`font-mono ${compact ? "text-sm" : "text-base"} font-semibold tnum ${TONE[t]}`}>{v == null ? "—" : g.fmt(v)}</span>
      </div>
      {data.length > 1 ? (
        <div className={`${compact ? "h-7" : "h-9"} mt-1`} aria-label={`${g.label} over 24 hours, peak ${isFinite(peak) ? g.fmt(peak) : "—"}`} role="img">
          <ResponsiveContainer><AreaChart data={data} margin={{ top: 2, bottom: 0, left: 0, right: 0 }}>
            <Tooltip cursor={{ stroke: "rgb(var(--mute))", strokeWidth: 1 }} isAnimationActive={false} wrapperStyle={{ zIndex: 20 }}
                     content={({ active, payload }) => active && payload?.length ? <div className="rounded border border-line bg-panel px-2 py-1 font-mono text-[11px] shadow-sm">{ts(payload[0].payload.ts)} · {payload[0].value == null ? "—" : g.fmt(payload[0].value as number)}</div> : null} />
            <Area type="monotone" dataKey="v" stroke={STROKE[t]} fill={FILL[t]} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls baseValue={0} />
          </AreaChart></ResponsiveContainer>
        </div>) : <div className={`${compact ? "h-7" : "h-9"} mt-1 flex items-end text-[11px] text-mute`}>no samples yet</div>}
      {!compact && isFinite(peak) && <div className="mt-0.5 text-[11px] text-mute">24 h peak {g.fmt(peak)}{g.max && peak >= 90 && g.key !== "load1" ? " — near full" : ""}</div>}
    </div>
  );
}

export function Facts({ f, labels }: { f: Record<string, any>; labels?: Record<string, any> }) {
  const rows: [string, string][] = [
    ["OS", f.os], ["Kernel", f.kernel], ["Arch", f.arch], ["CPUs", f.cpus], ["Memory", f.mem_total_mb && fmtMB(f.mem_total_mb)], ["Disk", f.disk_total_gb && fmtGB(f.disk_total_gb)],
    ["Up", f.uptime_s && fmtUptime(f.uptime_s)], ["Load 5m / 15m", f.load5 != null && `${f.load5} / ${f.load15}`], ["Time zone", f.timezone], ["Runs as", f.virt === "vm" ? "virtual machine" : f.virt === "container" ? "container" : null],
  ].filter(([, v]) => v) as [string, string][];
  const lab = Object.entries(labels ?? {});
  if (!rows.length && !lab.length) return <p className="text-xs text-mute">No host facts yet — the agent reports them with its next heartbeat (agent 0.2.0 or newer).</p>;
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3" data-testid="host-facts">
      {rows.map(([k, v]) => <div key={k} className={k === "OS" ? "col-span-2 min-w-0" : "min-w-0"}><dt className="text-mute">{k}</dt><dd className="truncate" title={String(v)}>{String(v)}</dd></div>)}
      {lab.length > 0 && <div className="col-span-full flex flex-wrap gap-1 pt-1">{lab.map(([k, v]) => <span key={k} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px]">{k}={String(v)}</span>)}</div>}
    </dl>
  );
}

export function AgentBadge({ agent }: { agent: HostContext["agent"] }) {
  if (!agent) return <span className="inline-flex items-center gap-1.5 text-xs text-mute"><span className="dot dot-unknown" />No agent</span>;
  const st = AGENT_STATE[agent.state] ?? AGENT_STATE.never;
  return <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${st.cls}`} data-testid="agent-state"><span className={`dot ${st.dot}`} />{st.label}</span>;
}

export function HostPanel({ ctx, source, lastHost, currentJobId }: { ctx: HostContext | null | undefined; source: string; lastHost?: string | null; currentJobId?: string }) {
  if (!ctx) {
    return (
      <aside className="card bg-panel p-4 text-sm" aria-label="Host" data-testid="host-panel">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-mute">Host</div>
        {source === "ping" ? (<>
          <p>Reported by ping URL{lastHost && <>; the last run came from <span className="font-mono">{lastHost}</span></>}.</p>
          <p className="mt-2 text-mute">Install the Argus agent on that server to see its health next to the run: CPU, memory, disk and load at the moment a job fails, plus the other jobs on the same box.</p>
          <Link href="/agents" className="btn mt-3">Install an agent</Link>
        </>) : <p className="text-mute">No host information.</p>}
      </aside>);
  }
  const { server, agent, latest, series = [], jobs = [] } = ctx;
  const cpus = server.facts?.cpus as number | undefined;
  const others = jobs.filter((j) => j.id !== currentJobId);
  const hot = GAUGES.filter((g) => tone(g.key, latest?.[g.key] as number | null, cpus) === "bad");
  return (
    <aside className="card bg-panel text-sm" aria-label="Host" data-testid="host-panel">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-wide text-mute">Host</div>
            <div className="truncate font-mono text-base font-semibold">{server.hostname}</div>
          </div>
          <AgentBadge agent={agent} />
        </div>
        {agent && <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-mute">
          <span>{agent.kind} agent {agent.version && <span className="font-mono">v{agent.version}</span>}</span>
          <span>seen {ago(agent.last_seen_at ?? null)}</span>
          {agent.skew_ms != null && Math.abs(agent.skew_ms) > 5000 && <span className="text-warn">clock off by {Math.round(agent.skew_ms / 1000)} s</span>}
          <Link href={`/agents/${agent.id}`} className="text-accent hover:underline">Details</Link>
        </div>}
        {agent?.state === "offline" && <p className="mt-2 rounded bg-bad/10 px-2 py-1.5 text-xs text-bad">No heartbeat for over {Math.round(((agent.heartbeat_interval_s ?? 60) * 3) / 60)} min — runs on this host cannot be observed. Check that the server is up and the agent service is running.</p>}
        {hot.length > 0 && agent?.state !== "offline" && <p className="mt-2 rounded bg-bad/10 px-2 py-1.5 text-xs text-bad">{hot.map((g) => `${g.label} ${g.fmt(latest![g.key] as number)}`).join(" · ")} — likely to make jobs here fail or run slow.</p>}
      </div>
      <div className="grid grid-cols-2 gap-2 p-3">
        {GAUGES.slice(0, 4).map((g) => <Gauge key={g.key} g={g} latest={latest} series={series} cpus={cpus} compact />)}
      </div>
      {latest && <div className="px-4 pb-1 text-[11px] text-mute">Latest sample {ago(latest.ts)} · I/O wait {latest.io_wait_pct == null ? "—" : `${latest.io_wait_pct}%`} · inodes {latest.inode_pct == null ? "—" : `${Math.round(latest.inode_pct)}%`}</div>}
      <div className="border-t border-line px-4 py-3"><Facts f={server.facts ?? {}} labels={server.labels} /></div>
      <div className="border-t border-line px-4 py-3">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-mute">{others.length ? `Also on this host (${others.length})` : "Jobs on this host"}</div>
        {others.length === 0 ? <p className="text-xs text-mute">No other monitored jobs on this server.</p> : (
          <ul className="divide-y divide-line/60">{others.slice(0, 8).map((j) => (
            <li key={j.id}><Link href={`/jobs/${j.id}`} className="flex items-center justify-between gap-2 py-1.5 hover:underline"><span className="flex min-w-0 items-center gap-2"><span className={`dot dot-${j.status}`} /><span className="truncate">{j.name}</span></span><span className="shrink-0 text-xs text-mute">{ago(j.last_run_at ?? null)}</span></Link></li>))}
            {others.length > 8 && agent && <li className="pt-1.5 text-xs"><Link href={`/agents/${agent.id}`} className="text-accent hover:underline">All {others.length} jobs</Link></li>}
          </ul>)}
      </div>
    </aside>
  );
}
