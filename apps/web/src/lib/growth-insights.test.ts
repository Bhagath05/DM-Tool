/**
 * Phase 10.3c — Growth Insights composer tests.
 *
 * The page calls `composeGrowthInsights({ opportunities, postingPlans,
 * performance })` and renders the result. These pure-function tests
 * pin three guarantees:
 *
 *   1. Each source contributes at most one insight (no duplicates).
 *   2. Empty / null sources don't crash and silently skip — better
 *      to surface fewer real insights than three thin ones.
 *   3. Every insight carries a CTA href + label (Founder Rule).
 */

import { describe, expect, it } from "vitest";

import type {
  Opportunity,
  OpportunityCenterReport,
} from "./api";
import {
  composeGrowthInsights,
  topOpportunityInsight,
  topPerformanceInsight,
  topPostingInsight,
} from "./growth-insights";
import type { PerformanceCards } from "./performance-translator";
import type { PlatformPostingPlan } from "./posting-time";

function makeOpp(over: Partial<Opportunity> = {}): Opportunity {
  return {
    id: "opp-1",
    kind: "content",
    headline: "AI Payroll content demand surged",
    what_is_happening: "Search interest up 38% week-over-week.",
    why_it_matters: "Your audience is actively researching this.",
    recommended_action: "Create a carousel breaking down 5 setup steps.",
    expected_result: "+15-25 leads in 14 days.",
    confidence: 87,
    reason: "Trend volume + your existing audience overlap.",
    impact_category: "lead",
    evidence: [],
    generator: {
      target: "content",
      format: "carousel",
      platform: "linkedin",
      goal: "leads",
      objective: null,
    },
    ...over,
  };
}

function makeReport(
  contentOpps: Opportunity[] = [],
  adOpps: Opportunity[] = [],
): OpportunityCenterReport {
  return {
    headline: "test",
    hero_recommendation: {
      what_is_happening: "x",
      impact_category: "lead",
      recommendation: "y",
      expected_result: "z",
      confidence: 70,
      reason: "q",
    },
    content_opportunities: contentOpps,
    ad_opportunities: adOpps,
    skip_for_now: [],
    signals_used: [],
    generated_at: "2026-06-08T00:00:00Z",
  };
}

function makePlan(
  over: Partial<PlatformPostingPlan> = {},
): PlatformPostingPlan {
  return {
    platform: "linkedin",
    day: "Mon",
    source: "derived",
    windows: [
      {
        start_hour: 8,
        start_minute: 30,
        confidence_score: 80,
        engagement_score: 75,
      },
    ],
    ...over,
  };
}

function makePerfCards(
  cards: PerformanceCards["cards"] = [],
): PerformanceCards {
  return {
    cards,
    hasUsableCards: cards.length > 0,
    lastUploadAt: "2026-06-07T10:00:00Z",
    rowsIngested: 100,
    creativesTracked: 5,
  };
}

function makePerfCard(
  over: Partial<PerformanceCards["cards"][number]> = {},
): PerformanceCards["cards"][number] {
  return {
    id: "card-1",
    kind: "winner",
    section: "baseline",
    confidence: 85,
    impactCategory: "lead",
    whatIsHappening: "Concept 'before/after' is winning across audiences.",
    recommendation: "Replicate the before/after hook in 3 new posts this week.",
    expectedResult: "+15% engagement based on the past 14 days.",
    reason: "Top concept by performance score.",
    evidence: {},
    ...over,
  };
}


describe("topOpportunityInsight", () => {
  it("returns null when there's no report", () => {
    expect(topOpportunityInsight(null)).toBeNull();
  });

  it("returns null when both opportunity arrays are empty", () => {
    expect(topOpportunityInsight(makeReport([], []))).toBeNull();
  });

  it("picks the highest-confidence opportunity across both arrays", () => {
    const insight = topOpportunityInsight(
      makeReport(
        [makeOpp({ id: "c1", confidence: 70 })],
        [makeOpp({ id: "a1", confidence: 95 })],
      ),
    );
    expect(insight).not.toBeNull();
    expect(insight?.title).toContain("2 opportunities detected");
    expect(insight?.detail).toContain("95%");
    expect(insight?.ctaHref).toBe("/grow/opportunities");
  });

  it("uses singular when there's exactly one opportunity", () => {
    const insight = topOpportunityInsight(makeReport([makeOpp()], []));
    expect(insight?.title).toBe("1 opportunity detected");
  });
});


