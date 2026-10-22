"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";

type Item = { slug: string; title: string; group: string };
type Entry = { slug: string; title: string; text: string };
type ApiGroup = { slug: string; name: string; ops: { id: string; method: string; summary: string; path?: string }[] };
const MC: Record<string, string> = { GET: "text-ok", POST: "text-accent", PUT: "text-warn", PATCH: "text-warn", DELETE: "text-bad" };

/** R59: docs sidebar with a small client-side search over titles, summaries and section headings. */
export function DocsNav({ items, groups, index, api = [] }: { items: Item[]; groups: readonly string[]; index: Entry[]; api?: ApiGroup[] }) {
  const path = usePathname();
  const inApi = path.startsWith("/docs/api");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const hits = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? index.filter((e) => (e.title + " " + e.text).toLowerCase().includes(s)).slice(0, 8) : [];
  }, [q, index]);
  const nav = (
    <nav aria-label="Documentation" className="text-sm">
      <label className="relative mb-5 block">
        <span className="sr-only">Search the docs</span>
        <Search size={14} className="absolute left-2.5 top-2.5 text-mute" aria-hidden />
        <input className="input py-1.5" style={{ paddingLeft: "2rem" }} placeholder="Search the docs" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {q && <ul className="mb-5 space-y-1" aria-label="Search results">
        {hits.length ? hits.map((h) => <li key={h.slug}><Link href={`/docs/${h.slug}`} onClick={() => { setQ(""); setOpen(false); }}
          className="block rounded px-2 py-1 hover:bg-raised"><span className="font-medium">{h.title}</span><span className="block truncate text-xs text-mute">{h.text}</span></Link></li>)
          : <li className="px-2 text-xs text-mute">No matches</li>}</ul>}
      {inApi ? <ApiNav api={api} path={path} onPick={() => setOpen(false)} /> : groups.map((g) => {
        const list = items.filter((i) => i.group === g);
        if (!list.length) return null;
        const current = list.some((i) => path === (i.slug === "api" ? "/docs/api" : `/docs/${i.slug}`));
        return (
          <details key={g} className="group mb-3" open={current || path === "/docs" || undefined}>
            <summary className="flex cursor-pointer list-none items-center justify-between rounded px-2 py-1 text-[13px] font-semibold text-ink hover:bg-raised">
              {g}<span aria-hidden className="text-mute transition-transform group-open:rotate-90">›</span></summary>
            <ul className="mt-1 space-y-0.5 border-l border-line pl-2 ml-2">{list.map((i) => {
              const href = i.slug === "api" ? "/docs/api" : `/docs/${i.slug}`;
              const active = path === href;
              return <li key={i.slug}><Link href={href} onClick={() => setOpen(false)} aria-current={active ? "page" : undefined}
                className={`block rounded px-2 py-1 ${active ? "bg-accent/10 font-medium text-accent" : "text-ink/80 hover:bg-raised hover:text-ink"}`}>{i.title}</Link></li>;
            })}</ul>
          </details>);
      })}
    </nav>
  );
  return (
    <>
      <div className="lg:hidden">
        <button className="btn mb-4 w-full justify-between" aria-expanded={open} onClick={() => setOpen(!open)}>{inApi ? "Browse the API" : "Browse the docs"}<span aria-hidden>{open ? "−" : "+"}</span></button>
        {open && <div className="mb-6 rounded-lg border border-line bg-panel p-3">{nav}</div>}
      </div>
      <div className="hidden lg:block">{nav}</div>
    </>
  );
}

function ApiNav({ api, path, onPick }: { api: ApiGroup[]; path: string; onPick: () => void }) {
  const link = (href: string, active: boolean, label: React.ReactNode) => (
    <Link href={href} onClick={onPick} aria-current={active ? "page" : undefined}
      className={`block rounded px-2 py-1 ${active ? "bg-accent/10 font-medium text-accent" : "text-ink/80 hover:bg-raised hover:text-ink"}`}>{label}</Link>);
  return (
    <div>
      <Link href="/docs" onClick={onPick} className="mb-3 block px-2 text-xs text-mute hover:text-ink">← Guides</Link>
      <ul className="mb-3 space-y-0.5">
        <li>{link("/docs/api", path === "/docs/api", "Overview")}</li>
        {[["#authentication", "Authentication"], ["#errors", "Errors"], ["#pagination", "Pagination"], ["#rate-limits", "Rate limits"]].map(([h, l]) => (
          <li key={h}>{link(`/docs/api${h}`, false, <span className="pl-2 text-[13px] text-mute">{l}</span>)}</li>))}
      </ul>
      {api.map((g) => {
        const href = `/docs/api/${g.slug}`;
        const current = path === href;
        return (
          <details key={g.slug} className="group mb-1" open={current || undefined}>
            <summary className={`flex cursor-pointer list-none items-center justify-between rounded px-2 py-1 text-[13px] font-semibold hover:bg-raised ${current ? "text-accent" : "text-ink"}`}>
              {g.name}<span aria-hidden className="text-mute transition-transform group-open:rotate-90">›</span></summary>
            <ul className="ml-2 mt-1 space-y-0.5 border-l border-line pl-2">
              {g.ops.map((o) => <li key={o.id}><Link href={`${href}#${o.id}`} onClick={onPick} className="flex items-baseline gap-2 rounded px-2 py-0.5 text-[13px] text-ink/80 hover:bg-raised hover:text-ink">
                <span className={`w-9 shrink-0 font-mono text-[10px] font-semibold ${MC[o.method] ?? ""}`}>{o.method === "DELETE" ? "DEL" : o.method}</span><span className="min-w-0">{o.summary}</span></Link></li>)}
            </ul>
          </details>);
      })}
    </div>);
}
