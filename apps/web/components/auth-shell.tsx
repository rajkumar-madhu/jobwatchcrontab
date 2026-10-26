"use client";
/* R51 / R69: shared layout for sign-in and sign-up. The form is on the left; on wide screens the right
   panel shows the product (the schedule tape) and the controls that protect an account. Every item
   in that list is a shipped feature, not a claim. Credentials are only ever entered on Keycloak;
   these pages choose the route (provider, SSO, email). */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, Check } from "lucide-react";
import { ScheduleTape } from "@/components/marketing";
import { ThemeToggle } from "@/components/theme-toggle";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "";
export type Provider = { alias: string; label: string };

export function useProviders(): Provider[] {
  const [p, setP] = useState<Provider[]>([]);
  useEffect(() => {
    fetch(`${API}/auth/providers`).then((r) => (r.ok ? r.json() : { social: [] })).then((d) => setP(d.social ?? [])).catch(() => setP([]));
  }, []);
  return p;
}

export function useNext(fallback: string): string {
  const [n, setN] = useState(fallback);
  useEffect(() => {
    const v = new URLSearchParams(location.search).get("next");
    if (v && v.startsWith("/") && !v.startsWith("//")) setN(v);   // the API re-checks this too (safe_next)
  }, []);
  return n;
}

function Mark({ alias }: { alias: string }) {
  const letter = { google: "G", github: "GH", microsoft: "M", gitlab: "GL", bitbucket: "B" }[alias] ?? alias[0]?.toUpperCase();
  return <span className="grid h-5 w-5 place-items-center rounded bg-raised text-[10px] font-semibold text-mute" aria-hidden>{letter}</span>;
}

export function ProviderButtons({ providers, href }: { providers: Provider[]; href: (alias: string) => string }) {
  if (!providers.length) return null;
  return (
    <div className="grid gap-2">
      {providers.map((p) => (
        <a key={p.alias} href={href(p.alias)} className="btn w-full justify-start gap-3 py-2.5"><Mark alias={p.alias} /><span className="flex-1 text-center">Continue with {p.label}</span><span className="w-5" /></a>))}
    </div>
  );
}

export function Divider({ label = "or" }: { label?: string }) {
  return <div className="my-5 flex items-center gap-3 text-xs text-mute"><span className="h-px flex-1 bg-line" />{label}<span className="h-px flex-1 bg-line" /></div>;
}

const CONTROLS = [
  ["Single sign-on", "SAML 2.0 or OIDC with Okta, Microsoft Entra ID, Google and others, enforced per organization"],
  ["Multi-factor sign-in", "Authenticator apps for password sign-in; organizations can require it"],
  ["Directory sync", "SCIM provisioning, with directory groups mapped to roles"],
  ["Six roles", "From viewer to owner, on every API call and page"],
  ["Audit log", "Every change recorded and streamed to your SIEM"],
  ["Tenant isolation", "Each organization's rows separated by Postgres row-level security"],
] as const;

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: React.ReactNode; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <main className="grid min-h-screen bg-bg lg:grid-cols-[minmax(440px,1fr)_minmax(0,1.1fr)]">
      <div className="flex flex-col px-5 py-6 sm:px-12 sm:py-8">
        <div className="flex items-center justify-between">
          <Link href="/welcome" className="flex items-center gap-2 font-display font-semibold">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-accent/15 text-accent"><Activity size={15} aria-hidden /></span>WeCrew JobWatch</Link>
          <ThemeToggle />
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10">
          <h1 className="font-display text-[28px] font-semibold leading-tight text-balance">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-mute">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          <div className="mt-8 text-sm text-mute">{footer}</div>
        </div>
        <nav className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-mute" aria-label="More">
          <Link href="/security" className="hover:text-ink">Security</Link>
          <Link href="/docs/sso" className="hover:text-ink">Single sign-on guide</Link>
          <Link href="/docs" className="hover:text-ink">Docs</Link>
          <Link href="/contact" className="hover:text-ink">Talk to a human</Link>
        </nav>
      </div>
      <aside className="auth-panel relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-center lg:px-12 xl:px-16" aria-label="About JobWatch">
        <h2 className="max-w-[520px] font-display text-[30px] font-semibold leading-tight text-balance">Every scheduled run, accounted for.</h2>
        <p className="mt-3 max-w-[520px] text-[15px] opacity-80">JobWatch expects each run before it is due, so a job that never starts is caught on time, not found weeks later.</p>
        <div className="mt-8 max-w-[640px] [&_figure]:shadow-[0_30px_80px_-40px_rgb(0_0_0/.6)]"><ScheduleTape callout={false} /></div>
        <ul className="mt-10 grid max-w-[640px] gap-x-8 gap-y-4 xl:grid-cols-2">{CONTROLS.map(([t, d]) => (
          <li key={t} className="flex gap-3"><Check size={16} className="mt-0.5 shrink-0 opacity-70" aria-hidden />
            <div><div className="text-sm font-medium">{t}</div><div className="text-[13px] opacity-70">{d}</div></div></li>))}</ul>
      </aside>
    </main>
  );
}

/** A free-mail address cannot match an organization's verified domain, so teammates will not join
 *  automatically and single sign-on cannot apply. Advice only: the address still works. */
const FREE_MAIL = ["gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
  "aol.com", "proton.me", "protonmail.com", "gmx.com", "yandex.com", "zoho.com", "rediffmail.com", "mail.com"];
export const isFreeMail = (email: string) => FREE_MAIL.includes(email.split("@")[1]?.trim().toLowerCase() ?? "");
