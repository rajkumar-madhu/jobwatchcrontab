"use client";
/* R69: code panel of the API reference. One language choice for the whole reference (like Stripe and
   Datadog): picking Python on one endpoint switches every endpoint, and it is remembered in this
   browser. Samples use the hosts saved in the docs host selector. */
import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";

const LANGS = [["curl", "cURL"], ["python", "Python"], ["go", "Go"]] as const;
type Lang = (typeof LANGS)[number][0];
const LKEY = "jw_api_lang";
const HKEY = "jw_docs_hosts";

function hosts(): { ingest: string; app: string } {
  try { return { ingest: "", app: "", ...JSON.parse(localStorage.getItem(HKEY) || "{}") }; } catch { return { ingest: "", app: "" }; }
}

function useHosts() {
  const [h, setH] = useState({ ingest: "", app: "" });
  useEffect(() => {
    setH(hosts());
    const on = () => setH(hosts());
    window.addEventListener("jw-hosts", on); window.addEventListener("storage", on);
    return () => { window.removeEventListener("jw-hosts", on); window.removeEventListener("storage", on); };
  }, []);
  return (s: string) => {
    let out = s;
    if (h.ingest) out = out.replaceAll("ingest.example.com", h.ingest);
    if (h.app) out = out.replaceAll("app.example.com", h.app);
    return out;
  };
}

function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLang] = useState<Lang>("curl");
  useEffect(() => {
    try { const v = localStorage.getItem(LKEY) as Lang | null; if (v && LANGS.some(([k]) => k === v)) setLang(v); } catch { /* private mode */ }
    const on = (e: Event) => setLang((e as CustomEvent<Lang>).detail);
    window.addEventListener("jw-api-lang", on);
    return () => window.removeEventListener("jw-api-lang", on);
  }, []);
  return [lang, (l: Lang) => {
    try { localStorage.setItem(LKEY, l); } catch { /* private mode */ }
    window.dispatchEvent(new CustomEvent("jw-api-lang", { detail: l }));
  }];
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-slate-300 hover:bg-white/10 hover:text-white" aria-label={label}
      onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { /* blocked */ } }}>
      {done ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}{done ? "Copied" : "Copy"}
    </button>);
}

export function ApiCode({ id, method, path, samples, responses }: {
  id: string; method: string; path: string; samples: Record<Lang, string>; responses: { status: string; example?: string }[];
}) {
  const [lang, setLang] = useLang();
  const host = useHosts();
  const withEx = responses.filter((r) => r.example);
  const [status, setStatus] = useState(withEx[0]?.status ?? "");
  const code = host(samples[lang]);
  const resp = withEx.find((r) => r.status === status);
  return (
    <div className="space-y-4">
      <div className="api-code overflow-hidden rounded-lg border border-slate-700/60 bg-[#0f1729] text-slate-100 shadow-sm">
        <div className="flex items-center justify-between gap-2 border-b border-slate-700/60 px-3 py-1.5">
          <span className="min-w-0 truncate font-mono text-[11px] text-slate-400"><b className="text-slate-200">{method}</b> {path}</span>
          <CopyButton text={code} label={`Copy ${lang} example`} />
        </div>
        <div role="tablist" aria-label="Language" className="flex gap-1 border-b border-slate-700/60 px-2">
          {LANGS.map(([k, l]) => (
            <button key={k} role="tab" type="button" id={`${id}-tab-${k}`} aria-selected={lang === k} aria-controls={`${id}-code`}
              className={`-mb-px border-b-2 px-2 py-1.5 text-xs font-medium ${lang === k ? "border-sky-400 text-white" : "border-transparent text-slate-400 hover:text-slate-200"}`}
              onClick={() => setLang(k)}>{l}</button>))}
        </div>
        <pre id={`${id}-code`} role="tabpanel" aria-labelledby={`${id}-tab-${lang}`} className="max-h-[420px] overflow-auto p-4 font-mono text-[12.5px] leading-relaxed"><code>{code}</code></pre>
      </div>
      {withEx.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-line bg-panel">
          <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-1.5">
            <span className="text-xs font-medium text-mute">Response</span>
            <div role="tablist" aria-label="Response status" className="flex flex-wrap gap-1">
              {withEx.map((r) => (
                <button key={r.status} role="tab" type="button" aria-selected={status === r.status} onClick={() => setStatus(r.status)}
                  className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${status === r.status ? (r.status.startsWith("2") ? "bg-ok/15 text-ok" : "bg-bad/10 text-bad") : "text-mute hover:text-ink"}`}>{r.status}</button>))}
            </div>
          </div>
          <pre className="max-h-[360px] overflow-auto p-4 font-mono text-[12px] leading-relaxed"><code>{resp?.example}</code></pre>
        </div>)}
    </div>
  );
}

/** Copyable snippet for the overview page (auth, errors, pagination). */
export function Snippet({ code, label }: { code: string; label?: string }) {
  const host = useHosts();
  const text = host(code);
  return (
    <div className="api-code overflow-hidden rounded-lg border border-slate-700/60 bg-[#0f1729] text-slate-100">
      <div className="flex items-center justify-between border-b border-slate-700/60 px-3 py-1"><span className="text-[11px] text-slate-400">{label ?? "Example"}</span><CopyButton text={text} label="Copy example" /></div>
      <pre className="overflow-auto p-4 font-mono text-[12.5px] leading-relaxed"><code>{text}</code></pre>
    </div>);
}
