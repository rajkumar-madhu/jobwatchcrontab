/* R69: one endpoint of the API reference (server component). Left: what it does, who may call it,
   parameters, body and responses. Right: code samples and example responses. */
import { Marked } from "marked";
import { Link2, Lock, ShieldCheck, Unlock } from "lucide-react";
import type { Field, Op } from "@/lib/api-reference";
import { ApiCode } from "@/components/api-code";

const md = new Marked({ gfm: true });
const block = (s: string) => md.parse(s, { async: false }) as string;
const inline = (s: string) => md.parseInline(s, { async: false }) as string;

export const METHOD_STYLE: Record<string, string> = {
  GET: "bg-ok/12 text-ok border-ok/30", POST: "bg-accent/10 text-accent border-accent/30", PUT: "bg-warn/12 text-warn border-warn/30",
  PATCH: "bg-warn/12 text-warn border-warn/30", DELETE: "bg-bad/10 text-bad border-bad/30",
};
const ROLE: Record<string, string> = { viewer: "Viewer", developer: "Developer", sre: "SRE", devops: "DevOps", admin: "Admin", owner: "Owner" };

export function MethodBadge({ m, small = false }: { m: string; small?: boolean }) {
  return <span className={`inline-flex shrink-0 justify-center rounded border font-mono font-semibold ${small ? "w-11 px-1 text-[10px]" : "px-1.5 py-0.5 text-[11px]"} ${METHOD_STYLE[m] ?? ""}`}>{m === "DELETE" && small ? "DEL" : m}</span>;
}

function FieldRows({ fields, depth = 0 }: { fields: Field[]; depth?: number }) {
  return (
    <ul className={depth ? "mt-2 space-y-0 border-l border-line pl-4" : "divide-y divide-line"}>
      {fields.map((f) => (
        <li key={f.name} className={depth ? "py-2" : "py-3"}>
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <code className="font-mono text-[13px] font-semibold text-ink">{f.name}</code>
            <span className="font-mono text-xs text-mute">{f.type}{f.nullable ? " | null" : ""}</span>
            {f.required ? <span className="text-[11px] font-medium text-bad">required</span> : <span className="text-[11px] text-mute">optional</span>}
          </div>
          {f.description && <div className="api-md mt-1 text-sm text-mute" dangerouslySetInnerHTML={{ __html: inline(f.description) }} />}
          {(f.enumValues || f.default || f.constraints.length > 0) && (
            <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs text-mute">
              {f.enumValues && <span>One of {f.enumValues.map((v, i) => <span key={v}>{i ? ", " : ""}<code className="api-chip">{v}</code></span>)}</span>}
              {f.default && <span>Default <code className="api-chip">{f.default}</code></span>}
              {f.constraints.map((c) => <span key={c} className="api-chip">{c}</span>)}
            </div>)}
          {f.children && f.children.length > 0 && (
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer select-none text-xs font-medium text-accent">Show {f.children.length} child attributes</summary>
              <FieldRows fields={f.children} depth={depth + 1} />
            </details>)}
        </li>))}
    </ul>);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="mt-8"><h3 className="border-b border-line pb-2 text-sm font-semibold uppercase tracking-wide text-mute">{title}</h3>{children}</div>;
}

export function Endpoint({ op }: { op: Op }) {
  const ok = op.responses.filter((r) => r.status.startsWith("2"));
  return (
    <section id={op.id} aria-labelledby={`${op.id}-h`} className="scroll-mt-24 border-t border-line py-12 first:border-t-0 first:pt-4">
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <div className="min-w-0">
          <h2 id={`${op.id}-h`} className="group flex items-center gap-2 font-display text-2xl font-semibold">
            {op.summary}
            <a href={`#${op.id}`} className="text-mute opacity-0 transition group-hover:opacity-100 focus:opacity-100" aria-label={`Link to ${op.summary}`}><Link2 size={16} aria-hidden /></a>
          </h2>
          <div className="mt-3 flex min-w-0 items-center gap-2 rounded-md border border-line bg-panel px-3 py-2">
            <MethodBadge m={op.method} />
            <code className="min-w-0 break-all font-mono text-[13px]"><span className="text-mute">{op.base.replace(/^https:\/\//, "")}</span>{op.path}</code>
          </div>
          {op.description && <div className="doc-content api-md mt-4" dangerouslySetInnerHTML={{ __html: block(op.description) }} />}
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            {op.auth === "key" && <>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1"><ShieldCheck size={13} className="text-accent" aria-hidden />Requires role <b>{ROLE[op.role ?? "viewer"]}</b> or above</span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1"><Lock size={13} className="text-mute" aria-hidden />API key, bearer token or session</span></>}
            {op.auth === "ping-token" && <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1"><Lock size={13} className="text-mute" aria-hidden />Ping token in the URL · ingest host</span>}
            {op.auth === "none" && <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1"><Unlock size={13} className="text-mute" aria-hidden />No authentication</span>}
          </div>

          {op.pathParams.length > 0 && <Section title="Path parameters"><FieldRows fields={op.pathParams} /></Section>}
          {op.queryParams.length > 0 && <Section title="Query parameters"><FieldRows fields={op.queryParams} /></Section>}
          {op.body && <Section title={op.body.isArray ? "Request body (array of objects)" : "Request body"}>
            {op.body.fields.length ? <FieldRows fields={op.body.fields} /> : <p className="py-3 text-sm text-mute">A JSON object.</p>}</Section>}
          {ok.some((r) => r.fields?.length) && <Section title="Response attributes">
            <FieldRows fields={ok.find((r) => r.fields?.length)!.fields!} /></Section>}
          <Section title="Responses">
            <ul className="divide-y divide-line">{op.responses.map((r) => (
              <li key={r.status} className="flex gap-3 py-2.5 text-sm">
                <code className={`w-10 shrink-0 font-mono font-semibold ${r.status.startsWith("2") ? "text-ok" : r.status.startsWith("4") ? "text-bad" : "text-warn"}`}>{r.status}</code>
                <span className="api-md text-mute" dangerouslySetInnerHTML={{ __html: inline(r.description) + (r.headers?.length ? ` Headers: ${r.headers.map((h) => `<code>${h}</code>`).join(", ")}.` : "") }} />
              </li>))}</ul>
          </Section>
        </div>
        <div className="min-w-0 xl:sticky xl:top-20 xl:self-start">
          <ApiCode id={op.id} method={op.method} path={op.path} samples={op.samples} responses={op.responses.map(({ status, example }) => ({ status, example }))} />
        </div>
      </div>
    </section>);
}
