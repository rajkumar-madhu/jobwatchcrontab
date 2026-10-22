"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { API, AuthShell, Divider, ProviderButtons, useNext, useProviders } from "@/components/auth-shell";

/** R51 / R69 sign-in. Routes: a configured social provider, the company's SSO (found from the email
 *  domain via /auth/discover), or Keycloak's password page with the email filled in. "Single sign-on"
 *  mode is the same lookup, for people who know their company uses SSO and expect to say so. */
export default function Login() {
  const providers = useProviders();
  const next = useNext("/");
  const [mode, setMode] = useState<"email" | "sso">("email");
  const [email, setEmail] = useState("");
  const [sso, setSso] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const qs = (o: Record<string, string>) => new URLSearchParams({ next, ...o }).toString();
  useEffect(() => { if (new URLSearchParams(location.search).get("sso") === "1") setMode("sso"); }, []);

  const discover = async (): Promise<{ sso: boolean; provider?: string | null }> => {
    try {
      const r = await fetch(`${API}/auth/discover?${new URLSearchParams({ email })}`);
      return r.ok ? await r.json() : { sso: false };
    } catch { return { sso: false }; }
  };
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setMsg(null);
    const d = await discover();
    if (d.sso) { setSso(d.provider ?? "your company"); location.href = `${API}/auth/sso?${qs({ email })}`; return; }
    if (mode === "sso") {
      setBusy(false);
      setMsg(`${email.split("@")[1] ?? "This domain"} does not have single sign-on set up with JobWatch. Sign in with your email and password, or ask your administrator to connect your identity provider.`);
      return;
    }
    location.href = `${API}/auth/login?${qs({ login_hint: email })}`;
  };

  return (
    <AuthShell title={mode === "sso" ? "Sign in with single sign-on" : "Sign in to JobWatch"}
      subtitle={mode === "sso" ? "Enter your work email. We will send you to your company's identity provider." : "Welcome back."}
      footer={<>New to JobWatch? <Link href="/signup" className="font-medium text-accent hover:underline">Create an account</Link>
        <p className="mt-3 text-xs">Automating? Use an <Link href="/docs/api" className="underline">API key</Link> instead of signing in.</p></>}>
      {mode === "email" && <>
        <ProviderButtons providers={providers} href={(a) => `${API}/auth/login?${qs({ idp: a })}`} />
        {providers.length > 0 && <Divider />}
      </>}
      <form onSubmit={onSubmit} className="space-y-3">
        <label className="block text-sm font-medium" htmlFor="login-email">Work email</label>
        <input id="login-email" className="input py-2.5" type="email" required autoComplete="username" autoFocus value={email}
          onChange={(e) => { setEmail(e.target.value); setSso(null); setMsg(null); }} placeholder="you@company.com" />
        <button className="btn btn-primary w-full py-2.5" type="submit" disabled={busy}>{sso ? `Continuing to ${sso}…` : busy ? "Checking…" : "Continue"}</button>
      </form>
      {msg && <p className="mt-3 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm" role="status">{msg}</p>}
      <div className="mt-4 text-sm">
        {mode === "email"
          ? <button type="button" className="inline-flex items-center gap-2 text-accent hover:underline" onClick={() => { setMode("sso"); setMsg(null); }}><KeyRound size={14} aria-hidden />Sign in with single sign-on</button>
          : <button type="button" className="text-accent hover:underline" onClick={() => { setMode("email"); setMsg(null); }}>Use email and password instead</button>}
      </div>
      <p className="mt-4 text-xs text-mute">{mode === "sso"
        ? "Your administrator connects JobWatch to Okta, Microsoft Entra ID, Google Workspace or another SAML or OIDC provider."
        : "Companies with single sign-on go straight to it. Everyone else enters a password on the next step, where you can also reset it. If your organization requires it, you will be asked for a code from your authenticator app."}</p>
    </AuthShell>
  );
}
