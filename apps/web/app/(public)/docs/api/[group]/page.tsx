import Link from "next/link";
import { notFound } from "next/navigation";
import { apiGroup, apiReference } from "@/lib/api-reference";
import { Endpoint, MethodBadge } from "@/components/api-endpoint";

export const dynamic = "force-static";
export const dynamicParams = false;

export function generateStaticParams() {
  return apiReference().map((g) => ({ group: g.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ group: string }> }) {
  const g = apiGroup((await params).group);
  return { title: g ? `${g.name} · API reference · Argus docs` : "API reference", description: g?.description };
}

export default async function ApiGroupPage({ params }: { params: Promise<{ group: string }> }) {
  const groups = apiReference();
  const g = apiGroup((await params).group);
  if (!g) notFound();
  const idx = groups.findIndex((x) => x.slug === g.slug);
  const prev = groups[idx - 1], next = groups[idx + 1];
  return (
    <div className="min-w-0">
      <nav aria-label="Breadcrumb" className="text-sm text-mute">
        <ol className="flex flex-wrap items-center gap-1.5">
          <li><Link href="/docs" className="hover:text-ink">Docs</Link></li><li aria-hidden>/</li>
          <li><Link href="/docs/api" className="hover:text-ink">API reference</Link></li><li aria-hidden>/</li>
          <li aria-current="page" className="text-ink">{g.name}</li>
        </ol>
      </nav>
      <h1 className="mt-2 font-display text-4xl font-semibold">{g.name}</h1>
      <p className="mt-3 max-w-[720px] text-[17px] text-mute">{g.description}</p>
      <div className="mt-6 overflow-hidden rounded-lg border border-line">
        <div className="border-b border-line bg-panel px-4 py-2 text-xs font-semibold uppercase tracking-wide text-mute">Endpoints</div>
        <ul className="divide-y divide-line">{g.ops.map((o) => (
          <li key={o.id}><a href={`#${o.id}`} className="flex items-center gap-3 px-4 py-2 text-sm hover:bg-raised">
            <MethodBadge m={o.method} small /><code className="min-w-0 flex-1 truncate font-mono text-[13px]">{o.path}</code>
            <span className="hidden text-mute sm:inline">{o.summary}</span></a></li>))}</ul>
      </div>
      <div className="mt-6">{g.ops.map((o) => <Endpoint key={o.id} op={o} />)}</div>
      <nav className="mt-6 grid gap-3 border-t border-line pt-6 sm:grid-cols-2" aria-label="Previous and next">
        {prev ? <Link href={`/docs/api/${prev.slug}`} className="card p-3 text-sm hover:border-accent/60"><span className="text-xs text-mute">Previous</span><span className="block font-medium">{prev.name}</span></Link> : <Link href="/docs/api" className="card p-3 text-sm hover:border-accent/60"><span className="text-xs text-mute">Previous</span><span className="block font-medium">Overview</span></Link>}
        {next && <Link href={`/docs/api/${next.slug}`} className="card p-3 text-right text-sm hover:border-accent/60"><span className="text-xs text-mute">Next</span><span className="block font-medium">{next.name}</span></Link>}
      </nav>
    </div>
  );
}
