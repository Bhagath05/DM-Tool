"use client";

/**
 * RequireTenant — page-content gate.
 *
 * Renders children ONLY when a complete tenant context is available
 * (status='ready' AND activeOrg !== null AND activeBrand !== null).
 *
 * For every other state, renders a focused full-area message so the
 * user never sees a blank page or a half-loaded UI calling brand-scoped
 * APIs with no brand_id:
 *
 *   status='loading'         → spinner card ("Loading workspace…")
 *   status='error'           → error card with refresh action
 *   status='no-memberships'  → "Set up your workspace" with link to wizard
 *   status='ready' but
 *     no activeBrand         → "Create your first brand" with link to wizard
 *
 * Note on architecture:
 *   The TenantProvider's `enforceSuggestedRoute` is ALSO redirecting
 *   the user to /onboarding in the no-memberships case. This
 *   component covers the window BETWEEN that decision and the actual
 *   navigation (which is async) — during that window, we render the
 *   "missing org" card instead of letting the dashboard flash through.
 *
 *   The component is intentionally PRESENTATIONAL — it doesn't trigger
 *   navigation itself. That stays in the provider so there's one
 *   authoritative source of "where should this user be".
 */

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useTenant } from "@/components/tenant-provider";

export function RequireTenant({ children }: { children: React.ReactNode }) {
  const { status, error, activeOrg, activeBrand, refresh } = useTenant();

  if (status === "loading") {
    return (
      <CenteredCard testId="require-tenant-loading">
        <Spinner />
        <p className="text-sm text-muted-foreground">Loading workspace…</p>
      </CenteredCard>
    );
  }

  if (status === "error") {
    return (
      <CenteredCard testId="require-tenant-error">
        <h2 className="text-lg font-semibold">Couldn&apos;t load your workspace</h2>
        <p className="text-sm text-muted-foreground">
          {error?.message ?? "Unknown error"}
        </p>
        <Button onClick={() => void refresh()} data-testid="require-tenant-retry">
          Retry
        </Button>
      </CenteredCard>
    );
  }

  if (status === "no-memberships" || !activeOrg) {
    return (
      <CenteredCard testId="require-tenant-missing-org">
        <h2 className="text-lg font-semibold">Set up your workspace</h2>
        <p className="text-sm text-muted-foreground">
          You don&apos;t have an organization yet. Create one to start using
          the product.
        </p>
        <Button asChild>
          <Link href={"/onboarding" as never}>Create workspace</Link>
        </Button>
      </CenteredCard>
    );
  }

  if (!activeBrand) {
    return (
      <CenteredCard testId="require-tenant-missing-brand">
        <h2 className="text-lg font-semibold">Create your first brand</h2>
        <p className="text-sm text-muted-foreground">
          Your organization <span className="font-medium">{activeOrg.name}</span>{" "}
          doesn&apos;t have an active brand. Brands own all campaigns,
          content, and analytics — pick one to continue.
        </p>
        <Button asChild>
          <Link href={"/onboarding" as never}>Add a brand</Link>
        </Button>
      </CenteredCard>
    );
  }

  // Ready. Render the actual page.
  return <>{children}</>;
}

// ---------------------------------------------------------------------
//  Presentational helpers
// ---------------------------------------------------------------------

function CenteredCard({
  children,
  testId,
}: {
  children: React.ReactNode;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className="flex min-h-[60vh] items-center justify-center p-6"
    >
      <div className="flex max-w-md flex-col items-center gap-4 rounded-lg border border-border bg-card p-6 text-center">
        {children}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <div
      aria-hidden
      className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary"
    />
  );
}
