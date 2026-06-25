/**
 * Phase 10.4 — Action Scoring unit tests.
 *
 * Pin that the three scorers (Opportunity, WeeklyAction, LeadPriority)
 * each:
 *   - Surface confidence verbatim
 *   - Parse expected_result honestly (no fabrication)
 *   - Derive difficulty/time from the right hint
 *   - Use the right reach-band source (platform-derived vs n/a)
 */

import { describe, expect, it } from "vitest";

import type {
  LeadPriorityItem,
  Opportunity,
  WeeklyAction,
} from "./api";
import {
  humaniseDifficulty,
  humaniseValueBand,
  scoreLeadPriority,
  scoreOpportunity,
  scoreWeeklyAction,
} from "./action-scoring";


function makeOpp(over: Partial<Opportunity> = {}): Opportunity {
  return {
    id: "o1",
    kind: "content",
    headline: "x",
    what_is_happening: "x",
    why_it_matters: "x",
    recommended_action: "x",
    expected_result: "+15 leads in 14 days · ₹15,000–₹25,000",
    confidence: 87,
    reason: "x",
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

function makeAction(over: Partial<WeeklyAction> = {}): WeeklyAction {
  return {
    action_title: "Contact 3 warm leads",
    why: "x",
    business_impact: "x",
    impact_category: "lead",
    expected_result: "+3 booked calls",
    confidence: 75,
    reason: "x",
    cta_label: "Open inbox",
    cta_target: "lead_pages",
    priority: "focus",
    estimated_time: "12 mins",
    ...over,
  };
}

function makeLead(over: Partial<LeadPriorityItem> = {}): LeadPriorityItem {
  return {
    lead_id: "L1",
    email: "a@b.com",
    name: "Aisha",
    company: "X Corp",
    rank: 1,
    priority: "hot",
    why_now: "Visited pricing page 3 times",
    recommended_action: "Call now",
    expected_result: "Likely to convert this week",
    confidence: 91,
    reason: "x",
    impact_category: "revenue",
    estimated_value_band: "high",
    cta_label: "Open lead",
    ...over,
  };
}


describe("scoreOpportunity", () => {
  it("uses opportunity confidence verbatim", () => {
    const s = scoreOpportunity(makeOpp({ confidence: 73 }));
    expect(s.confidence).toBe(73);
  });

  it("derives the platform's reach band when confidence is high", () => {
    const s = scoreOpportunity(makeOpp({ confidence: 90 }));
    expect(s.expectedReach.band).toBe("high");
    expect(s.expectedReach.display).not.toBe("Awaiting data");
  });

  it("returns 'Awaiting data' for speculative-confidence opportunities", () => {
    const s = scoreOpportunity(makeOpp({ confidence: 30 }));
    expect(s.expectedReach.display).toBe("Awaiting data");
  });

  it("parses leads + revenue from expected_result text", () => {
    const s = scoreOpportunity(makeOpp());
    expect(s.expectedLeads).toContain("15");
    expect(s.expectedRevenue).toContain("₹15,000");
  });

  it("derives difficulty from format (reel = hard)", () => {
    const s = scoreOpportunity(
      makeOpp({
        generator: {
          target: "content",
          format: "reel",
          platform: "instagram",
          goal: "engagement",
          objective: null,
        },
      }),
    );
    expect(s.difficulty).toBe("hard");
    expect(s.timeRequired).toMatch(/mins|min/);
  });

  it("defaults to medium difficulty when generator hint is missing", () => {
    const s = scoreOpportunity(
      makeOpp({
        generator: null as unknown as Opportunity["generator"],
      }),
    );
    expect(s.difficulty).toBe("medium");
  });

  it("source label is 'opportunity'", () => {
    expect(scoreOpportunity(makeOpp()).source).toBe("opportunity");
  });
});


describe("scoreWeeklyAction", () => {
  it("uses estimated_time verbatim when provided", () => {
    const s = scoreWeeklyAction(makeAction({ estimated_time: "8 mins" }));
    expect(s.timeRequired).toBe("8 mins");
  });

  it("falls back to a sensible default when estimated_time is blank", () => {
    const s = scoreWeeklyAction(makeAction({ estimated_time: "" }));
    expect(s.timeRequired).toBe("30 mins");
  });

  it("WeeklyActions don't carry a platform — reach is honest 'Awaiting data'", () => {
    const s = scoreWeeklyAction(makeAction());
    expect(s.expectedReach.display).toBe("Awaiting data");
  });

  it("parses expected_result leads phrase", () => {
    const s = scoreWeeklyAction(makeAction({ expected_result: "+3 booked calls" }));
    // "booked calls" doesn't match "leads" — should fall through to summary, not leads.
    expect(s.expectedLeads).toBeNull();
  });
});


describe("scoreLeadPriority", () => {
  it("uses lead confidence verbatim", () => {
    const s = scoreLeadPriority(makeLead({ confidence: 91 }));
    expect(s.confidence).toBe(91);
  });

  it("hides reach (contacting one person isn't a reach signal)", () => {
    const s = scoreLeadPriority(makeLead());
    expect(s.expectedReach.band).toBe("unknown");
  });

  it("uses humanised value-band when LLM didn't include a revenue figure", () => {
    const s = scoreLeadPriority(
      makeLead({
        expected_result: "Likely to convert this week",
        estimated_value_band: "high",
      }),
    );
    expect(s.expectedRevenue).toBe("High-value lead");
  });

  it("prefers parsed revenue over value-band", () => {
    const s = scoreLeadPriority(
      makeLead({
        expected_result: "Deal worth ₹45,000",
        estimated_value_band: "low",
      }),
    );
    expect(s.expectedRevenue).toContain("₹45,000");
  });

  it("returns null revenue when band is 'unknown' and no revenue parsed", () => {
    const s = scoreLeadPriority(
      makeLead({
        expected_result: "Likely to convert",
        estimated_value_band: "unknown",
      }),
    );
    expect(s.expectedRevenue).toBeNull();
  });
});


describe("humaniseValueBand", () => {
  it("maps each band to a founder-friendly label", () => {
    expect(humaniseValueBand("high")).toBe("High-value lead");
    expect(humaniseValueBand("medium")).toBe("Mid-value lead");
    expect(humaniseValueBand("low")).toBe("Low-value lead");
    expect(humaniseValueBand("unknown")).toBeNull();
  });
});


describe("humaniseDifficulty", () => {
  it("maps each difficulty to a founder-friendly label", () => {
    expect(humaniseDifficulty("easy")).toBe("Quick win");
    expect(humaniseDifficulty("medium")).toBe("Some effort");
    expect(humaniseDifficulty("hard")).toBe("Bigger lift");
  });
});
