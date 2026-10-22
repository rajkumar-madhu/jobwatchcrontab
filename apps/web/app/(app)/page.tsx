"use client";
/* R69 — overview as an operations dashboard (Datadog-style): one time range drives every widget, the
   page refreshes itself, and every number links to the jobs behind it. All data comes from the API:
   analytics/overview, analytics/series, analytics/jobs, analytics/unusual-runs, jobs, incidents,
   platform/monitoring-gaps. */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Job, type Overview, type Incident, type MonitoringGaps } from "@/lib/api";
import { ago, dur } from "@/lib/format";
import { ErrorBox, Sev, Status } from "@/components/ui";

type Range = "24h" | "7d" | "30d";
const RANGES: Record<Range, { label: string; days: number; bucket: "hour" | "day"; prev: string }> = {
  "24h": { label: "24 hours", days: 1, bucket: "hour", prev: "previous 24 hours" },
  "7d": { label: "7 days", days: 7, bucket: "day", prev: "previous 7 days" },
  "30d": { label: "30 days", days: 30, bucket: "day", prev: "previous 30 days" },
};
type Point = { t: string; executions: number; ok: number; failed: number; missed: number; p95_ms?: number | null };
type JobStat = { id: string; name: string; status: string; tags: string[]; runs: number; failures: number; missed: number; success_rate: number | null;
  p95_ms: number | null; drift_pct: number | null; sla_target: number | null; sla_met: boolean | null };
type Unusual = { execution_id: string; job_id: string; job_name: string; status: string; finished_at: string | null; host: string | null; anomalies: { kind: string; message: string }[] };

const BAD = ["failed", "missed", "timeout"];
const STATE_ORDER: [string, string][] = [["failed", "Failed"], ["missed", "Missed"], ["timeout", "Timed out"], ["late", "Late"], ["running", "Running"],
  ["recovered", "Recovered"], ["healthy", "Healthy"], ["paused", "Paused"], ["unknown", "No data"]];
const tip = { contentStyle: { background: "rgb(var(--panel))", border: "1px solid rgb(var(--line))", borderRadius: 6, fontSize: 12 }, labelStyle: { color: "rgb(var(--ink))" } };
const pct = (n: number | null | undefined) => (n == null ? "—" : `${n >= 99.95 || n === 0 ? n.toFixed(0) : n.toFixed(n >= 99 ? 2 : 1)}%`);

function readRange(): Range {
  try { const v = localStorage.getItem("overview-range"); return v === "24h" || v === "30d" ? v : "7d"; } catch { return "7d"; }
}

/** Sum a window of points and the window before it (the series is fetched for twice the range). */
function split(points: Point[], bucket: "hour" | "day", days: number) {
  const cut = Date.now() - days * 86_400_000;
  const cur = points.filter((p) => new Date(p.t).getTime() >= cut - (bucket === "day" ? 43_200_000 : 0));
  const prev = points.filter((p) => !cur.includes(p));
  const sum = (xs: Point[]) => xs.reduce((a, p) => ({ runs: a.runs + p.executions, ok: a.ok + p.ok, failed: a.failed + p.failed, missed: a.missed + p.missed }),
    { runs: 0, ok: 0, failed: 0, missed: 0 });
  return { cur, totals: sum(cur), prevTotals: sum(prev) };
}

