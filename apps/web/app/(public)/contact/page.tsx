"use client";
/* R69: "Talk to sales". Posts to /public/contact (rate limited, stored for the team). The topic in the
   URL (?topic=security-review, ?topic=vulnerability) preselects what the visitor came for. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { SiteFooter, SiteNav } from "@/components/marketing";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const INTERESTS: [string, string][] = [["sso", "Single sign-on, SCIM and MFA"], ["self-hosted", "Self-hosted or private deployment"], ["volume", "Volume pricing"],
  ["security-review", "Security review or questionnaire"], ["migration", "Moving from another tool"], ["vulnerability", "Report a vulnerability"]];
const SIZES = ["1–20", "21–100", "101–500", "501–2,000", "2,000+"];
const WHAT: [string, string][] = [
  ["A walkthrough on your jobs", "We connect a server or cluster with you and show missed runs, failures and alert routing on real schedules."],
  ["Answers for your security team", "Identity, isolation, data handling and deployment, and your questionnaire filled in."],
  ["A deployment that fits", "Our cloud, or the whole platform inside your network with Helm."],
];

export default function Contact() {
  const [f, setF] = useState({ name: "", email: "", company: "", team_size: "", message: "", website: "" });
  const [interest, setInterest] = useState<string[]>([]);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [err, setErr] = useState("");
  useEffect(() => {
    const t = new URLSearchParams(location.search).get("topic");
    if (t && INTERESTS.some(([k]) => k === t)) setInterest([t]);
  }, []);
  const toggle = (k: string) => setInterest((xs) => (xs.includes(k) ? xs.filter((x) => x !== k) : [...xs, k]));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setState("sending"); setErr("");
    try {
      const r = await fetch(`${API}/public/contact`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...f, team_size: f.team_size || null, message: f.message || null, interest }) });
      if (r.status === 429) throw new Error("Too many requests from your network. Wait a minute and try again.");
      if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail?.[0]?.msg ?? "Check the fields and try again.");
      setState("sent");
    } catch (x) { setErr(x instanceof Error ? x.message : "Could not send. Try again."); setState("error"); }
  };

  return (
    <div className="min-h-screen">
      <SiteNav />
      <main className="mx-auto grid max-w-[1200px] gap-12 px-6 py-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="min-w-0">
          <p className="text-sm text-mute">Contact sales</p>
          <h1 className="mt-2 font-display text-[40px] font-semibold leading-tight text-balance">Talk to us about JobWatch for your organization</h1>
          <p className="mt-4 max-w-[520px] text-lg text-mute">For larger rollouts, single sign-on and directory sync, private deployments and security reviews.</p>
          <ul className="mt-10 space-y-6">{WHAT.map(([t, d]) => (
            <li key={t} className="flex gap-3"><span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/15 text-accent"><Check size={14} aria-hidden /></span>
              <div><div className="font-medium">{t}</div><div className="mt-1 text-sm text-mute">{d}</div></div></li>))}</ul>
          <p className="mt-10 text-sm text-mute">Just want to try it? <Link href="/signup" className="text-accent underline">Start free</Link>: 5 jobs, no card.</p>
        </div>
        <div className="min-w-0 rounded-lg border border-line bg-panel p-6 sm:p-8">
          {state === "sent" ? (
            <div role="status" className="py-10 text-center">
              <span className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-ok/15 text-ok"><Check size={20} aria-hidden /></span>
              <h2 className="mt-4 font-display text-xl font-semibold">Thanks, {f.name.split(" ")[0] || "we have it"}.</h2>
              <p className="mt-2 text-sm text-mute">We will reply to {f.email}. In the meantime, the <Link href="/docs/quickstart" className="underline">quick start</Link> and <Link href="/security" className="underline">security overview</Link> answer most first questions.</p>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4" aria-label="Contact sales">
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-medium">Name<input id="c-name" className="input mt-1.5" required maxLength={120} autoComplete="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
                <label className="text-sm font-medium">Work email<input id="c-email" className="input mt-1.5" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
                <label className="text-sm font-medium">Company<input id="c-company" className="input mt-1.5" required maxLength={200} autoComplete="organization" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} /></label>
                <label className="text-sm font-medium">Engineering team size<select id="c-size" className="input mt-1.5" value={f.team_size} onChange={(e) => setF({ ...f, team_size: e.target.value })}>
                  <option value="">Choose…</option>{SIZES.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
              </div>
              <fieldset><legend className="text-sm font-medium">What would you like to discuss?</legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">{INTERESTS.map(([k, l]) => (
                  <label key={k} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${interest.includes(k) ? "border-accent bg-accent/5" : "border-line"}`}>
                    <input type="checkbox" className="accent-[rgb(var(--accent))]" checked={interest.includes(k)} onChange={() => toggle(k)} />{l}</label>))}</div></fieldset>
              <label className="block text-sm font-medium">How many scheduled jobs, and where do they run?
                <textarea id="c-message" className="input mt-1.5 h-28" maxLength={4000} value={f.message} placeholder="For example: about 800 cron jobs on 60 servers, plus CronJobs in three clusters." onChange={(e) => setF({ ...f, message: e.target.value })} /></label>
              <input className="hidden" tabIndex={-1} autoComplete="off" aria-hidden name="website" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
              {state === "error" && <p className="rounded-md border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad" role="alert">{err}</p>}
              <button className="btn btn-primary w-full py-2.5" type="submit" disabled={state === "sending"}>{state === "sending" ? "Sending…" : "Send"}</button>
              <p className="text-xs text-mute">We use these details only to reply to you.</p>
            </form>)}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
