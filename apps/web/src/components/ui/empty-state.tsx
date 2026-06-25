"use client";

/**
 * Phase 10.0 — EmptyState primitive.
 *
 * Premium empty-state shell. Icon + title + 1-line copy + primary
 * CTA + optional secondary link/CTA. Used by every "no data yet" /
 * "coming soon" / "not enough data" surface so the empty state
 * never reads as broken — always as a starting point.
 *
 * Variants:
 *   default   — neutral background, suggests next action.
 *   ai        — soft AI accent, used when the empty state IS the
 *               "we need data to think for you" message.
 *
 * Never fabricates. The body copy comes from the caller; we just
 * present it elegantly.
 */

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  /** Optional secondary helper line, e.g. "Why this threshold?" */
  hint?: string;
  /** Primary action. Pass a `<Button>` or `<Link>` — anything clickable. */
  action?: React.ReactNode;
  /** Less prominent secondary action. */
  secondaryAction?: React.ReactNode;
  variant?: "default" | "ai";
  className?: string;
  "data-testid"?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  hint,
  action,
  secondaryAction,
  variant = "default",
  className,
  "data-testid": testId,
}: EmptyStateProps) {
  return (
    <div
      data-testid={testId ?? "empty-state"}
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-10 text-center",
        variant === "ai"
          ? "border-ai-border bg-ai-soft"
          : "border-border bg-card/40",
        className,
      )}
    >
      <span
        className={cn(
          "flex h-11 w-11 items-center justify-center rounded-full",
          variant === "ai"
            ? "bg-ai-soft text-ai"
            : "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        <Icon className="h-5 w-5" />
      </span>
      <div className="max-w-md space-y-1">
        <h3 className="text-base font-semibold tracking-tight">{title}</h3>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
        {hint && (
          <p className="text-xs text-muted-foreground/80">{hint}</p>
        )}
      </div>
      {(action || secondaryAction) && (
        <div className="mt-2 flex flex-col items-center gap-2 sm:flex-row">
          {action}
          {secondaryAction}
        </div>
      )}
    </div>
  );
}
