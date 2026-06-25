"use client";

/**
 * BackLink — tiny primitive for sub-page / deep-link navigation.
 *
 *   ← Back to {label}
 *
 * Renders an explicit Link to a parent destination. Explicit href
 * rather than `router.back()` so a founder who bookmarks the page
 * and lands there cold still gets a predictable trip home (browser
 * history could otherwise dump them on Google).
 *
 * Used by:
 *   - <CommandCenterHero> (sub-page back to Today)
 *   - <FromSourceBanner>  (auto-mounted, reads ?from= and resolves)
 *   - /landing-pages/[id] (sub-page back to /landing-pages)
 */

import { ChevronLeft } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export interface BackLinkProps {
  href: string;
  label: string;
  className?: string;
  "data-testid"?: string;
}

export function BackLink({
  href,
  label,
  className,
  "data-testid": testId,
}: BackLinkProps) {
  return (
    <Link
      href={href as never}
      data-testid={testId ?? "back-link"}
      className={cn(
        "inline-flex w-fit items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground",
        className,
      )}
    >
      <ChevronLeft className="h-3 w-3" />
      {label}
    </Link>
  );
}
