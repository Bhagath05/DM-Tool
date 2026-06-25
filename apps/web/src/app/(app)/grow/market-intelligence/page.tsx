"use client";

/**
 * Phase 10.3c — Market Intelligence (the founder's external radar).
 *
 * Composition (top to bottom):
 *
 *   1. MarketIntelHero            (greeting + signals-tracked badge)
 *   2. GrowthInsights             (top 3 AI insights composed across sources)
 *   3. OpportunitiesDetected      (top-3 highest-confidence plays)
 *   4. PostingTimeIntelligence    (best posting windows today, by platform)
 *   5. TrendDiscovery             (trending topics with momentum + CTA)
 *   6. CompetitorWatch            (honest placeholder for now)
 *   7. ContentGaps                (derived from patterns vs opportunities)
 *   8. AudienceSignals            (audience patterns + perf shift cards)
 *
 * Discipline:
 *   - Every section ships its own loading + empty state — no waterfall.
 *   - Zero new APIs; uses only api.opportunities.center, api.trends.get,
 *     api.social.patterns, api.social.audiencePatterns, api.performance.overview.
 *   - GrowthInsights is composed AT THE PAGE level so it has access to
 *     all three source loads; children stay self-contained otherwise.
 */

import { useCallback, useEffect, useState } from "react";

import {
  api,
  ApiError,
  type OpportunityCenterReport,
  type PerformanceOverview,
} from "@/lib/api";
import {
  composeGrowthInsights,
  type GrowthInsightInputs,
} from "@/lib/growth-insights";
import { translateOverview, type PerformanceCards } from "@/lib/performance-translator";
import { planForDay, todayWeekday } from "@/lib/posting-time";

import { AudienceSignals } from "./_components/audience-signals";
import { CompetitorWatch } from "./_components/competitor-watch";
import { ContentGaps } from "./_components/content-gaps";
import { GrowthInsights, type GrowthInsight } from "./_components/growth-insights";
import { MarketIntelHero } from "./_components/market-intel-hero";
import { OpportunitiesDetected } from "./_components/opportunities-detected";
import { PostingTimeIntelligence } from "./_components/posting-time-intelligence";
import { TrendDiscovery } from "./_components/trend-discovery";

export const dynamic = "force-dynamic";

export default function MarketIntelligencePage() {
  const [signalsTracked, setSignalsTracked] = useState<number | null>(null);
  const [insights, setInsights] = useState<GrowthInsight[] | null>(null);

  // Compose Growth Insights from three lightweight reads. Each is
  // best-effort — if one fails, the other two still feed an insight.
  const loadInsights = useCallback(async () => {
    const [opps, patterns, perfRaw] = await Promise.all([
      api.opportunities.center().catch((err) => {
        if (!(err instanceof ApiError)) console.warn(err);
        return null;
      }),
      api.social.patterns().catch(() => []),
      api.performance.overview().catch((err) => {
        if (!(err instanceof ApiError)) console.warn(err);
        return null;
      }),
    ]);

    const performance: PerformanceCards | null = perfRaw
      ? translateOverview(perfRaw as PerformanceOverview)
      : null;
    const postingPlans = planForDay(patterns ?? [], todayWeekday());

    const inputs: GrowthInsightInputs = {
      opportunities: opps as OpportunityCenterReport | null,
      postingPlans,
      performance,
    };
    setInsights(composeGrowthInsights(inputs));
  }, []);

  useEffect(() => {
    void loadInsights();
  }, [loadInsights]);

  return (
    <div
      className="mx-auto flex max-w-6xl flex-col gap-12"
      data-testid="market-intelligence-page"
    >
      {/* 1. Hero */}
      <MarketIntelHero signalsTracked={signalsTracked} />

      {/* 2. AI Growth Insights */}
      <GrowthInsights insights={insights} />

      {/* 3. Opportunities Detected — also feeds the signals-tracked
          counter via callback. */}
      <OpportunitiesDetected onCountChange={setSignalsTracked} />

      {/* 4. Posting Time Intelligence */}
      <PostingTimeIntelligence />

      {/* 5. Trend Discovery */}
      <TrendDiscovery />

      {/* 6. Competitor Watch (honest placeholder) */}
      <CompetitorWatch />

      {/* 7. Content Gaps */}
      <ContentGaps />

      {/* 8. Audience Signals */}
      <AudienceSignals />
    </div>
  );
}