export default function OverviewPage() {
  const [range, setRange] = useState<Range>("7d");
  useEffect(() => setRange(readRange()), []);
  const pick = (r: Range) => { setRange(r); try { localStorage.setItem("overview-range", r); } catch { /* private mode */ } };
  const R = RANGES[range];
  const live = { refetchInterval: 30_000 };

  const ov = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/api/v1/analytics/overview"), ...live });
  const series = useQuery({ queryKey: ["series", range], queryFn: () => api<{ points: Point[]; incidents: { t: string; n: number }[] }>(`/api/v1/analytics/series?days=${R.days * 2}&bucket=${R.bucket}`), ...live });
  const stats = useQuery({ queryKey: ["analytics-jobs", range], queryFn: () => api<JobStat[]>(`/api/v1/analytics/jobs?days=${R.days}&sort=failures`), ...live });
  const jobs = useQuery({ queryKey: ["jobs", "all"], queryFn: () => api<{ items: Job[] }>("/api/v1/jobs?limit=200"), ...live });
  const inc = useQuery({ queryKey: ["incidents", "open"], queryFn: () => api<Incident[]>("/api/v1/incidents?status=open&limit=6"), ...live });
  const unusual = useQuery({ queryKey: ["unusual", range], queryFn: () => api<Unusual[]>(`/api/v1/analytics/unusual-runs?days=${Math.max(R.days, 1)}&limit=6`), ...live });
  const gaps = useQuery({ queryKey: ["platform", "gaps"], staleTime: 300_000, queryFn: () => api<MonitoringGaps>("/api/v1/platform/monitoring-gaps") });

  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 5_000); return () => clearInterval(t); }, []);
  const updated = Math.max(ov.dataUpdatedAt, series.dataUpdatedAt, jobs.dataUpdatedAt);

  const s = useMemo(() => series.data ? split(series.data.points, R.bucket, R.days) : null, [series.data, R.bucket, R.days]);
  const rate = (t?: { runs: number; ok: number }) => (t && t.runs ? (100 * t.ok) / t.runs : null);
  const chart = (s?.cur ?? []).map((p) => ({ ...p, label: new Date(p.t).toLocaleString(undefined, R.bucket === "hour" ? { hour: "2-digit", minute: "2-digit" } : { month: "short", day: "numeric" }),
    rate: p.executions ? Math.round((1000 * p.ok) / p.executions) / 10 : null }));
  const all = jobs.data?.items ?? [];
  const attention = all.filter((j) => [...BAD, "late"].includes(j.status)).sort((a, b) => BAD.indexOf(a.status) - BAD.indexOf(b.status));
  const running = all.filter((j) => j.status === "running");
  const recentGaps = (gaps.data?.gaps ?? []).filter((g) => Date.now() - new Date(g.ended_at).getTime() < 7 * 86_400_000);
  const d = ov.data;

  if (ov.error) return <div className="p-6"><ErrorBox error={ov.error} /></div>;
  const curRate = rate(s?.totals), prevRate = rate(s?.prevTotals);
  const problems = s ? s.totals.failed + s.totals.missed : null, prevProblems = s ? s.prevTotals.failed + s.prevTotals.missed : null;

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6">
      <header className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="mr-auto min-w-0">
          <h1 className="text-xl font-semibold">Overview</h1>
          <p className="text-sm text-mute">{d ? <>{d.total_jobs} jobs monitored across servers, clusters and pipelines</> : <span className="skeleton inline-block h-4 w-64" />}</p>
        </div>
        <span className="flex items-center gap-1.5 text-xs text-mute" aria-live="polite" title="Refreshes every 30 seconds">
          <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-60 motion-reduce:hidden" /><span className="relative inline-flex h-2 w-2 rounded-full bg-ok" /></span>
          Live{updated ? ` · updated ${Math.max(0, Math.round((now - updated) / 1000))} s ago` : ""}</span>
        <div className="inline-flex rounded-md border border-line bg-panel p-0.5" role="group" aria-label="Time range">
          {(Object.keys(RANGES) as Range[]).map((r) => (
            <button key={r} type="button" aria-pressed={range === r} onClick={() => pick(r)}
              className={`rounded px-3 py-1 text-sm tabular-nums ${range === r ? "bg-accent text-[rgb(var(--on-accent))]" : "text-mute hover:text-ink"}`}>{r}</button>))}
        </div>
      </header>

      {recentGaps.length > 0 && gaps.data && <div className="mb-4 rounded-md border border-warn/40 bg-warn/10 px-4 py-2 text-sm" data-testid="monitoring-gap">
        {recentGaps.length === 1
          ? <><b>Monitoring gap on our side</b> — {recentGaps[0].service} was not watching for {dur(new Date(recentGaps[0].ended_at).getTime() - new Date(recentGaps[0].started_at).getTime())} ({ago(recentGaps[0].ended_at)}).</>
          : <details>
              <summary className="cursor-pointer list-none"><b>Monitoring gap on our side</b> — {recentGaps.length} gaps in the last 7 days, worst {dur(Math.max(...recentGaps.map(gapMs)))} ({recentGaps.reduce((a, b) => (gapMs(b) > gapMs(a) ? b : a)).service}). <span className="text-mute underline">Show all</span></summary>
              <ul className="mt-2 space-y-0.5">{recentGaps.map((g) => <li key={g.id}>{g.service} was not watching for {dur(gapMs(g))} ({ago(g.ended_at)})</li>)}</ul>
            </details>}
        {" "}{gaps.data.unobserved_slots_30d} scheduled run{gaps.data.unobserved_slots_30d === 1 ? "" : "s"} could not be observed and were not alerted on.</div>}

      <section className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Key numbers">
        <Kpi label="Success rate" value={pct(curRate)} delta={curRate != null && prevRate != null ? curRate - prevRate : null} unit="pts" good="up" prev={R.prev}
          spark={chart.map((p) => p.rate)} tone={curRate != null && curRate < 95 ? "bad" : "ok"} />
        <Kpi label="Runs" value={s ? s.totals.runs.toLocaleString() : "—"} delta={s && s.prevTotals.runs ? (100 * (s.totals.runs - s.prevTotals.runs)) / s.prevTotals.runs : null} unit="%" prev={R.prev}
          spark={chart.map((p) => p.executions)} />
        <Kpi label="Failed or missed" value={problems?.toLocaleString() ?? "—"} delta={problems != null && prevProblems != null ? problems - prevProblems : null} good="down" prev={R.prev}
          spark={chart.map((p) => p.failed + p.missed)} tone={problems ? "bad" : "ok"} href="/failures" />
        <Kpi label="Jobs needing attention" value={jobs.data ? String(attention.length) : "—"} sub={attention.length ? `${attention.filter((j) => BAD.includes(j.status)).length} failing · ${attention.filter((j) => j.status === "late").length} late` : "Nothing failing or late"}
          tone={attention.length ? "bad" : "ok"} href="/jobs?status=failed" />
        <Kpi label="Time to detect" value={d?.mttd_min != null ? dur(d.mttd_min * 60_000) : "—"} sub="Average, last 30 days" />
        <Kpi label="Time to recover" value={d?.mttr_min != null ? dur(d.mttr_min * 60_000) : "—"} sub={`${inc.data?.length ?? 0} incident${inc.data?.length === 1 ? "" : "s"} open`} href="/incidents" />
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <Widget title="Run outcomes" sub={`Per ${R.bucket} · ${R.label}`} className="xl:col-span-8">
          <div className="h-56">{chart.length ? <ResponsiveContainer><BarChart data={chart} barCategoryGap={R.bucket === "hour" ? 1 : 3}>
            <CartesianGrid vertical={false} stroke="rgb(var(--line))" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "rgb(var(--mute))" }} axisLine={{ stroke: "rgb(var(--line))" }} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
            <YAxis tick={{ fontSize: 11, fill: "rgb(var(--mute))" }} axisLine={false} tickLine={false} width={34} allowDecimals={false} />
            <Tooltip cursor={{ fill: "rgb(var(--raised))" }} {...tip} />
            <Bar dataKey="ok" stackId="a" fill="rgb(var(--ok))" name="Succeeded" />
            <Bar dataKey="failed" stackId="a" fill="rgb(var(--bad))" name="Failed" />
            <Bar dataKey="missed" stackId="a" fill="rgb(var(--warn))" name="Missed" radius={[2, 2, 0, 0]} />
          </BarChart></ResponsiveContainer> : <div className="skeleton h-full" />}</div>
          <Legend items={[["Succeeded", "bg-ok"], ["Failed", "bg-bad"], ["Missed", "bg-warn"]]} />
        </Widget>

        <Widget title="Job states" sub="Right now" className="xl:col-span-4">
          {d ? <States byStatus={d.by_status} total={d.total_jobs} /> : <div className="skeleton h-40" />}
        </Widget>

        <Widget title="Job health map" sub="One square per job, coloured by state" className="xl:col-span-8" action={<Link href="/jobs" className="text-xs text-accent hover:underline">All jobs</Link>}>
          {jobs.data ? <HealthMap jobs={all} /> : <div className="skeleton h-32" />}
        </Widget>

        <Widget title="Open incidents" className="xl:col-span-4" action={<Link href="/incidents" className="text-xs text-accent hover:underline">All incidents</Link>}>
          {inc.data?.length === 0 ? <Quiet text="No open incidents." /> : <ul className="divide-y divide-line">{inc.data?.map((i) => (
            <li key={i.id}><Link href={`/incidents/${i.id}`} className="flex items-center gap-2 py-2 hover:text-accent">
              <Sev s={i.severity} /><span className="min-w-0 flex-1 truncate text-sm">{i.title}</span><span className="whitespace-nowrap text-xs text-mute">{ago(i.started_at)}</span></Link></li>))}</ul>}
        </Widget>

        <Widget title="Needs attention" sub="Failed, missed, timed out or late" className="xl:col-span-6">
          {!jobs.data ? <div className="skeleton h-32" /> : attention.length === 0 ? <Quiet text="Nothing failed, missed or late." /> : (
            <table className="w-full table-fixed text-sm"><colgroup><col /><col className="w-28" /><col className="w-28" /></colgroup>
              <thead><tr className="text-left text-xs text-mute"><th className="pb-1.5 font-normal">Job</th><th className="pb-1.5 font-normal">State</th><th className="pb-1.5 text-right font-normal">Last run</th></tr></thead>
              <tbody>{attention.slice(0, 8).map((j) => (
                <tr key={j.id} className="border-t border-line"><td className="py-1.5 pr-3"><Link href={`/jobs/${j.id}`} className="block truncate font-medium hover:text-accent">{j.name}</Link>
                  <span className="block truncate text-xs text-mute">{j.schedule_human ?? "Heartbeat"}</span></td>
                  <td className="whitespace-nowrap py-1.5 pr-3"><Status s={j.status} /></td><td className="whitespace-nowrap py-1.5 text-right text-mute">{ago(j.last_run_at)}</td></tr>))}</tbody></table>)}
        </Widget>

        <Widget title="Unusual runs" sub="Succeeded, but far outside the job's history" className="xl:col-span-6" action={<Link href="/docs/unusual-runs" className="text-xs text-accent hover:underline">How it works</Link>}>
          {!unusual.data ? <div className="skeleton h-32" /> : unusual.data.length === 0 ? <Quiet text={`No unusual runs in the last ${R.label}.`} /> : (
            <ul className="divide-y divide-line">{unusual.data.map((u) => (
              <li key={u.execution_id} className="py-2"><div className="flex items-center gap-2 text-sm"><Link href={`/jobs/${u.job_id}`} className="min-w-0 flex-1 truncate font-medium hover:text-accent">{u.job_name}</Link>
                {u.status === "failed" ? <span className="rounded bg-bad/15 px-1.5 text-[11px] text-bad">Counted as failure</span> : <span className="rounded bg-warn/15 px-1.5 text-[11px] text-warn">Unusual</span>}
                <span className="whitespace-nowrap text-xs text-mute">{ago(u.finished_at)}</span></div>
                <p className="mt-0.5 truncate text-xs text-mute" title={u.anomalies.map((a) => a.message).join("; ")}>{u.anomalies[0]?.message}</p></li>))}</ul>)}
        </Widget>

        <Widget title="Most failures" sub={R.label} className="md:col-span-1 xl:col-span-3">
          <TopList rows={(stats.data ?? []).filter((r) => r.failures + r.missed > 0).sort((a, b) => b.failures + b.missed - (a.failures + a.missed)).slice(0, 5)
            .map((r) => ({ id: r.id, name: r.name, value: r.failures + r.missed, label: String(r.failures + r.missed), tone: "bad" }))} empty="No failures in this range." loading={!stats.data} />
        </Widget>
        <Widget title="Slowest (p95)" sub={R.label} className="xl:col-span-3">
          <TopList rows={(stats.data ?? []).filter((r) => r.p95_ms).sort((a, b) => (b.p95_ms ?? 0) - (a.p95_ms ?? 0)).slice(0, 5)
            .map((r) => ({ id: r.id, name: r.name, value: r.p95_ms ?? 0, label: dur(r.p95_ms) }))} empty="No completed runs yet." loading={!stats.data} />
        </Widget>
        <Widget title="Getting slower" sub="Duration trend" className="xl:col-span-3">
          <TopList rows={(stats.data ?? []).filter((r) => (r.drift_pct ?? 0) >= 10).sort((a, b) => (b.drift_pct ?? 0) - (a.drift_pct ?? 0)).slice(0, 5)
            .map((r) => ({ id: r.id, name: r.name, value: r.drift_pct ?? 0, label: `+${Math.round(r.drift_pct ?? 0)}%`, tone: "warn" }))} empty="No job slowed by 10% or more." loading={!stats.data} />
        </Widget>
        <Widget title="SLA" sub={`Jobs with a target · ${R.label}`} className="xl:col-span-3">
          <Sla rows={(stats.data ?? []).filter((r) => r.sla_target != null)} loading={!stats.data} />
        </Widget>

        {running.length > 0 && <Widget title="Running now" className="xl:col-span-12">
          <ul className="flex flex-wrap gap-2">{running.map((j) => (
            <li key={j.id}><Link href={`/jobs/${j.id}`} className="flex items-center gap-2 rounded-md border border-line px-2.5 py-1 text-sm hover:border-accent"><span className="dot dot-running" />{j.name}<span className="text-xs text-mute">started {ago(j.last_run_at)}</span></Link></li>))}</ul>
        </Widget>}
      </div>
    </div>
  );
}

