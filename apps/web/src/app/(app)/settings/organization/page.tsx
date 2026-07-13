"use client";

/**
 * Phase 10.1 — Settings · Organization.
 *
 * Read-only-by-default view of the company profile. The form fields
 * mirror what's in `BusinessProfile` so what the founder sees here
 * matches what the AI Coach is reasoning from.
 *
 * "Save" is deliberately scoped to the existing /onboarding flow —
 * we don't ship a half-baked inline form. The full editor lives in
 * the onboarding wizard; this page is the canonical "what does the
 * AI know about my business" surface plus a clear path back into
 * the wizard for changes.
 */

import {
  ArrowUpRight,
  Building2,
  Edit3,
  Globe,
  Mail,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DangerZone } from "./_components/danger-zone";
import { useTenant } from "@/components/tenant-provider";
import { displayRoleName } from "@/lib/roles";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type BusinessProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; profile: BusinessProfile };

export default function OrganizationSettingsPage() {
  const tenant = useTenant();
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const profile = await api.business.get();
      if (!profile) {
        setState({ kind: "missing" });
        return;
      }
      setState({ kind: "ready", profile });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof ApiError ? err.message : "Failed to load",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-8" data-testid="settings-organization">
      <SectionHeading
        eyebrow="Settings · Organization"
        heading="Company profile"
        description="What the AI Coach knows about your business. Edits flow back through onboarding so every recommendation stays calibrated."
        size="lg"
        action={
          <Button asChild size="sm" data-testid="org-edit-button">
            <Link href={"/onboarding/profile" as never}>
              <Edit3 className="mr-2 h-3.5 w-3.5" />
              Edit profile
            </Link>
          </Button>
        }
      />

      {state.kind === "loading" && <OrgSkeleton />}
      {state.kind === "error" && (
        <EmptyState
          icon={Building2}
          title="Couldn't load your profile"
          description={state.message}
          action={
            <Button size="sm" onClick={load}>
              Try again
            </Button>
          }
        />
      )}
      {state.kind === "missing" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="Set up your business profile"
          description="The AI Coach can't personalise recommendations without a profile. Takes 2 minutes."
          action={
            <Button asChild size="sm">
              <Link href={"/onboarding/profile" as never}>Start onboarding</Link>
            </Button>
          }
          hint="You can come back here to edit any time."
        />
      )}
      {state.kind === "ready" && (
        <OrgDetail profile={state.profile} workspaceName={tenant.activeOrg?.name ?? null} />
      )}

      {/* Workspace identity — sourced from the tenant context. */}
      <WorkspaceCard tenant={tenant} />

      {/* Danger zone — owner-only reset & delete. Renders nothing for
          non-owners. */}
      <DangerZone />
    </div>
  );
}

// ---------------------------------------------------------------------
//  Profile detail
// ---------------------------------------------------------------------

