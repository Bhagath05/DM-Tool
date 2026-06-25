/**
 * Tests for the raw-KPI → BusinessMetric translator.
 *
 * The translator is the seam between raw analytics endpoints and the
 * Constitution-shaped cards. Confidence calibration, status banding,
 * and small-sample discipline live here — pin them.
 */

import { describe, expect, it } from "vitest";

import type { OverviewKpis, SourceRow } from "@/lib/api";
import {
  translateConversionRate,
  translateTopChannel,
  translateTotalLeads,
} from "./analytics-translator";

function kpis(over: Partial<OverviewKpis> = {}): OverviewKpis {
  return {
    total_leads: 0,
    leads_7d: 0,
    leads_30d: 0,
    hot_leads: 0,
    landing_pages_published: 0,
    total_views: 0,
    total_submissions: 0,
    conversion_rate: 0,
    top_landing_page_title: null,
    top_landing_page_slug: null,
    top_landing_page_submissions: 0,
    ...over,
  };
}

// ---------------------------------------------------------------------
//  translateTotalLeads
// ---------------------------------------------------------------------

describe("translateTotalLeads", () => {
  it("zero leads → bad status + 'publish a lead page' recommendation", () => {
    const m = translateTotalLeads(kpis({ leads_30d: 0 }));
    expect(m.status).toBe("bad");
    expect(m.value).toBe("0");
    expect(m.recommendation.toLowerCase()).toContain("publish");
    expect(m.impactCategory).toBe("lead");
    expect(m.confidence).toBe(90);
  });

  it("1-9 leads → neutral status + 'keep publishing' recommendation", () => {
    const m = translateTotalLeads(kpis({ leads_30d: 5 }));
    expect(m.status).toBe("neutral");
    expect(m.plainLanguage).toContain("5 people");
    expect(m.recommendation.toLowerCase()).toMatch(/publish|content/);
  });

  it("10-49 leads → good status + 'double down on top channel' recommendation", () => {
    const m = translateTotalLeads(kpis({ leads_30d: 25 }));
    expect(m.status).toBe("good");
    expect(m.recommendation.toLowerCase()).toMatch(/channel|double down/);
  });

  it("50+ leads → good status + 'focus on quality' recommendation", () => {
    const m = translateTotalLeads(kpis({ leads_30d: 120 }));
    expect(m.status).toBe("good");
    expect(m.recommendation.toLowerCase()).toMatch(/quality|hot/);
  });

  it("always passes the Constitution contract — non-empty required fields", () => {
    for (const n of [0, 1, 9, 10, 49, 50, 200]) {
      const m = translateTotalLeads(kpis({ leads_30d: n }));
      expect(m.value).toBeTruthy();
      expect(m.plainLanguage).toBeTruthy();
      expect(m.businessImpact).toBeTruthy();
      expect(m.recommendation).toBeTruthy();
      expect(m.expectedResult).toBeTruthy();
      expect(m.reason).toBeTruthy();
      expect(m.confidence).toBeGreaterThan(0);
      expect(m.confidence).toBeLessThanOrEqual(100);
    }
  });

  it("surfaces technical details with raw counts", () => {
    const m = translateTotalLeads(
      kpis({ leads_30d: 12, leads_7d: 3, total_leads: 40, hot_leads: 4 }),
    );
    expect(m.technicalDetails).toMatchObject({
      "Leads (30 days)": 12,
      "Leads (7 days)": 3,
      "Total leads (all time)": 40,
      "Hot leads": 4,
    });
  });
});

// ---------------------------------------------------------------------
//  translateConversionRate (small-sample discipline)
// ---------------------------------------------------------------------

