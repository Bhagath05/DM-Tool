"use client";

/**
 * Settings · Team — live roster, invitations, and role catalog.
 *
 * Backed by `GET /api/v1/team` (TeamOverview), which returns the real
 * members, pending invites, role catalog, and the `can_invite` /
 * `can_revoke_owner` affordance flags in one call. Invite creation
 * (`POST /team/invites`) returns a one-time acceptance URL the admin
 * shares with the teammate; revoke cancels a pending invite.
 *
 * No fabricated members, no fake invitation counts — every row is real
 * data scoped to the active organization. Members with `team.manage`
 * (owners + admins) see the invite/revoke affordances; everyone else
 * sees the roster read-only.
 */

import {
  AlertCircle,
  Check,
  Copy,
  Mail,
  PlusCircle,
  ShieldCheck,
  Trash2,
  UserCircle,
  Users2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonTable } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  type InvitableRole,
  type InviteRead,
  type MemberSummary,
  type RoleDescriptor,
  type TeamOverview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default function TeamSettingsPage() {
  const tenant = useTenant();
  const [data, setData] = useState<TeamOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.team.overview());
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "We couldn't load your team just now.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRevoke = useCallback(
    async (invite: InviteRead) => {
      setRevokingId(invite.id);
      try {
        await api.team.revokeInvite(invite.id);
        await load();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Could not revoke that invitation.",
        );
      } finally {
        setRevokingId(null);
      }
    },
    [load],
  );

  const canInvite = data?.can_invite ?? false;
  const myEmail = tenant.user?.email ?? null;

  return (
    <div className="flex flex-col gap-8" data-testid="settings-team">
      <SectionHeading
        eyebrow="Settings · Team"
        heading="Members & roles"
        description="Who has access to this workspace and what they can do. Invite teammates by email — they join with the role you pick."
        size="lg"
        action={
          canInvite ? (
            <Button
              size="sm"
              onClick={() => setInviteOpen(true)}
              data-testid="team-invite-button"
            >
              <PlusCircle className="mr-2 h-3.5 w-3.5" />
              Invite teammate
            </Button>
          ) : undefined
        }
      />

      {/* Summary pills — real counts from the overview */}
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <StatusPill tone="neutral" size="sm" icon={Users2}>
          {data?.member_count ?? 0} active member
          {(data?.member_count ?? 0) === 1 ? "" : "s"}
        </StatusPill>
        <StatusPill
          tone={(data?.pending_invite_count ?? 0) > 0 ? "watch" : "muted"}
          size="sm"
        >
          {data?.pending_invite_count ?? 0} pending invitation
          {(data?.pending_invite_count ?? 0) === 1 ? "" : "s"}
        </StatusPill>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-xl border border-bad-border bg-bad-soft/40 px-4 py-3 text-sm"
        >
          <span className="flex items-center gap-2 text-bad-soft-foreground">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </span>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}

      {/* Members table */}
      <article
        data-testid="team-members"
        className="card-surface overflow-hidden p-0"
      >
        <header className="flex items-center justify-between border-b border-border/60 px-5 py-3">
          <h3 className="text-card-title">Members</h3>
          {data && (
            <span className="text-meta">
              Showing {data.members.length} of {data.member_count}
            </span>
          )}
        </header>

        <div className="hidden border-b border-border/60 bg-muted/40 px-5 py-2 text-meta md:grid md:grid-cols-[1fr_1fr_140px_120px]">
          <span>Person</span>
          <span>Email</span>
          <span>Role</span>
          <span className="text-right">Joined</span>
        </div>

        {loading ? (
          <div className="p-5">
            <SkeletonTable rows={3} />
          </div>
        ) : data && data.members.length > 0 ? (
          data.members.map((m) => (
            <MemberRow
              key={m.member_id}
              member={m}
              isYou={myEmail != null && m.email === myEmail}
            />
          ))
        ) : (
          <EmptyState
            icon={Users2}
            title="No members yet"
            description="Sign in to see the workspace roster."
          />
        )}
      </article>

      {/* Pending invitations — real list */}
      <article
        data-testid="team-invitations"
        className="card-surface flex flex-col gap-4 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Pending invitations"
          description="Invitations sent but not yet accepted. Revoke one to cancel access before it's used."
        />
        {loading ? (
          <SkeletonTable rows={2} />
        ) : data && data.pending_invites.length > 0 ? (
          <ul className="flex flex-col divide-y divide-border/60">
            {data.pending_invites.map((inv) => (
              <InviteRow
                key={inv.id}
                invite={inv}
                canRevoke={canInvite}
                revoking={revokingId === inv.id}
                onRevoke={() => void handleRevoke(inv)}
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Mail}
            title="No pending invitations"
            description="When you invite teammates, their email and role show up here until they accept."
            hint={
              canInvite
                ? "Use “Invite teammate” above to send one."
                : undefined
            }
          />
        )}
      </article>

      {/* Roles & permissions explainer — real catalog */}
      <article
        data-testid="team-roles"
        className="card-surface flex flex-col gap-5 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Roles & permissions"
          description="What each role can do in this workspace."
        />
        {loading ? (
          <SkeletonTable rows={2} />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(data?.roles ?? []).map((r) => (
              <RoleCard
                key={r.slug}
                role={r}
                isMine={tenant.roleSlugs?.includes(r.slug) ?? false}
              />
            ))}
          </div>
        )}
      </article>

      {inviteOpen && data && (
        <InviteModal
          roles={data.roles.filter((r) => r.can_be_invited_as)}
          onClose={() => setInviteOpen(false)}
          onCreated={() => void load()}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function MemberRow({
  member,
  isYou,
}: {
  member: MemberSummary;
  isYou: boolean;
}) {
  const displayName = member.display_name ?? (isYou ? "You" : member.email);
  const initials = makeInitials(displayName || member.email);
  const role = member.is_owner ? "owner" : member.role_slugs[0] ?? "member";
  return (
    <div
      data-testid="member-row"
      className="grid grid-cols-1 gap-3 px-5 py-4 text-sm md:grid-cols-[1fr_1fr_140px_120px] md:items-center md:gap-4"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ai/15 text-xs font-semibold uppercase tracking-wide text-ai"
          aria-hidden
        >
          {initials}
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-medium text-foreground">
            {displayName}
            {isYou && (
              <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                (you)
              </span>
            )}
          </span>
          <span className="text-xs text-muted-foreground md:hidden">
            {member.email}
          </span>
        </div>
      </div>
      <span className="hidden truncate text-muted-foreground md:inline">
        {member.email}
      </span>
      <span>
        <StatusPill tone="ai" size="sm" icon={ShieldCheck}>
          {cap(role)}
        </StatusPill>
      </span>
      <span className="text-xs text-muted-foreground md:text-right">
        {formatDate(member.joined_at)}
      </span>
    </div>
  );
}

function InviteRow({
  invite,
  canRevoke,
  revoking,
  onRevoke,
}: {
  invite: InviteRead;
  canRevoke: boolean;
  revoking: boolean;
  onRevoke: () => void;
}) {
  const expired = invite.is_expired;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
          aria-hidden
        >
          <Mail className="h-4 w-4" />
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-medium text-foreground">
            {invite.email}
          </span>
          <span className="text-xs text-muted-foreground">
            Invited as {cap(invite.role_slug)} · {expiresLabel(invite)}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StatusPill tone={expired ? "bad" : "watch"} size="sm" dot>
          {expired ? "Expired" : "Pending"}
        </StatusPill>
        {canRevoke && (
          <Button
            size="sm"
            variant="ghost"
            onClick={onRevoke}
            disabled={revoking}
            aria-label={`Revoke invitation for ${invite.email}`}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            {revoking ? "Revoking…" : "Revoke"}
          </Button>
        )}
      </div>
    </li>
  );
}

function RoleCard({
  role,
  isMine,
}: {
  role: RoleDescriptor;
  isMine: boolean;
}) {
  return (
    <div
      data-testid={`role-${role.slug}`}
      className={cn(
        "flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/30 p-4 transition-colors",
        isMine && "border-ai-border bg-ai-soft/40",
      )}
    >
      <div className="flex items-center gap-2">
        <StatusPill
          tone={isMine ? "ai" : "neutral"}
          size="sm"
          dot={isMine}
          icon={ShieldCheck}
        >
          {role.display_name}
        </StatusPill>
        {isMine && (
          <span className="text-xs text-muted-foreground">· Your role</span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {role.description}
      </p>
      {role.capabilities.length > 0 && (
        <ul className="mt-1 space-y-1">
          {role.capabilities.map((cap_) => (
            <li
              key={cap_}
              className="flex items-start gap-2 text-xs text-foreground/80"
            >
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-good" />
              <span>{cap_}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function InviteModal({
  roles,
  onClose,
  onCreated,
}: {
  roles: RoleDescriptor[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [roleSlug, setRoleSlug] = useState<InvitableRole>(
    (roles.find((r) => r.slug === "viewer")?.slug ??
      roles[0]?.slug ??
      "viewer") as InvitableRole,
  );
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [acceptUrl, setAcceptUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const submit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = email.trim();
      if (!trimmed) {
        setFormError("Enter the teammate's email address.");
        return;
      }
      setSubmitting(true);
      setFormError(null);
      try {
        const res = await api.team.createInvite({
          email: trimmed,
          role_slug: roleSlug,
        });
        setAcceptUrl(res.accept_url);
        onCreated();
      } catch (err) {
        setFormError(
          err instanceof Error
            ? err.message
            : "Could not create that invitation.",
        );
      } finally {
        setSubmitting(false);
      }
    },
    [email, roleSlug, onCreated],
  );

  const copy = useCallback(async () => {
    if (!acceptUrl) return;
    try {
      await navigator.clipboard.writeText(acceptUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setFormError("Couldn't copy automatically — select and copy the link.");
    }
  }, [acceptUrl]);

  // Stable handler — an inline arrow here re-creates the Modal's `close`
  // callback on every keystroke, which re-runs its focus effect and steals
  // focus mid-typing (you could only enter one character).
  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) onClose();
    },
    [onClose],
  );

  return (
    <Modal
      open
      onOpenChange={handleOpenChange}
      data-testid="invite-modal"
      title={
        <span className="flex items-center gap-2">
          <UserCircle className="h-5 w-5 text-ai" />
          {acceptUrl ? "Invitation ready" : "Invite a teammate"}
        </span>
      }
    >
      <div className="w-full max-w-md">
        {acceptUrl ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm leading-relaxed text-muted-foreground">
              Share this link with{" "}
              <span className="font-medium text-foreground">{email.trim()}</span>
              . They&apos;ll sign in and join this workspace as{" "}
              <span className="font-medium text-foreground">
                {cap(roleSlug)}
              </span>
              . The link expires in 7 days.
            </p>
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={acceptUrl}
                onFocus={(e) => e.currentTarget.select()}
                className="font-mono text-xs"
                aria-label="Invitation link"
              />
              <Button size="sm" variant="outline" onClick={() => void copy()}>
                {copied ? (
                  <>
                    <Check className="mr-1.5 h-3.5 w-3.5" /> Copied
                  </>
                ) : (
                  <>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy
                  </>
                )}
              </Button>
            </div>
            <div className="mt-2 flex justify-end">
              <Button size="sm" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={(e) => void submit(e)}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="invite-email">Email address</Label>
              <Input
                id="invite-email"
                type="email"
                autoComplete="off"
                placeholder="teammate@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="invite-role">Role</Label>
              <select
                id="invite-role"
                value={roleSlug}
                onChange={(e) => setRoleSlug(e.target.value as InvitableRole)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {roles.map((r) => (
                  <option key={r.slug} value={r.slug}>
                    {r.display_name} — {r.description}
                  </option>
                ))}
              </select>
            </div>

            {formError && (
              <p
                role="alert"
                className="flex items-start gap-2 text-sm text-bad-soft-foreground"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                {formError}
              </p>
            )}

            <div className="mt-2 flex items-center justify-end gap-2">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={onClose}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={submitting}>
                {submitting ? "Creating…" : "Create invitation"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function expiresLabel(invite: InviteRead): string {
  if (invite.is_expired) return "Expired";
  const ms = new Date(invite.expires_at).getTime() - Date.now();
  if (ms <= 0) return "Expired";
  const days = Math.round(ms / 86_400_000);
  if (days >= 1) return `Expires in ${days} day${days === 1 ? "" : "s"}`;
  const hours = Math.max(1, Math.round(ms / 3_600_000));
  return `Expires in ${hours} hour${hours === 1 ? "" : "s"}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function makeInitials(s: string): string {
  const t = s.trim();
  if (!t) return "?";
  if (t.includes("@")) return t[0].toUpperCase();
  const parts = t.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function cap(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}
