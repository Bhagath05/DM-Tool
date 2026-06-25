"use client";

/**
 * OrgSwitcher — dropdown of the user's memberships.
 *
 * State machine:
 *   loading            → spinner pill
 *   no-memberships     → "No workspace" label (non-interactive)
 *   ≤1 membership      → org name label (non-interactive — no point in
 *                        a dropdown of one)
 *   ≥2 memberships     → button → menu with all memberships
 *   pending switch     → chevron replaced with spinner, button disabled
 *
 * Security:
 *   The menu only renders entries from `useTenant().memberships`, which
 *   the backend authoritatively returns from /me. The user CANNOT pick
 *   an org they're not a member of via this UI. Even if they tampered
 *   with the in-flight request, the backend's `require_tenant` rejects
 *   non-member orgs with 403 — see `tenancy.dependencies._load_active_member`.
 */

import { useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";

import { useTenant } from "@/components/tenant-provider";
import {
  PopoverMenu,
  PopoverMenuItem,
  PopoverMenuLabel,
  PopoverMenuSeparator,
} from "@/components/ui/popover-menu";
import { cn } from "@/lib/utils";

export function OrgSwitcher() {
  const { status, memberships, activeOrg, switchOrg } = useTenant();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") {
    return (
      <PillLabel data-testid="org-switcher-loading">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading…
      </PillLabel>
    );
  }

  if (status === "no-memberships" || memberships.length === 0) {
    return (
      <PillLabel data-testid="org-switcher-empty">
        No workspace
      </PillLabel>
    );
  }

  // Only one membership → don't pretend there's a choice. Render the
  // name as a static label and skip the dropdown chrome. We deliberately
  // source the label from `memberships[0]` rather than `activeOrg` —
  // activeOrg could be stale (e.g. pointing at a deleted org) and the
  // user should always see the workspace they actually have access to.
  if (memberships.length === 1) {
    return (
      <PillLabel data-testid="org-switcher-single">
        {memberships[0].organization.name}
      </PillLabel>
    );
  }

  async function handleSwitch(orgId: string) {
    if (orgId === activeOrg?.id) return; // no-op
    setError(null);
    setPendingId(orgId);
    try {
      await switchOrg(orgId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  }

  const isPending = pendingId !== null;

  return (
    <div className="flex flex-col gap-1">
      <PopoverMenu
        ariaLabel="Switch organization"
        disabled={isPending}
        trigger={({ isOpen }) => (
          <span
            data-testid="org-switcher-trigger"
            data-active-id={activeOrg?.id}
            className={cn(
              "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-sm font-medium transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
              isOpen && "bg-accent",
              isPending && "cursor-progress opacity-60",
            )}
          >
            <span className="max-w-[12rem] truncate">
              {activeOrg?.name ?? "Select org"}
            </span>
            {isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </span>
        )}
      >
        <PopoverMenuLabel>Switch organization</PopoverMenuLabel>
        {memberships.map((m) => (
          <PopoverMenuItem
            key={m.organization.id}
            data-testid={`org-switcher-item-${m.organization.id}`}
            selected={m.organization.id === activeOrg?.id}
            disabled={isPending && pendingId !== m.organization.id}
            onSelect={() => void handleSwitch(m.organization.id)}
            description={
              <span>
                {m.role_slugs.join(", ") || "no role"} ·{" "}
                {m.brands.length} brand
                {m.brands.length === 1 ? "" : "s"}
              </span>
            }
          >
            {m.organization.name}
          </PopoverMenuItem>
        ))}
        {error && (
          <>
            <PopoverMenuSeparator />
            <div
              role="alert"
              data-testid="org-switcher-error"
              className="px-2 py-1.5 text-xs text-destructive"
            >
              {error}
            </div>
          </>
        )}
      </PopoverMenu>
    </div>
  );
}

function PillLabel({
  children,
  "data-testid": testId,
}: {
  children: React.ReactNode;
  "data-testid"?: string;
}) {
  return (
    <span
      data-testid={testId}
      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-dashed border-border px-2 text-sm text-muted-foreground"
    >
      {children}
    </span>
  );
}
