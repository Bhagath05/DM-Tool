"use client";

/**
 * Invitations panel (Phase 6.6 Slice 4, Part 3).
 *
 * Reuses the existing team-invite backend: create, list (with terminal
 * history), resend (new token + extended expiry), and revoke. Every
 * action is audited server-side. Statuses: pending / accepted / expired /
 * revoked. Invite roles use the established invitable set (admin / analyst
 * / viewer) — the same contract the backend enforces.
 */

import { Check, Copy, Mail, RefreshCw, Send, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { api, type InvitableRole, type InviteRead } from "@/lib/api";
import { displayRoleName } from "@/lib/roles";
import { cn } from "@/lib/utils";

const INVITABLE: InvitableRole[] = ["admin", "analyst", "viewer"];

export function InvitationsPanel({ canManage }: { canManage: boolean }) {
  const [invites, setInvites] = useState<InviteRead[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Invite form.
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InvitableRole>("viewer");
  const [sending, setSending] = useState(false);
  const [lastUrl, setLastUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.team.listInvites(showHistory);
      setInvites(res.invites);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load invitations.");
    }
  }, [showHistory]);

  useEffect(() => {
    void load();
  }, [load]);

  const send = async () => {
    setSending(true);
    setError(null);
    setLastUrl(null);
    try {
      const res = await api.team.createInvite({ email: email.trim(), role_slug: role });
      setLastUrl(res.accept_url);
      setEmail("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the invite.");
    } finally {
      setSending(false);
    }
  };

  const resend = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      const res = await api.team.resendInvite(id);
      setLastUrl(res.accept_url);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't resend the invite.");
    } finally {
      setBusy(null);
    }
  };

  const revoke = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      await api.team.revokeInvite(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't cancel the invite.");
    } finally {
      setBusy(null);
    }
  };

  const copyUrl = async () => {
    if (!lastUrl) return;
    await navigator.clipboard.writeText(lastUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const validEmail = /.+@.+\..+/.test(email.trim());

  return (
    <section className="flex flex-col gap-4" data-testid="invitations-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Invitations</h3>
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          className="text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          {showHistory ? "Show pending only" : "Show history"}
        </button>
      </div>

      {canManage && (
        <div className="rounded-lg border border-border p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-1">
              <Label htmlFor="invite-email">Email</Label>
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="teammate@company.com"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="invite-role">Role</Label>
              <select
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value as InvitableRole)}
                className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {INVITABLE.map((r) => (
                  <option key={r} value={r}>
                    {displayRoleName(r)}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={send} disabled={!validEmail || sending}>
              <Send className="mr-1.5 h-3.5 w-3.5" />
              {sending ? "Sending…" : "Send invite"}
            </Button>
          </div>

          {lastUrl && (
            <div className="mt-3 flex items-center gap-2 rounded-md bg-good-soft px-3 py-2">
              <Mail className="h-4 w-4 shrink-0 text-good-soft-foreground" />
              <code className="min-w-0 flex-1 truncate text-xs text-good-soft-foreground">
                {lastUrl}
              </code>
              <button
                type="button"
                onClick={copyUrl}
                className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium text-good-soft-foreground hover:bg-good/10"
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy link"}
              </button>
            </div>
          )}
        </div>
      )}

      {error && (
        <p className="rounded-md bg-bad-soft px-3 py-2 text-xs text-bad-soft-foreground">
          {error}
        </p>
      )}

      {invites === null ? (
        <p className="text-sm text-muted-foreground">Loading invitations…</p>
      ) : invites.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {showHistory ? "No invitations yet." : "No pending invitations."}
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {invites.map((inv) => {
            const status = inv.is_expired && inv.status === "pending" ? "expired" : inv.status;
            return (
              <li
                key={inv.id}
                className="flex flex-wrap items-center gap-3 px-3 py-2.5"
                data-testid="invite-row"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{inv.email}</p>
                  <p className="text-xs text-muted-foreground">
                    {displayRoleName(inv.role_slug)} · expires{" "}
                    {new Date(inv.expires_at).toLocaleDateString()}
                  </p>
                </div>
                <StatusPill tone={inviteTone(status)} size="sm">
                  {status}
                </StatusPill>
                {canManage && inv.status === "pending" && !inv.is_expired && (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={busy === inv.id}
                      onClick={() => resend(inv.id)}
                      aria-label={`Resend invite to ${inv.email}`}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                    >
                      <RefreshCw className={cn("h-4 w-4", busy === inv.id && "animate-spin")} />
                    </button>
                    <button
                      type="button"
                      disabled={busy === inv.id}
                      onClick={() => revoke(inv.id)}
                      aria-label={`Cancel invite to ${inv.email}`}
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-bad-soft hover:text-bad-soft-foreground disabled:opacity-50"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function inviteTone(status: string): PillTone {
  switch (status) {
    case "pending":
      return "watch";
    case "accepted":
      return "good";
    case "revoked":
      return "muted";
    case "expired":
      return "bad";
    default:
      return "neutral";
  }
}
