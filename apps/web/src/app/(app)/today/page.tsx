"use client";

/**
 * Phase 10.3b — Today's Plan.
 *
 * The new homepage. Replaces the Phase 10.0 /overview composition with
 * an action-first, founder-friendly five-section layout per the
 * Founder Simplification Pass (docs/phase-10.3-founder-simplification.md):
 *
 *   1. Today Hero            (greeting · date · workspace · plan badge)
 *   2. One Thing To Do Today (AI Coach hero card — the #1 action)
 *   3. Your Day At A Glance  (4 mini-tiles: leads / posts / opps / done)
 *   4. This Week             (5-day action strip)
 *   5. What Changed          (recent shifts since last visit)
 *
 * Discipline:
 *   - Reuses every existing API. No new backend, no schema change,
 *     no contract modification.
 *   - Each section owns its own loading + error state — the page
 *     never blocks on a single waterfall.
 *   - Removed from this surface (relative to /overview): Executive
 *     Summary 4-tile snapshot, Winning Creative Formula, full
 *     Performance Intelligence, Industry Benchmark, Business Profile.
 *     Those live at /results (Slice 6) and /settings/workspace.
 *
 * `/overview` keeps working unchanged — direct URL still resolves to
 * the prior analytics-leaning page. Slice 6 may flip it into a legacy
 * redirect; for now it remains as a power-user backup.
 */

import { ArrowRight, Zap } from "lucide-react";
import Link from "next/link";

import { AiCoachPanel } from "../overview/_components/ai-coach-panel";
import { useTenant } from "@/components/tenant-provider";

import { DayAtAGlance } from "./_components/day-at-a-glance";
import { ThisWeekStrip } from "./_components/this-week-strip";
import { TodayHero } from "./_components/today-hero";
import { WhatChanged } from "./_components/what-changed";

export const dynamic = "force-dynamic";

export default function TodayPage() {
  const tenant = useTenant();

  const firstName =
    tenant.user?.display_name?.split(" ")[0] ?? "there";
  const organizationName =
    tenant.activeOrg?.name ??
    tenant.memberships?.[0]?.organization.name ??
    null;
  const brandName = tenant.activeBrand?.name ?? null;

  return (
    <div
      className="mx-auto flex max-w-6xl flex-col gap-12"
      data-testid="today-page"
    >
      {/* 1. Greeting + date */}
      <TodayHero
        firstName={firstName}
        organizationName={organizationName}
        brandName={brandName}
      />

      {/* 2. THE one thing to do today */}
      <AiCoachPanel />

      {/* 2b. Phase 10.4 — entry to the execution surface. Slim band so it
          doesn't crowd the hero. Founders ready to ship more this week
          jump here; Today's Plan stays focused on the single action. */}
      <Link
        href={"/today/command-center" as never}
        data-testid="today-command-center-cta"
        className="group flex items-center justify-between gap-3 rounded-2xl border border-ai-border bg-ai-soft/40 px-5 py-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm"
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-ai/15 text-ai-soft-foreground"
          >
            <Zap className="h-4 w-4" />
          </span>
          <div className="flex flex-col">
            <span className="text-sm font-semibold text-foreground">
              Open the AI Command Center
            </span>
            <span className="text-xs text-muted-foreground">
              Six ranked moves — posts, ads, reels, lead actions, landing-page fixes — each with confidence + time to ship.
            </span>
          </div>
        </div>
        <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
      </Link>

      {/* 3. Glance row */}
      <DayAtAGlance />

      {/* 4. Five-day plan */}
      <ThisWeekStrip />

      {/* 5. What changed feed */}
      <WhatChanged />
    </div>
  );
}
