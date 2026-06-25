"use client";

/**
 * Phase 10.0 polish — Overview hero band.
 *
 * Premium top-of-page composition:
 *
 *   OVERVIEW · Wednesday, Jun 3
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ Good afternoon, Bhagath.                                     │
 *   │ Acme Coffee · Last refreshed 12 minutes ago                  │
 *   └──────────────────────────────────────────────────────────────┘
 *   [● Growing] [Last 30 days] [Acme Coffee · Mumbai brand]
 *
 * Reads from the existing tenant + performance state — no new
 * endpoints. The status pill is derived from the Performance overview
 * the page already loads.
 */

import { Building2, CalendarRange, Sparkles } from "lucide-react";

import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import type { PerformanceCards } from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

export interface OverviewHeroProps {
  firstName: string;
  organizationName: string | null;
  brandName: string | null;
  perf: PerformanceCards | null;
  className?: string;
}

export function OverviewHero({
  firstName,
  organizationName,
  brandName,
  perf,
  className,
}: OverviewHeroProps) {
  const status = pickStatus(perf);
  const lastRefreshed = perf?.lastUploadAt
    ? formatRelative(perf.lastUploadAt)
    : null;
  const dateRange = perf?.lastUploadAt
    ? "Last 30 days"
    : "Awaiting first upload";
  const today = formatToday();

  return (
    <header
      data-testid="overview-hero"
      className={cn(
        "animate-fade-up flex flex-col gap-5",
        className,
      )}
    >
      {/* Top meta line — date + breadcrumb */}
      <div className="flex flex-wrap items-center gap-2 text-meta">
        <span>Overview</span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span>{today}</span>
      </div>

      {/* Display-size greeting */}
      <div className="flex flex-col gap-2">
        <h1 className="text-display">
          {greet()}, {firstName}.
        </h1>
        <p className="text-base text-muted-foreground sm:text-lg">
          {organizationName ? (
            <>
              <span className="font-medium text-foreground">
                {organizationName}
              </span>
              {brandName && (
                <span className="text-muted-foreground"> · {brandName}</span>
              )}
              {lastRefreshed && (
                <span className="text-muted-foreground/80">
                  {" "}
                  · Last refreshed {lastRefreshed}
                </span>
              )}
            </>
          ) : (
            "Here's what's happening with your business right now."
          )}
        </p>
      </div>

      {/* Status row — pills */}
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill
          tone={status.tone}
          size="md"
          dot
          data-testid="overview-hero-status"
        >
          {status.label}
        </StatusPill>
        <StatusPill
          tone="neutral"
          size="md"
          icon={CalendarRange}
          data-testid="overview-hero-range"
        >
          {dateRange}
        </StatusPill>
        {organizationName && (
          <StatusPill
            tone="neutral"
            size="md"
            icon={Building2}
            data-testid="overview-hero-org"
          >
            {organizationName}
            {brandName && ` · ${brandName}`}
          </StatusPill>
        )}
        <StatusPill
          tone="ai"
          size="md"
          icon={Sparkles}
          data-testid="overview-hero-plan"
        >
          AI Performance OS
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

function formatRelative(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, now - then);
    const mins = Math.round(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
    const days = Math.round(hrs / 24);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  } catch {
    return "recently";
  }
}

function pickStatus(perf: PerformanceCards | null): {
  label: string;
  tone: PillTone;
} {
  if (!perf || !perf.hasUsableCards) {
    return { label: "Tracking", tone: "neutral" };
  }
  const hasWaste = perf.cards.some(
    (c) => c.kind === "budget_waste" || c.kind === "audience_loser",
  );
  const hasHighWinner = perf.cards.some(
    (c) =>
      (c.kind === "winner" ||
        c.kind === "audience_winner" ||
        c.kind === "concept_winner" ||
        c.kind === "creative_dna") &&
      c.confidence >= 80,
  );
  if (hasHighWinner && !hasWaste) return { label: "Growing", tone: "good" };
  if (hasWaste) return { label: "Needs attention", tone: "watch" };
  return { label: "Stable", tone: "neutral" };
}
