/**
 * Tests for the backend-diagnostic → AiRecommendation translator.
 *
 * The Constitution contract lives at the API edge (Pydantic). These
 * tests pin the *frontend's* discipline: the translator must hide
 * any card that arrives malformed rather than rendering "undefined".
 */

import { describe, expect, it } from "vitest";

import type {
  PerformanceDiagnosticCard,
  PerformanceOverview,
} from "@/lib/api";
import {
  groupBySection,
  SECTION_ORDER,
  translateDiagnostic,
  translateOverview,
  type PerformanceOpportunity,
  type PerformanceSection,
} from "@/lib/performance-translator";

function card(over: Partial<PerformanceDiagnosticCard> = {}): PerformanceDiagnosticCard {
  return {
    id: "c-1",
    kind: "winner",
    impact_category: "lead",
    what_happened: "Your best-performing creative is Family dinner reel.",
    why: "It converted at INR 50 per lead — cheaper than the runner-up.",
    recommendation: "Make 2-3 more variants in the same direction.",
    expected_result: "Expect 30-50% more leads next month.",
    reason: "Based on 12,400 impressions, 240 clicks, and 20 conversions.",
    confidence: 75,
    evidence: {
      creative_ref: "Family dinner reel",
      platform: "meta",
      impressions: 12400,
      clicks: 240,
      conversions: 20,
      spend: 1000,
      currency: "INR",
      cpl: 50,
      concept_family: "family_experience",
      audience: "parents_25_45",
      offer_type: "consultation",
    },
    status: "open",
    created_at: "2026-06-01T10:00:00Z",
    ...over,
  };
}

// ---------------------------------------------------------------------
//  Per-card translation
// ---------------------------------------------------------------------

describe("translateDiagnostic", () => {
  it("maps backend snake_case to camelCase AiRecommendation props", () => {
    const opp = translateDiagnostic(card())!;
    expect(opp.id).toBe("c-1");
    expect(opp.impactCategory).toBe("lead");
    expect(opp.recommendation.toLowerCase()).toContain("variants");
    expect(opp.expectedResult.toLowerCase()).toContain("leads");
    expect(opp.confidence).toBe(75);
    expect(opp.reason.toLowerCase()).toContain("impressions");
  });

  it("combines what_happened + why into the whatIsHappening slot", () => {
    const opp = translateDiagnostic(card())!;
    expect(opp.whatIsHappening).toContain("Family dinner reel");
    expect(opp.whatIsHappening).toContain("cheaper than the runner-up");
  });

  it("returns null when a required contract field is empty", () => {
    expect(translateDiagnostic(card({ recommendation: "" }))).toBeNull();
    expect(translateDiagnostic(card({ reason: "  " }))).toBeNull();
    expect(translateDiagnostic(card({ expected_result: "" }))).toBeNull();
  });

  it("returns null when confidence is out of range", () => {
    expect(translateDiagnostic(card({ confidence: -1 }))).toBeNull();
    expect(translateDiagnostic(card({ confidence: 101 }))).toBeNull();
    // NaN sneaks past TS because the type is `number`. Pin anyway.
    expect(translateDiagnostic(card({ confidence: NaN }))).toBeNull();
  });

  it("rounds non-integer confidence", () => {
    const opp = translateDiagnostic(card({ confidence: 74.6 }))!;
    expect(opp.confidence).toBe(75);
  });
});

// ---------------------------------------------------------------------
//  Technical details (Pro mode disclosure)
// ---------------------------------------------------------------------

describe("translateDiagnostic — technicalDetails", () => {
  it("surfaces money with the account currency, never hardcoded INR", () => {
    const opp = translateDiagnostic(
      card({
        evidence: {
          ...card().evidence,
          currency: "USD",
          spend: 250,
          cpl: 12.5,
        },
      }),
    )!;
    const details = opp.technicalDetails!;
    expect(String(details["Spend"])).toContain("USD");
    expect(String(details["Cost per lead"])).toContain("USD");
  });

  it("humanises tag values", () => {
    const opp = translateDiagnostic(card())!;
    const d = opp.technicalDetails!;
    expect(d["Concept family"]).toBe("family experience");
    expect(d["Audience"]).toBe("parents 25 45");
    expect(d["Offer"]).toBe("consultation");
  });

  it("omits 'Offer' when the offer_type is 'none'", () => {
    const opp = translateDiagnostic(
      card({ evidence: { ...card().evidence, offer_type: "none" } }),
    )!;
    expect(opp.technicalDetails!["Offer"]).toBeUndefined();
  });

  it("surfaces ROAS only when present", () => {
    const withRoas = translateDiagnostic(
      card({ evidence: { ...card().evidence, roas: 3.4 } }),
    )!;
    const withoutRoas = translateDiagnostic(card())!;
    expect(withRoas.technicalDetails!["ROAS"]).toBe("3.40x");
    expect(withoutRoas.technicalDetails!["ROAS"]).toBeUndefined();
  });

  it("surfaces reallocation fields for budget_reallocation cards", () => {
    const opp = translateDiagnostic(
      card({
        kind: "budget_reallocation",
        evidence: {
          winner_ref: "Family dinner reel",
          winner_currency: "INR",
          underperformer_ref: "Generic banner",
          cpl_ratio: 4.0,
        },
      }),
    )!;
    const d = opp.technicalDetails!;
    expect(d["Winning creative"]).toBe("Family dinner reel");
    expect(d["Underperforming creative"]).toBe("Generic banner");
    expect(d["Cost gap"]).toBe("4.0x");
  });
});

