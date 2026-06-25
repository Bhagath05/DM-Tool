/**
 * Phase 10.0 — tests for the perf-card chip-derivation utility.
 *
 * Pins the honesty rules:
 *   - Priority maps deterministically to the confidence band.
 *   - Effort maps deterministically to the diagnostic kind.
 *   - Expected leads / revenue NEVER fabricate when evidence is absent.
 *   - Currency is taken from evidence, never hardcoded INR.
 */

import { describe, expect, it } from "vitest";

import { derive, priorityFromConfidence } from "@/lib/performance-derived";
import type { PerformanceOpportunity } from "@/lib/performance-translator";

function opp(
  over: Partial<PerformanceOpportunity> & {
    kind: PerformanceOpportunity["kind"];
  },
): PerformanceOpportunity {
  return {
    id: "x",
    section: "baseline",
    whatIsHappening: "x",
    impactCategory: "lead",
    recommendation: "x",
    expectedResult: "x",
    confidence: 80,
    reason: "x",
    evidence: {},
    ...over,
  } as PerformanceOpportunity;
}

describe("priorityFromConfidence", () => {
  it.each([
    [95, "HIGH"],
    [80, "HIGH"],
    [79, "MEDIUM"],
    [60, "MEDIUM"],
    [59, "LOW"],
    [0, "LOW"],
  ] as const)("%d -> %s", (c, expected) => {
    expect(priorityFromConfidence(c)).toBe(expected);
  });
});

describe("derive — Constitution discipline", () => {
  it("emits expected-leads from spend/cpl for scale_candidate", () => {
    const d = derive(
      opp({
        kind: "scale_candidate",
        confidence: 85,
        evidence: {
          spend: 2000,
          cpl: 50,
          conversions: 20,
          currency: "INR",
        },
      }),
    );
    expect(d.priority).toBe("HIGH");
    expect(d.effort).toBe("1 click");
    expect(d.expectedLeads).toBe("+40 leads");
  });

  it("uses freed_leads_estimate for budget_waste", () => {
    const d = derive(
      opp({
        kind: "budget_waste",
        confidence: 75,
        evidence: {
          freed_leads_estimate: 20,
          conversions: 5,
          currency: "INR",
        },
      }),
    );
    expect(d.expectedLeads).toBe("+20 leads");
    expect(d.priority).toBe("MEDIUM");
  });

  it("falls back to 'already delivered' framing for baseline winner", () => {
    const d = derive(
      opp({
        kind: "winner",
        evidence: { conversions: 30 },
      }),
    );
    // No forward-looking math for a single-creative winner; surface
    // what already happened rather than fabricate.
    expect(d.expectedLeads).toBe("30 delivered");
  });

  it("hides expected leads when no signal at all", () => {
    const d = derive(opp({ kind: "winner", evidence: {} }));
    expect(d.expectedLeads).toBeNull();
  });

  it("computes revenue impact with the row's currency, never hardcoded INR", () => {
    const d = derive(
      opp({
        kind: "scale_candidate",
        evidence: {
          spend: 1000,
          cpl: 25,
          conversions: 40,
          conversion_value: 4000, // value/lead = 100
          currency: "USD",
        },
      }),
    );
    // 1000 / 25 = 40 extra leads, × 100/lead = 4000 → "USD 4,000 potential"
    expect(d.revenueImpact).toBe("USD 4,000 potential");
    expect(d.revenueImpact).not.toContain("INR");
  });

  it("returns null revenue when no conversion_value present", () => {
    const d = derive(
      opp({
        kind: "scale_candidate",
        evidence: { spend: 1000, cpl: 25, conversions: 40, currency: "INR" },
      }),
    );
    expect(d.revenueImpact).toBeNull();
  });

  it("never fabricates revenue from a brand default", () => {
    // No conversion_value, no currency, no anything.
    const d = derive(opp({ kind: "audience_winner", evidence: {} }));
    expect(d.revenueImpact).toBeNull();
  });
});
