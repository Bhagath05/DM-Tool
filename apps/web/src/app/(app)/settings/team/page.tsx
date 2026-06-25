"use client";

/**
 * Phase 10.1 — Settings · Team.
 *
 * Members list + roles + permissions. Today the only authoritative
 * "team" data we have is the caller's own membership (from
 * `/users/me`); a real members table requires a roster endpoint
 * (Phase 10.2). Until then we show:
 *
 *   - The current user as a single-member row (honest, real data).
 *   - The role + permission catalog with explanations.
 *   - An "Invite teammates" CTA that opens a clearly-honest
 *     "Coming soon" affordance.
 *
 * No fabricated members or fake invitations.
 */

import {
  AlertCircle,
  Check,
  Mail,
  PlusCircle,
  ShieldCheck,
  UserCircle,
  Users2,
} from "lucide-react";
import { useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const ROLES: Array<{
  slug: string;
  label: string;
  description: string;
}> = [
  {
    slug: "owner",
    label: "Owner",
    description:
      "Full access to everything. Can manage billing, members, and roles.",
  },
  {
    slug: "admin",
    label: "Admin",
    description:
      "Manage members and creative work. Can't change billing or org owner.",
  },
  {
    slug: "editor",
    label: "Editor",
    description:
      "Generate content, ads, visuals; act on AI recommendations.",
  },
  {
    slug: "viewer",
    label: "Viewer",
    description:
      "Read-only access to insights, leads, and analytics.",
  },
];

export default function TeamSettingsPage() {
  const tenant = useTenant();
  const [inviteOpen, setInviteOpen] = useState(false);

  const memberCount = tenant.activeMembership ? 1 : 0;
  const role = tenant.roleSlugs?.[0] ?? "member";

  return (
    <div className="flex flex-col gap-8" data-testid="settings-team">
      <SectionHeading
        eyebrow="Settings · Team"
        heading="Members & roles"
        description="Who has access to this workspace and what they can do. Invitations and self-serve role changes arrive in the next release."
        size="lg"
        action={
          <Button
            size="sm"
            onClick={() => setInviteOpen(true)}
            data-testid="team-invite-button"
          >
            <PlusCircle className="mr-2 h-3.5 w-3.5" />
            Invite teammate
          </Button>
        }
      />

      {/* Member count summary */}
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <StatusPill tone="neutral" size="sm" icon={Users2}>
          {memberCount} active member{memberCount === 1 ? "" : "s"}
        </StatusPill>
        <StatusPill tone="muted" size="sm">
          0 pending invitations
        </StatusPill>
      </div>

      {/* Members table */}
      <article
        data-testid="team-members"
        className="card-surface overflow-hidden p-0"
      >
        <header className="flex items-center justify-between border-b border-border/60 px-5 py-3">
          <h3 className="text-card-title">Members</h3>
          <span className="text-meta">Showing {memberCount} of {memberCount}</span>
        </header>

        <div className="hidden border-b border-border/60 bg-muted/40 px-5 py-2 text-meta md:grid md:grid-cols-[1fr_1fr_140px_120px]">
          <span>Person</span>
          <span>Email</span>
          <span>Role</span>
          <span className="text-right">Status</span>
        </div>

        {tenant.user ? (
          <MemberRow
            displayName={tenant.user.display_name ?? "You"}
            email={tenant.user.email}
            role={role}
            isYou
            status="Active"
          />
        ) : (
          <EmptyState
            icon={Users2}
            title="No members yet"
            description="Sign in to see the workspace roster."
          />
        )}
      </article>

      {/* Pending invitations — honest empty */}
      <article
        data-testid="team-invitations"
        className="card-surface flex flex-col gap-4 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Pending invitations"
          description="Invitations sent but not yet accepted."
        />
        <EmptyState
          icon={Mail}
          title="No pending invitations"
          description="When you invite teammates, their email and role will show up here until they accept."
          hint="Email invitations + self-serve onboarding ship in the next release."
        />
      </article>

      {/* Roles & permissions explainer */}
      <article
        data-testid="team-roles"
        className="card-surface flex flex-col gap-5 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Roles & permissions"
          description="What each role can do. Custom roles arrive in a future release."
        />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {ROLES.map((r) => (
            <div
              key={r.slug}
              data-testid={`role-${r.slug}`}
              className={cn(
                "flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/30 p-4 transition-colors",
                r.slug === role && "border-ai-border bg-ai-soft/40",
              )}
            >
              <div className="flex items-center gap-2">
                <StatusPill
                  tone={r.slug === role ? "ai" : "neutral"}
                  size="sm"
                  dot={r.slug === role}
                  icon={ShieldCheck}
                >
                  {r.label}
                </StatusPill>
                {r.slug === role && (
                  <span className="text-xs text-muted-foreground">
                    · Your role
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {r.description}
              </p>
            </div>
          ))}
        </div>
      </article>

      {/* Invite modal (lightweight inline alert — full modal in 10.2) */}
      {inviteOpen && (
        <InviteComingSoon onClose={() => setInviteOpen(false)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function MemberRow({
  displayName,
  email,
  role,
  isYou,
  status,
}: {
  displayName: string;
  email: string;
  role: string;
  isYou: boolean;
  status: string;
}) {
  const initials = makeInitials(displayName || email);
  return (
    <div
      data-testid="member-row"
      className="grid grid-cols-1 gap-3 px-5 py-4 text-sm md:grid-cols-[1fr_1fr_140px_120px] md:items-center md:gap-4"
    >
      <div className="flex items-center gap-3 min-w-0">
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
          <span className="text-xs text-muted-foreground md:hidden">{email}</span>
        </div>
      </div>
      <span className="hidden truncate text-muted-foreground md:inline">
        {email}
      </span>
      <span>
        <StatusPill tone="ai" size="sm" icon={ShieldCheck}>
          {cap(role)}
        </StatusPill>
      </span>
      <span className="md:text-right">
        <StatusPill tone="good" size="sm" dot>
          {status}
        </StatusPill>
      </span>
    </div>
  );
}

function InviteComingSoon({ onClose }: { onClose: () => void }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="invite-modal"
      className="fixed inset-0 z-40 flex items-center justify-center bg-foreground/40 p-4 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="card-surface w-full max-w-md p-6 sm:p-7">
        <header className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ai-soft text-ai">
            <UserCircle className="h-5 w-5" />
          </span>
          <div className="flex flex-col gap-1">
            <h3 className="text-card-title">Invitations are coming soon</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Email + role invitations land in the next release. Until then,
              workspaces are single-member by design.
            </p>
          </div>
        </header>
        <ul className="mt-5 space-y-2 text-sm">
          {[
            "Email invite with role pre-selected",
            "Bulk invite via CSV",
            "Auto-expire after 7 days",
            "Audit trail for every grant",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-good" />
              <span className="text-foreground/90">{item}</span>
            </li>
          ))}
        </ul>
        <div className="mt-6 flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5" />
            We'll email you when it ships.
          </span>
          <Button size="sm" onClick={onClose}>
            Got it
          </Button>
        </div>
      </div>
    </div>
  );
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