describe("topPostingInsight", () => {
  it("returns null when there are no plans", () => {
    expect(topPostingInsight([])).toBeNull();
  });

  it("picks the highest-confidence window across platforms", () => {
    const insight = topPostingInsight([
      makePlan({
        platform: "instagram",
        windows: [
          {
            start_hour: 11,
            start_minute: 0,
            confidence_score: 60,
            engagement_score: 65,
          },
        ],
      }),
      makePlan({
        platform: "linkedin",
        windows: [
          {
            start_hour: 9,
            start_minute: 30,
            confidence_score: 92,
            engagement_score: 88,
          },
        ],
      }),
    ]);
    expect(insight?.title).toBe("Post on LinkedIn at 09:30 today");
    expect(insight?.tone).toBe("good"); // derived plan
  });

  it("marks placeholder-sourced insights as neutral", () => {
    const insight = topPostingInsight([
      makePlan({
        source: "placeholder",
        windows: [
          {
            start_hour: 11,
            start_minute: 0,
            confidence_score: 55,
            engagement_score: 60,
          },
        ],
      }),
    ]);
    expect(insight?.tone).toBe("neutral");
    expect(insight?.detail).toContain("Industry norm");
  });
});


describe("topPerformanceInsight", () => {
  it("returns null when there are no cards", () => {
    expect(topPerformanceInsight(null)).toBeNull();
    expect(topPerformanceInsight(makePerfCards([]))).toBeNull();
  });

  it("ignores non-shift kinds", () => {
    const insight = topPerformanceInsight(
      makePerfCards([
        makePerfCard({ kind: "info" as never, whatIsHappening: "steady" }),
      ]),
    );
    expect(insight).toBeNull();
  });

  it("picks the highest-confidence winner", () => {
    const insight = topPerformanceInsight(
      makePerfCards([
        makePerfCard({ id: "a", kind: "winner", confidence: 70 }),
        makePerfCard({ id: "b", kind: "creative_dna", confidence: 95 }),
      ]),
    );
    expect(insight?.title).toContain("before/after");
    expect(insight?.tone).toBe("good");
  });

  it("marks loser cards as 'watch' tone", () => {
    const insight = topPerformanceInsight(
      makePerfCards([
        makePerfCard({
          id: "loser",
          kind: "audience_loser",
          confidence: 88,
          whatIsHappening: "Lookalike-2% CTR fell sharply.",
        }),
      ]),
    );
    expect(insight?.tone).toBe("watch");
  });
});


describe("composeGrowthInsights", () => {
  it("returns empty array when every source is empty/null", () => {
    expect(
      composeGrowthInsights({
        opportunities: null,
        postingPlans: [],
        performance: null,
      }),
    ).toEqual([]);
  });

  it("contributes at most one insight per source", () => {
    const insights = composeGrowthInsights({
      opportunities: makeReport([makeOpp(), makeOpp({ id: "o2" })]),
      postingPlans: [makePlan(), makePlan({ platform: "instagram" })],
      performance: makePerfCards([
        makePerfCard(),
        makePerfCard({ id: "p2" }),
      ]),
    });
    expect(insights).toHaveLength(3);
    const ids = insights.map((i) => i.id).sort();
    expect(ids).toEqual([
      "insight-opportunities",
      "insight-performance",
      "insight-posting-time",
    ]);
  });

  it("every insight has a non-empty CTA label + href", () => {
    const insights = composeGrowthInsights({
      opportunities: makeReport([makeOpp()]),
      postingPlans: [makePlan()],
      performance: makePerfCards([makePerfCard()]),
    });
    for (const insight of insights) {
      expect(insight.ctaLabel).not.toBe("");
      expect(insight.ctaHref).toMatch(/^\/(grow|create|results|today)/);
    }
  });
});
