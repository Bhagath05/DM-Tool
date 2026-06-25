"use client";

/**
 * Phase 10.4 — /today/command-center.
 *
 * The execution surface that turns Today's Plan from a briefing into
 * a launchpad. Sits one click under /today via a card on the home page.
 *
 * Composition (top to bottom):
 *
 *   1. CommandCenterHero       (greeting + signals badges)
 *   2. NextBestAction          (1 huge card — top focus action)
 *   3. RecommendedPosts        (4 platform cards, 1 ranked post each)
 *   4. RecommendedAds          (3 ad-platform cards)
 *   5. RecommendedReels        (up to 2 reel ideas)
 *   6. LandingPageImprovements (5 heuristic findings)
 *   7. LeadOpportunities       (5 ranked priority leads)
 *
 * Discipline:
 *   - Every section streams independently — no waterfall.
 *   - Every card carries the Action Scoring footer (confidence /
 *     reach / leads / revenue / difficulty / time).
 *   - All data is composed from existing APIs (api.coach.weekly,
 *     api.opportunities.center, api.leads.intelligence,
 *     api.landingPages.list, api.social.patterns).
 *   - No backend changes, no schema changes, no API additions.
 */

import nextDynamic from "next/dynamic";

import { CommandCenterHero } from "./_components/command-center-hero";
import { NextBestAction } from "./_components/next-best-action";
import { Skeleton } from "@/components/ui/skeleton";

const sectionFallback = (
  <div className="flex flex-col gap-3">
    <Skeleton className="h-6 w-48" />
    <Skeleton className="h-40 w-full rounded-2xl" />
  </div>
);

const RecommendedPosts = nextDynamic(
  () =>
    import("./_components/recommended-posts").then((m) => ({
      default: m.RecommendedPosts,
    })),
  { loading: () => sectionFallback },
);
const RecommendedAds = nextDynamic(
  () =>
    import("./_components/recommended-ads").then((m) => ({
      default: m.RecommendedAds,
    })),
  { loading: () => sectionFallback },
);
const RecommendedReels = nextDynamic(
  () =>
    import("./_components/recommended-reels").then((m) => ({
      default: m.RecommendedReels,
    })),
  { loading: () => sectionFallback },
);
const LandingPageImprovements = nextDynamic(
  () =>
    import("./_components/landing-page-improvements").then((m) => ({
      default: m.LandingPageImprovements,
    })),
  { loading: () => sectionFallback },
);
const LeadOpportunities = nextDynamic(
  () =>
    import("./_components/lead-opportunities").then((m) => ({
      default: m.LeadOpportunities,
    })),
  { loading: () => sectionFallback },
);

export const dynamic = "force-dynamic";

export default function CommandCenterPage() {
  return (
    <div
      className="mx-auto flex max-w-6xl flex-col gap-12"
      data-testid="command-center-page"
    >
      <CommandCenterHero />
      <NextBestAction />
      <RecommendedPosts />
      <RecommendedAds />
      <RecommendedReels />
      <LandingPageImprovements />
      <LeadOpportunities />
    </div>
  );
}
