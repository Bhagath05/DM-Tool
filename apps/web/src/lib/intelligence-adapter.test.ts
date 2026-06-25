/**
 * Intelligence adapter tests.
 */

import { describe, expect, it } from "vitest";

import {
  intelligenceToAdvisoryTrend,
  intelligenceToHero,
  intelligenceToOpportunityReport,
  translateIntelligenceRec,
  type IntelligenceReport,
} from "./intelligence-adapter";

const baseRec = {
  observation: "You have 3 hot leads waiting.",
  root_cause: "Recent landing page traffic converted but no follow-up sent.",
  recommended_action: "Reply to hot leads before posting new content.",
  expected_impact: "Convert existing interest into booked calls.",
  confidence: 72,
  data_sources_used: [{ key: "hot", label: "Hot leads", value: "3" }],
  impact_category: "lead" as const,
};

describe("intelligence-adapter", () => {
  it("maps six fields to AiRecommendation props", () => {
    const props = translateIntelligenceRec(baseRec);
    expect(props.whatIsHappening).toBe(baseRec.observation);
    expect(props.reason).toBe(baseRec.root_cause);
    expect(props.recommendation).toBe(baseRec.recommended_action);
    expect(props.expectedResult).toBe(baseRec.expected_impact);
    expect(props.confidence).toBe(72);
  });

  it("builds opportunity report from intelligence", () => {
    const report: IntelligenceReport = {
      ready: true,
      hero: baseRec,
      content_opportunities: [
        {
          ...baseRec,
          kind: "content",
          headline: "Post a reel",
          generator_hint: {
            target: "content",
            format: "reel",
            platform: "Instagram",
            goal: "Drive engagement",
            objective: null,
          },
        },
      ],
      ad_opportunities: [],
      signals_used: ["leads"],
      confidence_cap: 75,
      generated_at: new Date().toISOString(),
    };
    const opp = intelligenceToOpportunityReport(report);
    expect(opp.hero_recommendation.recommendation).toBe(baseRec.recommended_action);
    expect(opp.content_opportunities).toHaveLength(1);
  });

  it("maps trend advisory", () => {
    const trend = intelligenceToAdvisoryTrend(baseRec);
    expect(trend?.recommended_action).toBe(baseRec.recommended_action);
  });

  it("maps hero for opportunity center", () => {
    const hero = intelligenceToHero(baseRec);
    expect(hero.what_is_happening).toBe(baseRec.observation);
    expect(hero.reason).toBe(baseRec.root_cause);
  });
});