// ---------------------------------------------------------------------
//  Overview grouping
// ---------------------------------------------------------------------

function overview(over: Partial<PerformanceOverview> = {}): PerformanceOverview {
  return {
    has_data: true,
    rows_ingested: 30,
    creatives_tracked: 5,
    last_upload_at: "2026-06-01T10:00:00Z",
    diagnostics: [],
    ...over,
  };
}

describe("translateOverview", () => {
  it("sorts cards by confidence desc", () => {
    const r = translateOverview(
      overview({
        diagnostics: [
          card({ id: "lo", confidence: 50 }),
          card({ id: "hi", confidence: 88 }),
          card({ id: "mid", confidence: 70 }),
        ],
      }),
    );
    expect(r.cards.map((c) => c.id)).toEqual(["hi", "mid", "lo"]);
  });

  it("drops invalid cards instead of rendering 'undefined'", () => {
    const r = translateOverview(
      overview({
        diagnostics: [
          card({ id: "ok" }),
          card({ id: "broken", recommendation: "" }),
        ],
      }),
    );
    expect(r.cards.map((c) => c.id)).toEqual(["ok"]);
    expect(r.hasUsableCards).toBe(true);
  });

  it("reports hasUsableCards=false when nothing survives translation", () => {
    const r = translateOverview(
      overview({
        diagnostics: [card({ recommendation: "" }), card({ reason: "" })],
      }),
    );
    expect(r.hasUsableCards).toBe(false);
    expect(r.cards).toEqual([]);
  });

  it("hasUsableCards=false also when the brand has uploaded nothing", () => {
    const r = translateOverview(
      overview({ has_data: false, diagnostics: [], rows_ingested: 0 }),
    );
    expect(r.hasUsableCards).toBe(false);
  });
});

// ---------------------------------------------------------------------
//  9.1.5 — Section mapping for all new kinds
// ---------------------------------------------------------------------

describe("translateDiagnostic — 9.1.5 sections", () => {
  const cases: Array<[PerformanceDiagnosticCard["kind"], PerformanceSection]> = [
    ["winner", "baseline"],
    ["budget_reallocation", "baseline"],
    ["audience_winner", "audience"],
    ["audience_loser", "audience"],
    ["concept_winner", "creative"],
    ["emotion_winner", "creative"],
    ["funnel_winner", "creative"],
    ["pattern_winner", "creative"],
    ["offer_winner", "offer"],
    ["offer_pricing_sensitivity", "offer"],
    ["scale_candidate", "scaling"],
    ["budget_waste", "scaling"],
    ["creative_dna", "dna"],
  ];

  it.each(cases)("maps %s → section %s", (kind, section) => {
    const opp = translateDiagnostic(card({ kind, id: kind }))!;
    expect(opp.section).toBe(section);
  });
});

