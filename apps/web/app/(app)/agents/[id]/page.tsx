"use client";
/* R70 — one agent / server: state, facts, 24 h of CPU, memory, disk, load and I/O wait as small
   multiples (one measure per chart, one axis each), and the jobs discovered on it. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, mutate, type AgentDetail, type HostMetricPoint } from "@/lib/api";
import { AgentBadge, Facts, GAUGES, tone } from "@/components/host-panel";
import { ago, ts } from "@/lib/format";
import { Page, Status, Skeleton, ErrorBox } from "@/components/ui";

const STROKE = { ok: "rgb(var(--accent))", warn: "rgb(var(--warn))", bad: "rgb(var(--bad))", mute: "rgb(var(--mute))" };
const FILL = { ok: "rgb(var(--accent) / .14)", warn: "rgb(var(--warn) / .16)", bad: "rgb(var(--bad) / .16)", mute: "rgb(var(--mute) / .1)" };
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function Chart({ g, series, latest, cpus }: { g: (typeof GAUGES)[number]; series: HostMetricPoint[]; latest: HostMetricPoint | null | undefined; cpus?: number | null }) {
  const data = series.map((p) => ({ ts: p.ts, v: p[g.key] as number | null }));
  const v = latest?.[g.key] as number | null | undefined;
  const t = tone(g.key, v, cpus);
  const peak = data.reduce((m, p) => (p.v != null && p.v > m ? p.v : m), -Infinity);
  return (
    <figure className="card bg-panel p-3" data-testid={`chart-${g.key}`}>
      <figcaption className="flex items-baseline justify-between text-sm"><span className="font-medium">{g.label}</span>
        <span className="text-xs text-mute">now <b className={`font-mono ${t === "bad" ? "text-bad" : t === "warn" ? "text-warn" : "text-ink"}`}>{v == null ? "—" : g.fmt(v)}</b>{isFinite(peak) && <> · peak {g.fmt(peak)}</>}</span></figcaption>
      <div className="mt-2 h-32" role="img" aria-label={`${g.label} over the last 24 hours`}>
        {data.length > 1 ? (
          <ResponsiveContainer><AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="rgb(var(--line))" />
            <XAxis dataKey="ts" tickFormatter={hhmm} tick={{ fontSize: 10, fill: "rgb(var(--mute))" }} axisLine={false} tickLine={false} minTickGap={48} />
            <YAxis domain={g.max ? [0, g.max] : [0, "auto"]} tick={{ fontSize: 10, fill: "rgb(var(--mute))" }} axisLine={false} tickLine={false} width={38} tickFormatter={(x) => (g.max ? `${x}%` : String(x))} />
            <Tooltip isAnimationActive={false} cursor={{ stroke: "rgb(var(--mute))" }} content={({ active, payload }) => active && payload?.length
              ? <div className="rounded border border-line bg-panel px-2 py-1 font-mono text-[11px] shadow-sm">{ts(payload[0].payload.ts)} · {payload[0].value == null ? "—" : g.fmt(payload[0].value as number)}</div> : null} />
            <Area type="monotone" dataKey="v" stroke={STROKE[t]} fill={FILL[t]} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          </AreaChart></ResponsiveContainer>) : <p className="pt-10 text-center text-xs text-mute">No samples yet.</p>}
      </div>
    </figure>
  );
}

export default function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["agent", id], queryFn: () => api<AgentDetail>(`/api/v1/agents/${id}`), refetchInterval: 60_000 });
  const [rot, setRot] = useState<string | null>(null);
  const rotate = useMutation({ mutationFn: () => mutate("/api/v1/agents/{agent_id}/rotate", "post", { path: { agent_id: id } }) as Promise<{ agent_key: string }>, onSuccess: (d) => { setRot(d.agent_key); qc.invalidateQueries({ queryKey: ["agent", id] }); } });
  const revoke = useMutation({ mutationFn: () => mutate("/api/v1/agents/{agent_id}/revoke", "post", { path: { agent_id: id } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["agent", id] }) });
  if (q.error) return <Page title="Agent"><ErrorBox error={q.error} /></Page>;
  if (!q.data) return <Page title="Agent"><Skeleton /></Page>;
  const a = q.data; const ctx = a.context; const state = a.state ?? "never";
  const cpus = ctx?.server.facts?.cpus as number | undefined;
  return (
    <Page title={<span className="flex items-center gap-3"><span className="font-mono">{ctx?.server.hostname ?? a.name}</span><AgentBadge agent={ctx?.agent ?? { id: a.id, kind: a.kind, name: a.name, version: a.version, state, last_seen_at: a.last_seen_at, skew_ms: a.skew_ms, heartbeat_interval_s: a.heartbeat_interval_s }} /></span>}
          subtitle={<><Link href="/agents" className="hover:underline">Servers &amp; agents</Link> / {a.kind} agent · <span className="font-mono">{a.host_id}</span> · v{a.version ?? "?"} · heartbeat every {a.heartbeat_interval_s}s · seen {ago(a.last_seen_at ?? null)}{a.skew_ms != null && Math.abs(a.skew_ms) > 5000 && <span className="text-warn"> · clock off by {Math.round(a.skew_ms / 1000)}s</span>}</>}
          actions={!a.revoked_at && <div className="flex gap-2"><button className="btn" onClick={() => rotate.mutate()}>Rotate key</button><button className="btn text-bad" onClick={() => confirm(`Revoke ${a.name}? It stops reporting immediately.`) && revoke.mutate()}>Revoke</button></div>}>
      {rot && <div className="mb-4 rounded-md border border-warn/40 bg-warn/5 p-3 text-sm">New key (shown once): <code className="font-mono">{rot}</code> — put it in <code className="font-mono">/etc/cronsentinel/agent.json</code> and restart the agent.</div>}
      {state === "offline" && <div className="mb-4 rounded-md border border-bad/40 bg-bad/5 px-4 py-3 text-sm text-bad" role="status">No heartbeat since {ts(a.last_seen_at ?? null)} — jobs on this server cannot be observed and will show as unknown. Check that the server is up and <code className="font-mono">systemctl status cronsentinel-agent</code>.</div>}
      {!ctx ? <p className="text-sm text-mute">This agent has not bound a server yet — it reports host facts and metrics after its first discovery run.</p> : (<>
        <section className="card mb-4 bg-panel px-4 py-3"><Facts f={ctx.server.facts ?? {}} labels={ctx.server.labels} />
          {ctx.server.facts_updated_at && <p className="mt-2 text-[11px] text-mute">Facts reported {ago(ctx.server.facts_updated_at)}{ctx.latest && <> · latest sample {ago(ctx.latest.ts)}</>}</p>}</section>
        <h2 className="mb-2 text-sm font-semibold">Last 24 hours</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{GAUGES.map((g) => <Chart key={g.key} g={g} series={ctx.series ?? []} latest={ctx.latest} cpus={cpus} />)}</div>
        <h2 className="mb-2 mt-6 text-sm font-semibold">Jobs on this server ({ctx.jobs?.length ?? 0})</h2>
        {!ctx.jobs?.length ? <p className="text-sm text-mute">No jobs discovered yet. The agent reads crontabs and systemd timers within 5 minutes of installation.</p> : (
          <div className="tbl card" data-testid="agent-jobs">
            <div className="row grid-cols-[minmax(0,2fr)_140px_140px] th" style={{ minWidth: 0 }}><span>Job</span><span>Status</span><span>Last run</span></div>
            {ctx.jobs.map((j) => <Link key={j.id} href={`/jobs/${j.id}`} className="row grid-cols-[minmax(0,2fr)_140px_140px] hover:underline" style={{ minWidth: 0 }}><span className="truncate font-medium">{j.name}</span><Status s={j.status} /><span className="text-mute">{ago(j.last_run_at ?? null)}</span></Link>)}
          </div>)}
      </>)}
    </Page>
  );
}
