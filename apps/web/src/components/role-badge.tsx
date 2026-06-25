"use client";

/**
 * RoleBadge — visualises the caller's primary role on the active org.
 *
 * "Primary" = first slug alphabetically (matches how the backend sorts
 * them for both structlog + Sentry tagging). When a user has multiple
 * roles we surface the most-permissive one in the tooltip via title.
 *
 * Renders nothing when there's no active membership — keeps the topbar
 * from showing a stray "no role" badge during loading.
 */

import { useTenant } from "@/components/tenant-provider";
import { cn } from "@/lib/utils";

const ROLE_TONES: Record<string, string> = {
  owner: "bg-primary/10 text-primary border-primary/20",
  admin: "bg-primary/10 text-primary border-primary/20",
  editor: "bg-accent text-accent-foreground border-border",
  viewer: "bg-muted text-muted-foreground border-border",
};

export function RoleBadge() {
  const { roleSlugs, status } = useTenant();

  if (status !== "ready" || roleSlugs.length === 0) return null;

  const sorted = [...roleSlugs].sort();
  const primary = sorted[0];
  const tone = ROLE_TONES[primary] ?? "bg-muted text-muted-foreground border-border";

  return (
    <span
      data-testid="role-badge"
      title={sorted.length > 1 ? `Roles: ${sorted.join(", ")}` : undefined}
      className={cn(
        "inline-flex h-6 items-center rounded-md border px-1.5 text-xs font-medium capitalize",
        tone,
      )}
    >
      {primary}
      {sorted.length > 1 && (
        <span className="ml-0.5 opacity-60">+{sorted.length - 1}</span>
      )}
    </span>
  );
}