describe("groupBySection", () => {
  function opp(
    over: Partial<PerformanceOpportunity> & {
      kind: PerformanceDiagnosticCard["kind"];
      id: string;
    },
  ): PerformanceOpportunity {
    return {
      section: "baseline", // overridden by translator in real flow
      whatIsHappening: "x",
      impactCategory: "lead",
      recommendation: "x",
      expectedResult: "x",
      confidence: 70,
      reason: "x",
      ...over,
    } as PerformanceOpportunity;
  }

  it("groups cards by section in canonical order", () => {
    const cards = [
      opp({ kind: "winner", id: "w", section: "baseline" }),
      opp({ kind: "creative_dna", id: "d", section: "dna" }),
      opp({ kind: "scale_candidate", id: "s", section: "scaling" }),
      opp({ kind: "audience_winner", id: "a", section: "audience" }),
    ];
    const groups = groupBySection(cards);
    expect(groups.map((g) => g.section)).toEqual([
      "dna",
      "baseline",
      "scaling",
      "audience",
    ]);
  });

  it("omits empty sections", () => {
    const cards = [
      opp({ kind: "winner", id: "w", section: "baseline" }),
    ];
    const groups = groupBySection(cards);
    expect(groups).toHaveLength(1);
    expect(groups[0].section).toBe("baseline");
  });

  it("preserves confidence-desc inside a section", () => {
    const cards = [
      opp({ kind: "audience_winner", id: "lo", confidence: 60, section: "audience" }),
      opp({ kind: "audience_loser",  id: "hi", confidence: 80, section: "audience" }),
    ];
    // groupBySection preserves input order — sort happens upstream in
    // translateOverview. Pin that contract explicitly.
    const sorted = [...cards].sort((a, b) => b.confidence - a.confidence);
    const groups = groupBySection(sorted);
    expect(groups[0].cards.map((c) => c.id)).toEqual(["hi", "lo"]);
  });

  it("SECTION_ORDER puts DNA first because it's the apex card", () => {
    expect(SECTION_ORDER[0]).toBe("dna");
  });
});

// ---------------------------------------------------------------------
//  9.1.5 — Technical-detail extraction for new evidence shapes
// ---------------------------------------------------------------------

describe("translateDiagnostic — 9.1.5 technical details", () => {
  it("creative_dna spells out the 5-tag pattern", () => {
    const opp = translateDiagnostic(
      card({
        kind: "creative_dna",
        id: "d-1",
        evidence: {
          audience: "parents_25_45",
          concept_family: "family_experience",
          emotion: "warmth",
          offer_type: "consultation",
          funnel_stage: "conversion",
          creatives_count: 2,
          currency: "INR",
          cpl: 50,
        },
      }),
    )!;
    expect(opp.technicalDetails!["Winning pattern"]).toContain("parents 25 45");
    expect(opp.technicalDetails!["Winning pattern"]).toContain("family experience");
    expect(opp.technicalDetails!["Creatives in this pattern"]).toBe(2);
  });

  it("audience_loser surfaces the winning-audience comparison", () => {
    const opp = translateDiagnostic(
      card({
        kind: "audience_loser",
        id: "al-1",
        evidence: {
          audience: "executives",
          winner_audience: "parents",
          cpl: 500,
          cpl_ratio: 10,
          currency: "INR",
          spend: 2500,
        },
      }),
    )!;
    expect(opp.technicalDetails!["Audience group"]).toBe("executives");
    expect(opp.technicalDetails!["Winning audience"]).toBe("parents");
  });

  it("scale_candidate surfaces headroom and cheaper-than-average", () => {
    const opp = translateDiagnostic(
      card({
        kind: "scale_candidate",
        id: "s-1",
        evidence: {
          creative_ref: "Family reel A",
          cpl: 50,
          brand_avg_cpl: 150,
          cpl_advantage_ratio: 3.0,
          headroom_share: 0.7,
          currency: "INR",
          spend: 1000,
          conversions: 20,
        },
      }),
    )!;
    expect(opp.technicalDetails!["Cheaper than average by"]).toBe("3.0x");
    expect(opp.technicalDetails!["Headroom (unspent share)"]).toBe("70%");
  });

  it("budget_waste surfaces overrun + freed-leads estimate", () => {
    const opp = translateDiagnostic(
      card({
        kind: "budget_waste",
        id: "bw-1",
        evidence: {
          creative_ref: "Generic banner",
          cpl: 500,
          brand_avg_cpl: 100,
          cpl_overrun_ratio: 5.0,
          spend: 2500,
          spend_share: 0.4,
          freed_leads_estimate: 20,
          currency: "INR",
          conversions: 5,
        },
      }),
    )!;
    expect(opp.technicalDetails!["Cost overrun"]).toBe("5.0x average");
    expect(opp.technicalDetails!["Share of total spend"]).toBe("40%");
    expect(opp.technicalDetails!["Leads freed if shifted"]).toBe(20);
  });

  it("offer_winner surfaces conversion rate + offer label", () => {
    const opp = translateDiagnostic(
      card({
        kind: "offer_winner",
        id: "o-1",
        evidence: {
          offer_type: "consultation",
          runner_up_offer: "discount",
          cvr: 0.15,
          cvr_ratio: 3.0,
          currency: "INR",
          conversions: 30,
        },
      }),
    )!;
    expect(opp.technicalDetails!["Offer"]).toBe("consultation");
    expect(opp.technicalDetails!["Runner-up offer"]).toBe("discount");
    expect(opp.technicalDetails!["Conversion rate"]).toBe("15.0%");
    expect(opp.technicalDetails!["Conversion ratio"]).toBe("3.0x");
  });
});
