"use client";

/**
 * Analytics dashboard — Constitution-compliant rewrite (Phase 3).
 *
 * Layout, top to bottom:
 *
 *   1. AI Summary card                   (reuses Phase 2.5 AnalyticsSummary)
 *   2. Lead Generation section           (BusinessMetric × N + AiRecommendation)
 *   3. Coming Soon outcome cards         (Revenue / Customers / Time / Cost)
 *   4. Deep dive tables                  (collapsed in Simple, inline in Pro)
 *
 * The page NEVER leads with raw metrics. Every BusinessMetric instance
 * carries the full Constitution contract via the translator in
 * lib/analytics-translator.ts.
 *
 * Existing tables (TopAssets / LandingPages / Sources / Timeline / Status
 * donut) are preserved untouched — they live behind a "Deep dive"
 * disclosure for users in Simple Mode and render inline in Professional
 * Mode. Hide, don't delete (Constitution).
 */

import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  AiRecommendation,
  BusinessMetric,
} from "@/components/ui/business-metric";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  api,
  type LandingPagePerformanceRow,
  type OverviewKpis,
  type SourceRow,
  type StatusDistribution,
  type TimelineResponse,
  type TopAssetRow,
} from "@/lib/api";
import {
  translateConversionRate,
  translateTopChannel,
  translateTotalLeads,
} from "@/lib/analytics-translator";
import { useViewMode } from "@/lib/use-view-mode";

import { ComingSoonCard } from "./coming-soon-card";
import { LandingPagesTable } from "./landing-pages-table";
import { Overview } from "./overview";
import { SourcesTable } from "./sources-table";
import { StatusDonut } from "./status-donut";
import { AnalyticsSummaryCard, useAnalyticsSummary } from "./summary-card";
import { Timeline } from "./timeline";
import { TopAssetsTable } from "./top-assets-table";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      overview: OverviewKpis;
      timeline: TimelineResponse;
      sources: SourceRow[];
      pages: LandingPagePerformanceRow[];
      status: StatusDistribution;
      topAssets: TopAssetRow[];
    };