const gapMs = (g: { started_at: string; ended_at: string }) => new Date(g.ended_at).getTime() - new Date(g.started_at).getTime();

function Widget({ title, sub, action, className = "", children }: { title: string; sub?: string; action?: React.ReactNode; className?: string; children: React.ReactNode }) {
  const id = `w-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section className={`min-w-0 rounded-lg border border-line bg-panel px-4 pb-4 pt-3 ${className}`} aria-labelledby={id}>
      <div className="mb-3 flex items-baseline gap-2"><h2 id={id} className="shrink-0 whitespace-nowrap text-sm font-semibold">{title}</h2>{sub && <span className="truncate text-xs text-mute">{sub}</span>}<span className="ml-auto shrink-0">{action}</span></div>
      {children}
    </section>
  );
}

function Kpi({ label, value, sub, delta, unit = "", good = "up", prev, spark, tone, href }: { label: string; value: string; sub?: string; delta?: number | null; unit?: string;
  good?: "up" | "down"; prev?: string; spark?: (number | null)[]; tone?: "ok" | "bad"; href?: string }) {
  const better = delta == null || Math.abs(delta) < 0.05 ? null : (delta > 0) === (good === "up");
  const body = (
    <div className="flex h-full flex-col rounded-lg border border-line bg-panel px-4 py-3 transition-colors group-hover:border-accent/50">
      <div className="text-xs text-mute">{label}</div>
      <div className="mt-1 flex items-end justify-between gap-2">
        <span className={`whitespace-nowrap font-display text-[26px] font-semibold leading-none tabular-nums ${tone === "bad" ? "text-bad" : ""}`}>{value}</span>
        {spark && spark.filter((v) => v != null).length > 1 && <div className="h-8 w-20 shrink-0" aria-hidden><ResponsiveContainer><AreaChart data={spark.map((v, i) => ({ i, v }))} margin={{ top: 2, bottom: 0, left: 0, right: 0 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area type="monotone" dataKey="v" stroke={tone === "bad" ? "rgb(var(--bad))" : "rgb(var(--accent))"} fill={tone === "bad" ? "rgb(var(--bad) / .12)" : "rgb(var(--accent) / .12)"} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
        </AreaChart></ResponsiveContainer></div>}
      </div>
      <div className="mt-1.5 truncate text-xs text-mute">{delta != null && prev ? (better == null ? <>Same as {prev}</> : <>
        <span className={better ? "text-ok" : "text-bad"}>{delta > 0 ? "+" : "−"}{Math.abs(delta) >= 10 || unit === "" ? Math.round(Math.abs(delta)) : Math.abs(delta).toFixed(1)}{unit === "%" ? "%" : unit && ` ${unit}`}</span> vs {prev}</>) : sub}</div>
    </div>);
  return href ? <Link href={href} className="group block">{body}</Link> : <div className="group">{body}</div>;
}

function States({ byStatus, total }: { byStatus: Record<string, number>; total: number }) {
  const rows = STATE_ORDER.map(([k, l]) => [k, l, byStatus[k] ?? 0] as const).filter(([, , n]) => n > 0);
  const sum = rows.reduce((a, [, , n]) => a + n, 0) || 1;
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-sm bg-raised" role="img" aria-label={rows.map(([, l, n]) => `${n} ${l}`).join(", ")}>
        {rows.map(([k, , n]) => <span key={k} className={`dot-${k} h-full`} style={{ width: `${(100 * n) / sum}%`, borderRadius: 0 }} />)}</div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">{rows.map(([k, l, n]) => (
        <li key={k}><Link href={`/jobs?status=${k}`} className="flex items-center gap-2 hover:text-accent"><span className={`dot dot-${k}`} /><span className="flex-1">{l}</span>
          <span className={`tabular-nums ${BAD.includes(k) ? "font-semibold text-bad" : ""}`}>{n}</span></Link></li>))}</ul>
      <p className="mt-3 text-xs text-mute">{total} jobs in total</p>
    </div>
  );
}

function HealthMap({ jobs }: { jobs: Job[] }) {
  const [by, setBy] = useState<"kind" | "tag">("kind");
  const KIND: Record<string, string> = { cron: "Cron", systemd: "systemd timers", k8s_cronjob: "Kubernetes CronJobs", heartbeat: "Heartbeat and pipelines" };
  const groups = useMemo(() => {
    const g: Record<string, Job[]> = {};
    for (const j of jobs) {
      const key = by === "kind" ? (KIND[j.kind] ?? j.kind) : (j.tags.find((t) => !["kubernetes", "discovered", "prod", "staging"].includes(t)) ?? "untagged");
      (g[key] ??= []).push(j);
    }
    return Object.entries(g).sort((a, b) => b[1].length - a[1].length);
  }, [jobs, by]);
  if (!jobs.length) return <Quiet text="No jobs yet." />;
  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-xs text-mute"><span>Group by</span>
        {(["kind", "tag"] as const).map((k) => <button key={k} type="button" aria-pressed={by === k} onClick={() => setBy(k)}
          className={`rounded border px-2 py-0.5 ${by === k ? "border-accent text-accent" : "border-line hover:text-ink"}`}>{k === "kind" ? "Type" : "Tag"}</button>)}</div>
      <div className="space-y-3">{groups.map(([name, js]) => (
        <div key={name}><div className="mb-1 text-xs text-mute">{name} <span className="tabular-nums">· {js.length}</span></div>
          <div className="flex flex-wrap gap-1">{js.map((j) => (
            <Link key={j.id} href={`/jobs/${j.id}`} title={`${j.name} — ${j.status}`} aria-label={`${j.name}: ${j.status}`}
              className={`dot-${j.status} block h-6 w-6 rounded-[3px] ring-offset-1 ring-offset-[rgb(var(--panel))] hover:ring-2 hover:ring-accent focus-visible:ring-2 focus-visible:ring-accent`} />))}</div></div>))}</div>
      <Legend items={[["Healthy", "dot-healthy"], ["Running", "dot-running"], ["Late", "dot-late"], ["Failed or missed", "dot-failed"], ["Paused", "dot-paused"]]} />
    </div>
  );
}

function TopList({ rows, empty, loading }: { rows: { id: string; name: string; value: number; label: string; tone?: "bad" | "warn" }[]; empty: string; loading: boolean }) {
  if (loading) return <div className="skeleton h-28" />;
  if (!rows.length) return <Quiet text={empty} />;
  const max = Math.max(...rows.map((r) => r.value)) || 1;
  return <ol className="space-y-2">{rows.map((r) => (
    <li key={r.id}><Link href={`/jobs/${r.id}`} className="block text-sm hover:text-accent">
      <div className="flex items-baseline gap-2"><span className="min-w-0 flex-1 truncate">{r.name}</span><span className={`whitespace-nowrap font-mono text-xs ${r.tone === "bad" ? "text-bad" : r.tone === "warn" ? "text-warn" : ""}`}>{r.label}</span></div>
      <div className="mt-1 h-1 rounded-full bg-raised"><div className={`h-1 rounded-full ${r.tone === "bad" ? "bg-bad" : r.tone === "warn" ? "bg-warn" : "bg-accent"}`} style={{ width: `${(100 * r.value) / max}%` }} /></div></Link></li>))}</ol>;
}

function Sla({ rows, loading }: { rows: JobStat[]; loading: boolean }) {
  if (loading) return <div className="skeleton h-28" />;
  if (!rows.length) return <Quiet text="No job has an SLA target. Set one on the job." />;
  const met = rows.filter((r) => r.sla_met).length;
  return (
    <div>
      <div className="font-display text-[26px] font-semibold leading-none tabular-nums">{met}<span className="text-base text-mute">/{rows.length}</span></div>
      <div className="mt-1 text-xs text-mute">meeting their target</div>
      <ul className="mt-3 space-y-1.5">{rows.slice(0, 4).map((r) => (
        <li key={r.id}><Link href={`/jobs/${r.id}`} className="flex items-center gap-2 text-sm hover:text-accent"><span className={`h-2 w-2 shrink-0 rounded-full ${r.sla_met ? "bg-ok" : "bg-bad"}`} />
          <span className="min-w-0 flex-1 truncate">{r.name}</span><span className="whitespace-nowrap font-mono text-xs">{pct(r.success_rate)} / {r.sla_target}%</span></Link></li>))}</ul>
    </div>
  );
}

function Legend({ items }: { items: [string, string][] }) {
  return <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">{items.map(([l, c]) => <li key={l} className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-sm ${c}`} />{l}</li>)}</ul>;
}

function Quiet({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-mute">{text}</p>;
}
