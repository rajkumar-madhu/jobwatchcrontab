"use client";
/* R69: people and sign-in policy. Members with their roles (directory-managed members are marked:
   their roles follow SCIM groups), invitations by email with a link shown once, and "require
   multi-factor sign-in" (owners only; needs the server's Keycloak admin client). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, mutate } from "@/lib/api";
import { ago } from "@/lib/format";
import { ErrorBox } from "@/components/ui";

type Member = { user_id: string; email: string; name: string | null; role: string; joined_at: string; managed_by_directory: boolean };
type Invite = { id: string; email: string; role: string; created_at: string; expires_at: string; status: string; invite_url?: string | null };
type Security = { require_mfa: boolean; mfa_checkable: boolean; sso_enforced: boolean };

const ROLES = ["viewer", "developer", "sre", "devops", "admin"] as const;
const ROLE_LABEL: Record<string, string> = { owner: "Owner", admin: "Admin", devops: "DevOps", sre: "SRE", developer: "Developer", viewer: "Viewer" };
const RANK: Record<string, number> = { viewer: 0, developer: 1, sre: 2, devops: 3, admin: 4, owner: 5 };

export function TeamSettings({ role }: { role?: string }) {
  const qc = useQueryClient();
  const isAdmin = (RANK[role ?? ""] ?? 0) >= RANK.admin;
  const members = useQuery({ queryKey: ["members"], queryFn: () => api<Member[]>("/api/v1/org/members") });
  const invites = useQuery({ queryKey: ["invites"], queryFn: () => api<Invite[]>("/api/v1/org/invites"), enabled: isAdmin });
  const [form, setForm] = useState({ email: "", role: "developer" });
  const [created, setCreated] = useState<Invite | null>(null);
  const [copied, setCopied] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["members"] }); qc.invalidateQueries({ queryKey: ["invites"] }); };
  const invite = useMutation({ mutationFn: () => mutate("/api/v1/org/invites" as any, "post", { body: form as any }) as Promise<Invite>,
    onSuccess: (r) => { setCreated(r); setCopied(false); setForm({ email: "", role: form.role }); refresh(); } });
  const revoke = useMutation({ mutationFn: (id: string) => mutate("/api/v1/org/invites/{invite_id}" as any, "delete", { path: { invite_id: id } } as any), onSuccess: refresh });
  const setRole = useMutation({ mutationFn: ({ id, r }: { id: string; r: string }) => mutate("/api/v1/org/members/{user_id}" as any, "patch", { path: { user_id: id }, body: { role: r } } as any), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => mutate("/api/v1/org/members/{user_id}" as any, "delete", { path: { user_id: id } } as any), onSuccess: refresh });
  const [confirm, setConfirm] = useState<string | null>(null);
  const pending = (invites.data ?? []).filter((i) => i.status === "pending");
  const canEdit = (m: Member) => isAdmin && m.role !== "owner" && (role === "owner" || m.role !== "admin");

  const copy = async (text: string) => { try { await navigator.clipboard.writeText(text); setCopied(true); } catch { setCopied(false); } };

  return (
    <div className="space-y-5">
      {isAdmin && <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }} aria-label="Invite a teammate">
        <label className="min-w-0 flex-1 basis-60 text-sm">Invite by email
          <input id="invite-email" className="input mt-1" type="email" required value={form.email} placeholder="name@company.com" onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label className="text-sm">Role
          <select id="invite-role" className="input mt-1 w-40" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.filter((r) => r !== "admin" || role === "owner" || role === "admin").map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></label>
        <button className="btn btn-primary" type="submit" disabled={invite.isPending || !form.email}>Send invite</button>
      </form>}
      {invite.error && <ErrorBox error={invite.error} />}
      {created?.invite_url && <div className="rounded-md border border-accent/50 bg-accent/[.07] px-4 py-3 text-sm" role="status">
        <div className="font-medium">Invitation created for {created.email}</div>
        <p className="mt-1 text-mute">Send them this link. It works once, expires in 7 days, and is not shown again. They join when they sign up or sign in with {created.email}.</p>
        <div className="mt-2 flex flex-wrap items-center gap-2"><code className="min-w-0 flex-1 break-all rounded border border-line bg-bg px-2 py-1 font-mono text-xs">{created.invite_url}</code>
          <button type="button" className="btn" onClick={() => copy(created.invite_url!)}>{copied ? "Copied" : "Copy link"}</button></div>
      </div>}

      <div className="overflow-x-auto rounded-md border border-line">
        <table className="w-full min-w-[640px] text-sm">
          <thead><tr className="text-left text-xs text-mute"><th className="px-3 py-2 font-normal">Member</th><th className="px-3 py-2 font-normal">Role</th><th className="px-3 py-2 font-normal">Joined</th><th className="px-3 py-2" /></tr></thead>
          <tbody>
            {members.isLoading && <tr><td colSpan={4} className="px-3 py-3"><div className="skeleton h-5" /></td></tr>}
            {members.data?.map((m) => (
              <tr key={m.user_id} className="border-t border-line">
                <td className="px-3 py-2"><div className="font-medium">{m.name ?? m.email}</div><div className="text-xs text-mute">{m.email}</div></td>
                <td className="px-3 py-2">{canEdit(m) && !m.managed_by_directory
                  ? <select aria-label={`Role for ${m.email}`} className="input w-36 py-1" value={m.role} disabled={setRole.isPending} onChange={(e) => setRole.mutate({ id: m.user_id, r: e.target.value })}>
                      {ROLES.filter((r) => r !== "admin" || role === "owner" || m.role === "admin").map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
                  : <span>{ROLE_LABEL[m.role] ?? m.role}</span>}
                  {m.managed_by_directory && <span className="ml-2 rounded bg-raised px-1.5 py-0.5 text-[11px] text-mute" title="Provisioned over SCIM: the role follows directory groups">Directory</span>}</td>
                <td className="whitespace-nowrap px-3 py-2 text-mute">{ago(m.joined_at)}</td>
                <td className="px-3 py-2 text-right">{canEdit(m) && (confirm === m.user_id
                  ? <span className="inline-flex items-center gap-2 text-xs">Remove {m.email}?<button type="button" className="btn py-1 text-bad" onClick={() => { remove.mutate(m.user_id); setConfirm(null); }}>Remove</button><button type="button" className="btn py-1" onClick={() => setConfirm(null)}>Cancel</button></span>
                  : <button type="button" className="text-xs text-mute hover:text-bad" onClick={() => setConfirm(m.user_id)}>Remove</button>)}</td>
              </tr>))}
            {isAdmin && pending.map((i) => (
              <tr key={i.id} className="border-t border-line bg-raised/40">
                <td className="px-3 py-2"><div className="font-medium">{i.email}</div><div className="text-xs text-mute">Invited {ago(i.created_at)} · expires {new Date(i.expires_at).toLocaleDateString()}</div></td>
                <td className="px-3 py-2">{ROLE_LABEL[i.role] ?? i.role}<span className="ml-2 rounded bg-warn/15 px-1.5 py-0.5 text-[11px] text-warn">Invited</span></td>
                <td className="px-3 py-2 text-mute">—</td>
                <td className="px-3 py-2 text-right"><button type="button" className="text-xs text-mute hover:text-bad" onClick={() => revoke.mutate(i.id)}>Revoke</button></td>
              </tr>))}
          </tbody>
        </table>
      </div>
      {(setRole.error || remove.error || revoke.error) && <ErrorBox error={setRole.error ?? remove.error ?? revoke.error} />}
      <p className="text-xs text-mute">Owners cannot be removed or demoted here. Members marked Directory are provisioned by your identity provider; change their role through directory groups.</p>
    </div>
  );
}

export function SecuritySettings({ role }: { role?: string }) {
  const qc = useQueryClient();
  const isOwner = role === "owner";
  const sec = useQuery({ queryKey: ["security"], queryFn: () => api<Security>("/api/v1/org/security"), enabled: (RANK[role ?? ""] ?? 0) >= RANK.admin });
  const save = useMutation({ mutationFn: (v: boolean) => mutate("/api/v1/org/security" as any, "put", { body: { require_mfa: v } } as any) as Promise<Security>,
    onSuccess: (r) => qc.setQueryData(["security"], r) });
  if ((RANK[role ?? ""] ?? 0) < RANK.admin) return <p className="text-sm text-mute">Only admins and owners can see sign-in policy.</p>;
  const d = sec.data;
  return (
    <div className="space-y-3">
      <label className={`flex items-start gap-3 rounded-md border border-line px-4 py-3 ${isOwner ? "cursor-pointer" : ""}`}>
        <input id="require-mfa" type="checkbox" className="mt-1 h-4 w-4 accent-[rgb(var(--accent))]" checked={!!d?.require_mfa} disabled={!isOwner || !d || save.isPending || (!d.mfa_checkable && !d.require_mfa)}
          onChange={(e) => save.mutate(e.target.checked)} />
        <span><span className="block text-sm font-medium">Require multi-factor sign-in</span>
          <span className="block text-sm text-mute">Members who sign in with a password must also enter a code from an authenticator app. The first time, they are asked to set one up.
            Sign-in with Google or GitHub is then refused for this organization; single sign-on members get multi-factor authentication from your identity provider.</span>
          {!isOwner && <span className="mt-1 block text-xs text-mute">Only owners can change this.</span>}
          {d && !d.mfa_checkable && <span className="mt-1 block text-xs text-warn">This server cannot check second factors yet: its Keycloak admin client is not configured.</span>}</span>
      </label>
      {d?.sso_enforced && <p className="text-sm text-mute">Single sign-on is enforced: members other than owners sign in through your identity provider.</p>}
      {save.error && <ErrorBox error={save.error} />}
    </div>
  );
}