export function Dashboard() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [window, setWindow] = useState<7 | 14 | 30 | 90>(30);
  const [deepDiveOpen, setDeepDiveOpen] = useState(false);
  const summaryStore = useAnalyticsSummary();
  const { isProfessional } = useViewMode();

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [overview, timeline, sources, pages, status, topAssets] =
        await Promise.all([
          api.analytics.overview(),
          api.analytics.timeline(window),
          api.analytics.sources(25),
          api.analytics.landingPages(),
          api.analytics.statusDistribution(),
          api.analytics.topAssets(10),
        ]);
      setState({
        kind: "ready",
        overview,
        timeline,
        sources: sources.items,
        pages: pages.items,
        status,
        topAssets: topAssets.items,
      });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "Failed to load analytics",
      });
    }
  }, [window]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <Card>
        <CardContent
          data-testid="analytics-loading"
          className="flex items-center gap-2 pt-6 text-sm text-muted-foreground"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading your business signals…
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent
          data-testid="analytics-error"
          className="pt-6 text-sm text-destructive"
        >
          {state.message}
        </CardContent>
      </Card>
    );
  }

  // ---- Translate raw KPIs → Constitution-shaped cards --------------
  const totalLeads = translateTotalLeads(state.overview);
  const conversion = translateConversionRate(state.overview);
  const topChannel = translateTopChannel(state.sources);

  // Professional Mode auto-expands the deep dive.
  const showDeepDive = deepDiveOpen || isProfessional;

  return (
    <div className="space-y-8">
      {/* ============================================================ */}
      {/* 1. AI Summary — the consultant's voice                        */}
      {/* ============================================================ */}
      <AnalyticsSummaryCard
        state={summaryStore.state}
        refreshing={summaryStore.refreshing}
        onRefresh={summaryStore.refresh}
      />

      {/* ============================================================ */}
      {/* 2. Lead Generation — the outcome we have data for            */}
      {/* ============================================================ */}
      <section
        data-testid="section-lead-generation"
        aria-labelledby="lead-generation-heading"
        className="space-y-3"
      >
        <h2
          id="lead-generation-heading"
          className="text-lg font-semibold tracking-tight"
        >
          Lead generation
        </h2>
        <p className="text-sm text-muted-foreground">
          People who showed real interest in your business and how they
          found you.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <BusinessMetric
            data-testid="metric-total-leads"
            {...totalLeads}
          />
          {conversion ? (
            <BusinessMetric
              data-testid="metric-conversion"
              {...conversion}
            />
          ) : (
            <ComingSoonCard
              impactCategory="lead"
              title="Visitor → lead conversion"
              reason={
                state.overview.total_views < 20
                  ? `We need at least 20 page views to give you a reliable conversion rate (currently ${state.overview.total_views}).`
                  : "Not enough page views yet to calculate a reliable rate."
              }
              unlockedBy="Drive more visitors to your lead page — even 20-50 unlocks the metric."
            />
          )}
        </div>
        {topChannel && (
          <AiRecommendation
            data-testid="rec-top-channel"
            {...topChannel}
          />
        )}
      </section>

      {/* ============================================================ */}
      {/* 3. Outcome categories we don't yet have data for             */}
      {/* ============================================================ */}
      <section
        data-testid="section-coming-soon"
        aria-labelledby="more-outcomes-heading"
        className="space-y-3"
      >
        <h2
          id="more-outcomes-heading"
          className="text-lg font-semibold tracking-tight"
        >
          More business outcomes
        </h2>
        <p className="text-sm text-muted-foreground">
          What we&apos;ll show once your data unlocks it.
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <ComingSoonCard
            impactCategory="revenue"
            title="Revenue impact"
            reason="No way to attribute revenue to marketing yet — we don't capture customer transactions."
            unlockedBy="Connect your payment platform OR tag leads as 'converted' to start tracking revenue."
          />
          <ComingSoonCard
            impactCategory="customer"
            title="Customer growth"
            reason="We track leads but don't yet distinguish leads from paying customers."
            unlockedBy="Mark leads as 'customer' when they convert. Tagging a few is enough to start."
          />
          <ComingSoonCard
            impactCategory="time"
            title="Time savings"
            reason="We aren't measuring hours saved by AI-generated content yet."
            unlockedBy="Log time spent on manual marketing tasks so we can quantify the AI lift."
          />
          <ComingSoonCard
            impactCategory="cost"
            title="Cost optimisation"
            reason="No ad-spend data flowing in — we can't show cost-per-lead or ROAS in business terms yet."
            unlockedBy="Connect your ad accounts (Facebook / Google) so we can attribute spend to leads."
          />
        </div>
      </section>

      {/* ============================================================ */}
      {/* 4. Deep dive — original tables, collapsed in Simple Mode      */}
      {/* ============================================================ */}
      <section
        data-testid="section-deep-dive"
        aria-labelledby="deep-dive-heading"
        className="space-y-3"
      >
        <div className="flex items-center justify-between">
          <div>
            <h2
              id="deep-dive-heading"
              className="text-lg font-semibold tracking-tight"
            >
              Deep dive
            </h2>
            <p className="text-sm text-muted-foreground">
              Per-page, per-source, and per-asset breakdown. Useful when
              you want to investigate a specific number from above.
            </p>
          </div>
          {!isProfessional && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setDeepDiveOpen((o) => !o)}
              data-testid="deep-dive-toggle"
            >
              {showDeepDive ? (
                <>
                  Hide deep dive <ChevronUp className="ml-1 h-3 w-3" />
                </>
              ) : (
                <>
                  Show deep dive <ChevronDown className="ml-1 h-3 w-3" />
                </>
              )}
            </Button>
          )}
        </div>

        {showDeepDive && (
          <div
            data-testid="deep-dive-content"
            className="space-y-6 rounded-lg border border-border bg-card/40 p-4"
          >
            <Overview kpis={state.overview} />

            <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
              <Timeline
                data={state.timeline}
                windowDays={window}
                onWindowChange={setWindow}
              />
              <StatusDonut status={state.status} />
            </div>

            <TopAssetsTable rows={state.topAssets} />

            <div className="grid gap-6 lg:grid-cols-2">
              <LandingPagesTable rows={state.pages} />
              <SourcesTable rows={state.sources} />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
