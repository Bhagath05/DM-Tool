"use client";

/**
 * Phase 10.0 — Overview page.
 *
 * The single front door. Merges what /dashboard and /today used to be.
 * Composition (top-to-bottom):
 *
 *   1. Quick Wins              (top-3 highest-confidence actions)
 *   2. Executive Summary       (4-tile snapshot: status / opp / waste / impact)
 *   3. AI Coach panel          (1 hero recommendation)
 *   4. Winning Creative Formula (apex DNA card — only when present)
 *   5. Performance Intelligence (full Phase 9.1.5 surface)
 *   6. Action Center           (priority-grouped action list)
 *   7. Industry Benchmark      (coming soon — honest empty)
 *   8. Business Profile        (strategy + edit-onboarding affordance)
 *
 * Loading-state discipline: each section owns its own loading state
 * via skeletons. The page doesn't block on a single waterfall — every
 * section streams in independently so the founder always sees the
 * page shape immediately.
 */

import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  ApiError,
  type PerformanceOverview,
  type WeeklyPlan,
} from "@/lib/api";
import { translateOverview, type PerformanceCards } from "@/lib/performance-translator";

import { ProfileLoader } from "../dashboard/profile-loader";

import { ActionCenter } from "./_components/action-center";
import { AiCoachPanel } from "./_components/ai-coach-panel";
import { ExecutiveSummary } from "./_components/executive-summary";
import { IndustryBenchmark } from "./_components/industry-benchmark";
import { OverviewHero } from "./_components/overview-hero";
import { PerformanceSection } from "./_components/performance-section";
import { QuickWins } from "./_components/quick-wins";
import { SectionHeading } from "@/components/ui/section-heading";
import { WinningCreativeFormula } from "./_components/winning-creative-formula";

export const dynamic = "force-dynamic";

export default function OverviewPage() {
  const tenant = useTenant();
  const [perf, setPerf] = useState<PerformanceCards | null>(null);
  const [perfLoading, setPerfLoading] = useState(true);
  const [weekly, setWeekly] = useState<WeeklyPlan | null>(null);

  // Performance overview — used by Quick Wins, Executive Summary,
  // Winning Creative Formula, and the embedded Action Center.
  const loadPerf = useCallback(async () => {
    setPerfLoading(true);
    try {
      const overview: PerformanceOverview = await api.performance.overview();
      setPerf(translateOverview(overview));
    } catch (err) {
      // Surface as "no data" rather than a hard error — perf is
      // additive; the rest of the page still works.
      if (!(err instanceof ApiError)) console.warn(err);
      setPerf(null);
    } finally {
      setPerfLoading(false);
    }
  }, []);

  // Weekly plan — feeds the Action Center alongside the perf cards.
  const loadWeekly = useCallback(async () => {
    try {
      const plan = await api.coach.weekly();
      setWeekly(plan);
    } catch (err) {
      if (!(err instanceof ApiError)) console.warn(err);
      setWeekly(null);
    }
  }, []);

  useEffect(() => {
    void loadPerf();
    void loadWeekly();
  }, [loadPerf, loadWeekly]);

  const firstName =
    tenant.user?.display_name?.split(" ")[0] ?? "there";
  const organizationName =
    tenant.activeOrg?.name ?? tenant.memberships?.[0]?.organization.name ?? null;
  const brandName = tenant.activeBrand?.name ?? null;

  return (
    <div
      className="mx-auto flex max-w-6xl flex-col gap-12"
      data-testid="overview-page"
    >
      <OverviewHero
        firstName={firstName}
        organizationName={organizationName}
        brandName={brandName}
        perf={perf}
      />

      {/* 1. Quick wins */}
      {perfLoading ? (
        <SectionSkeleton heading="Quick Wins" rows={3} />
      ) : perf ? (
        <QuickWins cards={perf.cards} />
      ) : null}

      {/* 2. Executive summary */}
      {perfLoading ? (
        <SectionSkeleton heading="Today's status" tiles={4} />
      ) : (
        <ExecutiveSummary
          cards={
            perf ?? {
              cards: [],
              hasUsableCards: false,
              lastUploadAt: null,
              rowsIngested: 0,
              creativesTracked: 0,
            }
          }
        />
      )}

      {/* 3. AI Coach panel — loads independently */}
      <AiCoachPanel />

      {/* 4. Winning Creative Formula — only when present */}
      {perf?.cards.find((c) => c.kind === "creative_dna") && (
        <WinningCreativeFormula
          card={perf.cards.find((c) => c.kind === "creative_dna") ?? null}
        />
      )}

      {/* 5. Performance Intelligence — the existing engine card,
            wrapped with the new section heading */}
      <PerformanceSection />

      {/* 6. Action Center */}
      <ActionCenter
        weekly={weekly?.actions ?? []}
        performance={perf?.cards ?? []}
      />

      {/* 7. Industry Benchmark — honest "coming soon" */}
      <IndustryBenchmark />

      {/* 8. Business Profile — strategy snapshot from onboarding +
            the "Edit your profile" affordance. The ProfileLoader
            internals own their own loading / missing / error states,
            and surface the link back into the onboarding wizard for
            edits. */}
      <section
        data-testid="overview-business-profile"
        className="animate-fade-up flex flex-col gap-5"
      >
        <SectionHeading
          eyebrow="About your business"
          heading="Business profile"
          description="The brand snapshot your AI Coach is reasoning from. Update it any time the business changes."
        />
        <ProfileLoader />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function SectionSkeleton({
  heading,
  rows,
  tiles,
}: {
  heading: string;
  rows?: number;
  tiles?: number;
}) {
  return (
    <section className="flex flex-col gap-4" data-testid={`overview-skeleton-${heading.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex flex-col gap-1.5">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-5 w-48" />
      </div>
      {tiles && tiles > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: tiles }).map((_, i) => (
            <div
              key={i}
              className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card p-5"
            >
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))}
        </div>
      )}
      {rows && rows > 0 && (
        <div className="flex flex-col gap-2.5">
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="flex items-center gap-4 rounded-xl border border-border/70 bg-card px-4 py-3.5"
            >
              <Skeleton className="h-8 w-8 rounded-full" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-5 w-24" />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
