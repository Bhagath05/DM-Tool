"use client";

/**
 * BrandSwitcher — dropdown of brands in the active org.
 *
 * State matrix mirrors OrgSwitcher (loading / empty / single / multi /
 * pending / error). See org-switcher.tsx for the security rationale —
 * the brand list is sourced from `useTenant().activeMembership.brands`,
 * which the backend returns from /me; user can't fabricate brand IDs
 * because the backend re-validates `brand.organization_id === active_org`
 * on every request.
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

export function BrandSwitcher() {
  const { status, activeMembership, activeBrand, switchBrand } = useTenant();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (status === "loading") {
    return (
      <PillLabel data-testid="brand-switcher-loading">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading…
      </PillLabel>
    );
  }

  if (status === "no-memberships" || !activeMembership) {
    return null; // OrgSwitcher already tells the user there's no workspace.
  }

  const brands = activeMembership.brands;

  if (brands.length === 0) {
    return (
      <PillLabel data-testid="brand-switcher-empty">No brand yet</PillLabel>
    );
  }

  if (brands.length === 1) {
    return (
      <PillLabel data-testid="brand-switcher-single">
        {activeBrand?.name ?? brands[0].name}
      </PillLabel>
    );
  }

  async function handleSwitch(brandId: string) {
    if (brandId === activeBrand?.id) return;
    setError(null);
    setPendingId(brandId);
    try {
      await switchBrand(brandId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  }

  const isPending = pendingId !== null;

  return (
    <PopoverMenu
      ariaLabel="Switch brand"
      disabled={isPending}
      trigger={({ isOpen }) => (
        <span
          data-testid="brand-switcher-trigger"
          data-active-id={activeBrand?.id}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-sm font-medium transition-colors",
            "hover:bg-accent hover:text-accent-foreground",
            isOpen && "bg-accent",
            isPending && "cursor-progress opacity-60",
          )}
        >
          <span className="max-w-[12rem] truncate">
            {activeBrand?.name ?? "Select brand"}
          </span>
          {isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </span>
      )}
    >
      <PopoverMenuLabel>Switch brand</PopoverMenuLabel>
      {brands.map((b) => (
        <PopoverMenuItem
          key={b.id}
          data-testid={`brand-switcher-item-${b.id}`}
          selected={b.id === activeBrand?.id}
          disabled={isPending && pendingId !== b.id}
          onSelect={() => void handleSwitch(b.id)}
        >
          {b.name}
        </PopoverMenuItem>
      ))}
      {error && (
        <>
          <PopoverMenuSeparator />
          <div
            role="alert"
            data-testid="brand-switcher-error"
            className="px-2 py-1.5 text-xs text-destructive"
          >
            {error}
          </div>
        </>
      )}
    </PopoverMenu>
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
