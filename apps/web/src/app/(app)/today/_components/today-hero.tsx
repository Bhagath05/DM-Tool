"use client";

/**
 * Phase 10.3b — Today's Plan hero.
 *
 * Founder-first restraint: greeting + date + workspace + plan only.
 * No analytics-shaped status pill (the old OverviewHero had one — it
 * showed "Growing / Needs attention / Stable" which is a chart-first
 * framing the Founder Simplification Pass explicitly removes from
 * the homepage).
 *
 *   TODAY · Monday, Jun 8
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ Good morning, Nikhil.                                        │
 *   │ Acme Coffee · Default                                        │
 *   └──────────────────────────────────────────────────────────────┘
 *   [● Today's Plan]  [⚡ Early Access]
 *
 * Reads from `useTenant()` only — no API call, no waiting state.
 */

import { Sparkles, Sun } from "lucide-react";

import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export interface TodayHeroProps {
  firstName: string;
  organizationName: string | null;
  brandName: string | null;
  className?: string;
}

export function TodayHero({
  firstName,
  organizationName,
  brandName,
  className,
}: TodayHeroProps) {
  const today = formatToday();

  return (
    <header
      data-testid="today-hero"
      className={cn("animate-fade-up flex flex-col gap-5", className)}
    >
      {/* Top meta line — section name + date */}
      <div className="flex flex-wrap items-center gap-2 text-meta">
        <span>Today</span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span>{today}</span>
      </div>

      {/* Display-size greeting */}
      <div className="flex flex-col gap-2">
        <h1 className="text-display">
          {greet()}, {firstName}.
        </h1>
        {organizationName && (
          <p className="text-base text-muted-foreground sm:text-lg">
            <span className="font-medium text-foreground">
              {organizationName}
            </span>
            {brandName && (
              <span className="text-muted-foreground"> · {brandName}</span>
            )}
          </p>
        )}
      </div>

      {/* Plan-of-day badges — action-oriented, NOT analytics-oriented */}
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill
          tone="ai"
          size="md"
          dot
          icon={Sun}
          data-testid="today-hero-badge"
        >
          Today's Plan
        </StatusPill>
        <StatusPill tone="neutral" size="md" icon={Sparkles}>
          Early Access
        </StatusPill>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------
//  Pure helpers
// ---------------------------------------------------------------------

function greet(): string {
  if (typeof window === "undefined") return "Welcome back";
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function formatToday(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}
