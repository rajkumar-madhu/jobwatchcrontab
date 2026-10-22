"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api, mutate, type Agent } from "@/lib/api";
import { AGENT_STATE } from "@/components/host-panel";
import { ago } from "@/lib/format";
import { Page, Skeleton, ErrorBox, Empty } from "@/components/ui";


export default function AgentsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["agents"], queryFn: () => api<Agent[]>("/api/v1/agents") });
  const [tok, setTok] = useState<{ token: string; install: string | null; install_problem?: string | null } | null>(null);
  const [rot, setRot] = useState<string | null>(null);
  const mint = useMutation({ mutationFn: () => mutate("/api/v1/agents/bootstrap-token", "post", { body: {} }) as Promise<{ token: string; install: string | null; install_problem?: string | null }>, onSuccess: setTok });
  const rotate = useMutation({ mutationFn: (id: string) => mutate("/api/v1/agents/{agent_id}/rotate", "post", { path: { agent_id: id } }) as Promise<{ agent_key: string }>, onSuccess: (d) => { setRot(d.agent_key); qc.invalidateQueries({ queryKey: ["agents"] }); } });
  const revoke = useMutation({ mutationFn: (id: string) => mutate("/api/v1/agents/{agent_id}/revoke", "post", { path: { agent_id: id } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }) });
  // R72: the API decides online/offline (3× the agent's own heartbeat interval), the same rule the agent page uses
  const dotFor = (a: Agent) => (AGENT_STATE[a.state ?? "never"] ?? AGENT_STATE.never).dot;
  return (
    <Page title="Servers & agents" actions={<button className="btn btn-primary" onClick={() => mint.mutate()}>Install an agent</button>}>
      {tok && <div className="mb-4 rounded-lg border border-line bg-panel p-4 text-sm">
        <p className="mb-2">Run this on the server as root. The token works once and expires in 24 hours.</p>
        {tok.install
          ? <pre className="overflow-auto rounded-md border border-line bg-bg p-3 font-mono text-xs">{tok.install}</pre>
          : <div className="rounded-md border border-line bg-bg p-3 text-sm" role="status">
              <p>Bootstrap token: <code className="font-mono">{tok.token}</code></p>
              <p className="mt-1 text-mute">The one-line installer is not available on this server: {tok.install_problem}. Ask your administrator to set it,
                or install from the release as described in <a className="text-accent underline" href="/docs/linux-agent">the Linux agent guide</a>.</p>
            </div>}
        <p className="mt-2 text-mute">The agent discovers crontabs and systemd timers within 5 minutes. Wrap jobs with <code className="font-mono">jobwatch-run -- cmd</code> to capture exit codes and logs.</p></div>}
      {rot && <div className="mb-4 rounded-md border border-warn/40 bg-warn/5 p-3 text-sm">New key (shown once): <code className="font-mono">{rot}</code> — put it in <code className="font-mono">/etc/cronsentinel/agent.json</code> and restart the agent.</div>}
      {q.error ? <ErrorBox error={q.error} /> : q.isLoading ? <Skeleton /> : q.data!.length === 0
        ? <Empty title="No agents yet" hint="Install the Linux agent to auto-discover cron jobs and collect host metrics." action={<button className="btn btn-primary" onClick={() => mint.mutate()}>Get install command</button>} />
        : <div className="tbl card">
            <div className="row grid-cols-[minmax(0,2fr)_80px_100px_120px_70px_80px_160px] th"><span>Host</span><span>Kind</span><span>Version</span><span>Last seen</span><span>Skew</span><span>Jobs</span><span /></div>
            {q.data!.map((a) => (
              <div key={a.id} className="row grid-cols-[minmax(0,2fr)_80px_100px_120px_70px_80px_160px]">
                <div className="min-w-0"><div className="flex items-center gap-2 font-medium"><span className={`dot ${dotFor(a)}`} title={(AGENT_STATE[a.state ?? "never"] ?? AGENT_STATE.never).label} /><Link href={`/agents/${a.id}`} className="hover:underline">{a.name}</Link></div><div className="truncate font-mono text-xs text-mute">{a.host_id}</div></div>
                <span className="text-mute">{a.kind}</span><span className="font-mono text-xs">{a.version ?? "—"}</span><span className={a.state === "offline" ? "text-bad" : "text-mute"}>{ago(a.last_seen_at ?? null)}</span>
                <span className={`font-mono text-xs ${Math.abs(a.skew_ms ?? 0) > 5000 ? "text-warn" : "text-mute"}`}>{a.skew_ms ?? 0} ms</span><span>{a.jobs}</span>
                <div className="flex gap-1">{!a.revoked_at && <><button className="btn" onClick={() => rotate.mutate(a.id)}>Rotate key</button><button className="btn text-bad" onClick={() => confirm(`Revoke ${a.name}? It stops reporting immediately.`) && revoke.mutate(a.id)}>Revoke</button></>}{a.revoked_at && <span className="text-xs text-mute">revoked</span>}</div>
              </div>))}
          </div>}
    </Page>
  );
}