describe("translateConversionRate", () => {
  it("returns null when views < 20 (small-sample discipline)", () => {
    expect(
      translateConversionRate(
        kpis({ total_views: 5, total_submissions: 2, conversion_rate: 0.4 }),
      ),
    ).toBeNull();
    expect(
      translateConversionRate(
        kpis({
          total_views: 19,
          total_submissions: 10,
          conversion_rate: 0.526,
        }),
      ),
    ).toBeNull();
  });

  it("renders when views >= 20", () => {
    const m = translateConversionRate(
      kpis({
        total_views: 100,
        total_submissions: 3,
        conversion_rate: 0.03,
      }),
    );
    expect(m).not.toBeNull();
    expect(m!.value).toBe("3%");
    expect(m!.plainLanguage).toContain("3 of every 100");
  });

  it("low conversion (<1%) → bad status + 'rewrite headline' recommendation", () => {
    const m = translateConversionRate(
      kpis({ total_views: 1000, total_submissions: 5, conversion_rate: 0.005 }),
    )!;
    expect(m.status).toBe("bad");
    expect(m.recommendation.toLowerCase()).toMatch(/headline|hook/);
  });

  it("healthy conversion (2-5%) → good status", () => {
    const m = translateConversionRate(
      kpis({
        total_views: 1000,
        total_submissions: 35,
        conversion_rate: 0.035,
      }),
    )!;
    expect(m.status).toBe("good");
    expect(m.recommendation.toLowerCase()).toContain("traffic");
  });

  it("exceptional conversion (>5%) → good status + scale traffic recommendation", () => {
    const m = translateConversionRate(
      kpis({
        total_views: 500,
        total_submissions: 50,
        conversion_rate: 0.1,
      }),
    )!;
    expect(m.status).toBe("good");
    expect(m.recommendation.toLowerCase()).toMatch(/traffic|scale|increase/);
  });

  it("confidence scales with sample size", () => {
    const small = translateConversionRate(
      kpis({ total_views: 25, total_submissions: 1, conversion_rate: 0.04 }),
    )!;
    const big = translateConversionRate(
      kpis({
        total_views: 500,
        total_submissions: 20,
        conversion_rate: 0.04,
      }),
    )!;
    expect(big.confidence).toBeGreaterThan(small.confidence);
  });

  it("reason mentions the actual sample sizes", () => {
    const m = translateConversionRate(
      kpis({
        total_views: 250,
        total_submissions: 8,
        conversion_rate: 0.032,
      }),
    )!;
    expect(m.reason).toContain("250");
    expect(m.reason).toContain("8");
  });
});

// ---------------------------------------------------------------------
//  translateTopChannel
// ---------------------------------------------------------------------

function src(over: Partial<SourceRow> = {}): SourceRow {
  return {
    source_asset_type: null,
    utm_source: null,
    utm_medium: null,
    utm_campaign: null,
    leads: 0,
    hot_leads: 0,
    ...over,
  };
}

describe("translateTopChannel", () => {
  it("returns null when no sources", () => {
    expect(translateTopChannel([])).toBeNull();
  });

  it("returns null when all sources have zero leads", () => {
    expect(
      translateTopChannel([
        src({ utm_source: "instagram", leads: 0 }),
        src({ utm_source: "facebook", leads: 0 }),
      ]),
    ).toBeNull();
  });

  it("picks the source with the most leads", () => {
    const rec = translateTopChannel([
      src({ utm_source: "instagram", leads: 3 }),
      src({ utm_source: "facebook", leads: 12 }),
      src({ utm_source: "linkedin", leads: 1 }),
    ])!;
    expect(rec.whatIsHappening).toContain("Facebook");
    expect(rec.recommendation).toContain("Facebook");
  });

  it("strong dominance (>=50%) triggers 'put extra time' recommendation", () => {
    const rec = translateTopChannel([
      src({ utm_source: "instagram", leads: 30 }),
      src({ utm_source: "facebook", leads: 5 }),
      src({ utm_source: "linkedin", leads: 5 }),
    ])!;
    expect(rec.whatIsHappening).toContain("#1");
    expect(rec.recommendation.toLowerCase()).toContain("extra time");
  });

  it("balanced mix (<50%) triggers an experiment recommendation", () => {
    const rec = translateTopChannel([
      src({ utm_source: "instagram", leads: 10 }),
      src({ utm_source: "facebook", leads: 9 }),
      src({ utm_source: "linkedin", leads: 8 }),
    ])!;
    expect(rec.recommendation.toLowerCase()).toMatch(/experiment|double/);
  });

  it("humanises channel labels", () => {
    const rec = translateTopChannel([
      src({ utm_source: "linkedin", leads: 5 }),
    ])!;
    expect(rec.whatIsHappening).toContain("LinkedIn"); // not "linkedin"
  });

  it("falls back to source_asset_type when no utm_source", () => {
    const rec = translateTopChannel([
      src({ source_asset_type: "content", leads: 5 }),
    ])!;
    expect(rec.whatIsHappening).toContain("Content");
  });

  it("technicalDetails carry the share + counts", () => {
    const rec = translateTopChannel([
      src({ utm_source: "instagram", leads: 8 }),
      src({ utm_source: "facebook", leads: 2 }),
    ])!;
    expect(rec.technicalDetails["Top channel"]).toBe("Instagram");
    expect(rec.technicalDetails["Top channel leads"]).toBe(8);
    expect(rec.technicalDetails["Top channel share"]).toBe("80%");
    expect(rec.technicalDetails["Total leads (sourced)"]).toBe(10);
  });

  it("contract: every field is non-empty + confidence in range", () => {
    const rec = translateTopChannel([
      src({ utm_source: "facebook", leads: 50 }),
    ])!;
    expect(rec.whatIsHappening).toBeTruthy();
    expect(rec.recommendation).toBeTruthy();
    expect(rec.expectedResult).toBeTruthy();
    expect(rec.reason).toBeTruthy();
    expect(rec.confidence).toBeGreaterThan(0);
    expect(rec.confidence).toBeLessThanOrEqual(100);
  });
});
