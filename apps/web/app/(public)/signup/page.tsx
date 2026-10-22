"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { API, AuthShell, Divider, ProviderButtons, isFreeMail, useNext, useProviders } from "@/components/auth-shell";

type Invite = { email: string; role: string; organization: string; invited_by: string | null; expired: boolean };
const ROLE: Record<string, string> = { viewer: "a viewer", developer: "a developer", sre: "an SRE", devops: "a DevOps engineer", admin: "an admin" };

/** R51 sign-up; R69 adds invitations and work-email advice. A social provider creates the account on
 *  first use; a work email whose company has verified SSO goes to that provider; anyone else gets
 *  Keycloak's registration form with the email filled in (email verification is on in the realm).
 *  An invite link shows who invited you; the membership is created when you sign in with that email. */
export default function Signup() {
  const providers = useProviders();
  const [token, setToken] = useState<string | null>(null);
  const [invite, setInvite] = useState<Invite | null>(null);
  const [inviteError, setInviteError] = useState(false);
  const next = useNext(token ? "/" : "/onboarding");
  const [email, setEmail] = useState("");
  const qs = (o: Record<string, string>) => new URLSearchParams({ next, ...o }).toString();

  useEffect(() => {
    const t = new URLSearchParams(location.search).get("invite");
    if (!t) return;
    setToken(t);
    fetch(`${API}/auth/invite/${encodeURIComponent(t)}`).then(async (r) => {
      if (!r.ok) { setInviteError(true); return; }
      const d: Invite = await r.json(); setInvite(d); setEmail(d.email);
    }).catch(() => setInviteError(true));
  }, []);

  const free = !invite && email.includes("@") && isFreeMail(email);
  const title = invite ? `Join ${invite.organization} on JobWatch` : "Start monitoring free";
  const subtitle = invite
    ? <>{invite.invited_by ?? "An administrator"} invited <b className="text-ink">{invite.email}</b> as {ROLE[invite.role] ?? invite.role}. Create your account with this email to join.</>
    : <>5 jobs free, no card. Upgrade, or self-host the whole platform with Helm, whenever you like.</>;

  return (
    <AuthShell title={title} subtitle={subtitle}
      footer={<>Already have an account? <Link href={token ? `/login?next=/` : "/login"} className="font-medium text-accent hover:underline">Sign in</Link>
        {!invite && <p className="mt-3 text-xs">Rolling out to a large team, or need SSO, SCIM or a self-hosted deployment? <Link href="/contact" className="underline">Talk to sales</Link>.</p>}</>}>
      {inviteError && <p className="mb-4 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm" role="status">
        This invitation link has expired, was revoked, or was already used. Ask the person who invited you for a new one.</p>}
      {invite?.expired && <p className="mb-4 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm" role="status">
        This invitation has expired. Ask {invite.invited_by ?? "your administrator"} to send a new one.</p>}
      <ProviderButtons providers={providers} href={(a) => `${API}/auth/signup?${qs({ idp: a })}`} />
      {providers.length > 0 && <Divider />}
      <form onSubmit={(e) => { e.preventDefault(); location.href = `${API}/auth/signup?${qs({ email })}`; }} className="space-y-3">
        <label className="block text-sm font-medium" htmlFor="signup-email">Work email</label>
        <input id="signup-email" className="input py-2.5" type="email" required autoComplete="email" autoFocus={!invite} value={email} readOnly={!!invite}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-describedby={free ? "free-mail" : undefined} />
        {free && <p id="free-mail" className="text-xs text-warn">Use your work email if you can: teammates on your company domain can then join your organization, and single sign-on can apply.</p>}
        <button className="btn btn-primary w-full py-2.5" type="submit" disabled={!!invite?.expired}>{invite ? "Create account and join" : "Create account"}</button>
      </form>
      <ul className="mt-6 space-y-1.5 text-xs text-mute">
        {invite ? <li>Signing in with a different email will not join you to {invite.organization}.</li> : <>
          <li>Your first job can be pinging within two minutes of signing up.</li>
          <li>If your company already uses JobWatch with single sign-on, you will join its organization.</li></>}
        <li>We will ask you to confirm your email before you can sign in.</li>
      </ul>
    </AuthShell>
  );
}
