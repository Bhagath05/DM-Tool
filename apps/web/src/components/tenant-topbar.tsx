"use client";

/**
 * TenantTopbar — composed header strip living in the (app) layout.
 *
 * Layout: [OrgSwitcher] · [BrandSwitcher] · [Environment] · [RoleBadge]
 *
 * Each child is responsible for its own state matrix (loading / empty /
 * single-option-collapse / multi-option-dropdown), so this component
 * just composes them. The dividers stay rendered even when an inner
 * component returns null, but they're visually low-contrast so an empty
 * slot looks like a small gap rather than a broken layout.
 */

import { useTenant } from "@/components/tenant-provider";
import { BrandSwitcher } from "@/components/brand-switcher";
import { OrgSwitcher } from "@/components/org-switcher";
import { RoleBadge } from "@/components/role-badge";
import { ViewModeToggle } from "@/components/view-mode-toggle";
import { cn } from "@/lib/utils";

export function TenantTopbar() {
  const { environment, status, error } = useTenant();

  // The switchers handle their own loading state; this fast-path is
  // only for the error case where rendering switchers would look weird.
  if (status === "error") {
    return (
      <span
        data-testid="tenant-topbar-error"
        className="text-sm text-destructive"
      >
        Workspace error · {error?.message ?? "unknown"}
      </span>
    );
  }

  // Founder Experience Audit (C3): the environment chip is for staff
  // debugging — never surface "PRODUCTION" / "STAGING" labels to founders.
  // Production is the only environment real users ever see, so hiding the
  // badge there strips the dev-tool vibe completely. In non-prod environments
  // (dev / staging) the audience is internal, so the badge stays useful.
  const showEnvironmentBadge = environment !== "production";

  return (
    <div className="flex items-center gap-2 text-sm" data-testid="tenant-topbar">
      <OrgSwitcher />
      <Divider />
      <BrandSwitcher />
      {showEnvironmentBadge && (
        <>
          <Divider />
          <EnvironmentBadge environment={environment} />
        </>
      )}
      <RoleBadge />
      <Divider />
      <ViewModeToggle />
    </div>
  );
}

function Divider() {
  return (
    <span aria-hidden className="text-muted-foreground/50">
      ·
    </span>
  );
}

const ENV_TONES: Record<string, string> = {
  production: "border-destructive/40 text-destructive bg-destructive/5",
  staging: "border-yellow-500/40 text-yellow-700 bg-yellow-500/5",
  development: "border-border text-muted-foreground bg-muted",
  test: "border-border text-muted-foreground bg-muted",
};

function EnvironmentBadge({ environment }: { environment: string }) {
  const tone = ENV_TONES[environment] ?? ENV_TONES.development;
  return (
    <span
      data-testid="environment-badge"
      className={cn(
        "inline-flex h-6 items-center rounded-md border px-1.5 text-xs font-medium uppercase tracking-wide",
        tone,
      )}
    >
      {environment}
    </span>
  );
}