function OrgDetail({
  profile,
  workspaceName,
}: {
  profile: BusinessProfile;
  workspaceName: string | null;
}) {
  return (
    <article
      data-testid="organization-profile"
      className="card-surface flex flex-col gap-6 p-6 sm:p-7"
    >
      <header className="flex items-start gap-4">
        {/* Avatar — initials. A future phase will support real logo
            upload; for now this is honest and consistent with the
            sidebar identity treatment. */}
        <span
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-ai/15 text-lg font-semibold uppercase tracking-wide text-ai"
          aria-hidden
        >
          {initials(profile.business_name)}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h3 className="text-card-title text-foreground">
            {profile.business_name}
          </h3>
          {workspaceName && workspaceName !== profile.business_name && (
            <p className="text-xs text-muted-foreground">
              Workspace · {workspaceName}
            </p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusPill tone="neutral" size="sm" icon={Building2}>
              {profile.industry || "Industry not set"}
            </StatusPill>
            {profile.business_location && (
              <StatusPill tone="neutral" size="sm">
                {profile.business_location}
              </StatusPill>
            )}
            {profile.analysis_status === "completed" && (
              <StatusPill tone="ai" size="sm" dot>
                AI brief ready
              </StatusPill>
            )}
            {profile.analysis_status === "pending" && (
              <StatusPill tone="watch" size="sm" dot>
                Analysing…
              </StatusPill>
            )}
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-x-8 gap-y-5 border-t border-border/60 pt-6 md:grid-cols-2">
        <Field
          label="Website"
          value={profile.website}
          icon={Globe}
          href={profile.website ?? undefined}
        />
        <Field label="Target audience" value={profile.target_audience} />
        <Field label="Brand tone" value={profile.brand_tone || "—"} />
        <Field label="Primary goal" value={profile.primary_goal_text} />
        <Field
          label="Monthly lead volume"
          value={
            profile.current_monthly_leads_band
              ? humanBand(profile.current_monthly_leads_band)
              : "Not set"
          }
        />
        <Field
          label="Monthly ad budget"
          value={
            profile.monthly_budget_band
              ? humanBand(profile.monthly_budget_band)
              : "Not set"
          }
        />
        <Field
          label="Preferred platforms"
          value={
            profile.preferred_platforms.length > 0
              ? profile.preferred_platforms.join(" · ")
              : "Not set"
          }
        />
        <Field
          label="Goals"
          value={profile.goals.length > 0 ? profile.goals.join(" · ") : "Not set"}
        />
      </div>
    </article>
  );
}

function Field({
  label,
  value,
  icon: Icon,
  href,
}: {
  label: string;
  value: string | null;
  icon?: typeof Globe;
  href?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-meta">{label}</span>
      {value && href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm font-medium text-foreground hover:text-ai"
        >
          {Icon && <Icon className="h-3.5 w-3.5" />}
          <span className="truncate">{value}</span>
          <ArrowUpRight className="h-3 w-3 shrink-0 opacity-50" />
        </a>
      ) : (
        <span className="text-sm leading-relaxed text-foreground/90">
          {value ?? "Not set"}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Workspace card — tenant-level info (org / brand / role)
// ---------------------------------------------------------------------

function WorkspaceCard({
  tenant,
}: {
  tenant: ReturnType<typeof useTenant>;
}) {
  if (!tenant.activeOrg) return null;
  const role = tenant.roleSlugs?.[0] ?? "member";
  return (
    <article
      data-testid="organization-workspace"
      className="card-surface flex flex-col gap-5 p-6 sm:p-7"
    >
      <SectionHeading
        eyebrow="Tenant"
        heading="Workspace"
        description="The org and brand your account is currently scoped to. Switch them from the top bar."
      />
      <div className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
        <Field label="Organization" value={tenant.activeOrg.name} />
        <Field label="Brand" value={tenant.activeBrand?.name ?? "—"} />
        <Field label="Your role" value={displayRoleName(role)} />
        <Field
          label="Member since"
          value={
            tenant.user?.created_at
              ? new Date(tenant.user.created_at).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })
              : "—"
          }
        />
        <Field
          label="Signed in as"
          value={tenant.user?.email ?? "—"}
          icon={Mail}
        />
        <Field
          label="Environment"
          value={cap(tenant.environment ?? "development")}
        />
      </div>
    </article>
  );
}

function OrgSkeleton() {
  return (
    <div className="card-surface flex flex-col gap-5 p-6">
      <div className="flex items-center gap-4">
        <Skeleton className="h-14 w-14 rounded-2xl" />
        <div className="flex flex-1 flex-col gap-2">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-5 border-t border-border/60 pt-5 md:grid-cols-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Pure helpers
// ---------------------------------------------------------------------

function initials(s: string): string {
  const t = (s ?? "").trim();
  if (!t) return "?";
  const parts = t.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function cap(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ");
}

function humanBand(s: string): string {
  // Profile bands look like "100-499". Humanise without touching the
  // underlying string format.
  return s.replace(/-/g, " – ");
}
