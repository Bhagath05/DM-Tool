/**
 * Phase 10.4 — Recommendation Engine unit tests.
 *
 * Pin the three pivot functions:
 *   - topPostPerPlatform: returns 4 slots, never leaks reels, picks
 *     by confidence DESC
 *   - topAdPerFormat: returns 3 slots (Meta, Google, LinkedIn), exact
 *     format match
 *   - topReels: picks reel-formatted opportunities from both arrays,
 *     bounded by limit
 */

import { describe, expect, it } from "vitest";

import type { Opportunity, OpportunityCenterReport } from "./api";
import {
  adFormatLabel,
  isReelOpportunity,
  postPlatformLabel,
  topAdPerFormat,
  topPostPerPlatform,
  topReels,
} from "./recommendation-engine";


function makeOpp(over: Partial<Opportunity> & { id: string }): Opportunity {
  const defaults: Opportunity = {
    id: "default",
    kind: "content",
    headline: "x",
    what_is_happening: "x",
    why_it_matters: "x",
    recommended_action: "x",
    expected_result: "x",
    confidence: 80,
    reason: "x",
    impact_category: "lead",
    evidence: [],
    generator: {
      target: "content",
      format: "social_post",
      platform: "instagram",
      goal: "leads",
      objective: null,
    },
  };
  // Spread `over` last so `id` (and any other override) wins.
  return { ...defaults, ...over };
}

function makeReport(
  content: Opportunity[] = [],
  ads: Opportunity[] = [],
): OpportunityCenterReport {
  return {
    headline: "x",
    hero_recommendation: {
      what_is_happening: "x",
      impact_category: "lead",
      recommendation: "x",
      expected_result: "x",
      confidence: 70,
      reason: "x",
    },
    content_opportunities: content,
    ad_opportunities: ads,
    skip_for_now: [],
    signals_used: [],
    generated_at: "2026-06-08T00:00:00Z",
  };
}


describe("topPostPerPlatform", () => {
  it("returns 4 slots even when report is null (UI grid stays stable)", () => {
    const slots = topPostPerPlatform(null);
    expect(slots).toHaveLength(4);
    expect(slots.map((s) => s.platform)).toEqual([
      "instagram",
      "linkedin",
      "facebook",
      "twitter",
    ]);
    expect(slots.every((s) => s.opportunity === null)).toBe(true);
  });

  it("picks the highest-confidence opportunity per platform", () => {
    const report = makeReport([
      makeOpp({
        id: "ig-low",
        confidence: 60,
        generator: {
          target: "content",
          format: "social_post",
          platform: "instagram",
          goal: "leads",
          objective: null,
        },
      }),
      makeOpp({
        id: "ig-high",
        confidence: 90,
        generator: {
          target: "content",
          format: "social_post",
          platform: "instagram",
          goal: "leads",
          objective: null,
        },
      }),
      makeOpp({
        id: "li-1",
        confidence: 75,
        generator: {
          target: "content",
          format: "carousel",
          platform: "linkedin",
          goal: "leads",
          objective: null,
        },
      }),
    ]);
    const slots = topPostPerPlatform(report);
    const ig = slots.find((s) => s.platform === "instagram");
    const li = slots.find((s) => s.platform === "linkedin");
    expect(ig?.opportunity?.id).toBe("ig-high");
    expect(li?.opportunity?.id).toBe("li-1");
  });

  it("EXCLUDES reel-formatted opportunities (reels live elsewhere)", () => {
    const report = makeReport([
      makeOpp({
        id: "reel-1",
        confidence: 95,
        generator: {
          target: "content",
          format: "reel",
          platform: "instagram",
          goal: "engagement",
          objective: null,
        },
      }),
    ]);
    const slots = topPostPerPlatform(report);
    expect(slots.find((s) => s.platform === "instagram")?.opportunity).toBeNull();
  });

  it("leaves the slot null when no opportunity targets that platform", () => {
    const report = makeReport([
      makeOpp({
        id: "fb-only",
        generator: {
          target: "content",
          format: "social_post",
          platform: "facebook",
          goal: "leads",
          objective: null,
        },
      }),
    ]);
    const slots = topPostPerPlatform(report);
    expect(slots.find((s) => s.platform === "instagram")?.opportunity).toBeNull();
    expect(slots.find((s) => s.platform === "facebook")?.opportunity?.id).toBe(
      "fb-only",
    );
  });
});


describe("topAdPerFormat", () => {
  it("returns the 3 supported formats (Meta, Google Search, LinkedIn)", () => {
    const slots = topAdPerFormat(null);
    expect(slots.map((s) => s.format)).toEqual([
      "meta",
      "google_search",
      "linkedin",
    ]);
  });

  it("picks the highest-confidence ad per format", () => {
    const report = makeReport(
      [],
      [
        makeOpp({
          id: "meta-1",
          confidence: 70,
          generator: {
            target: "ad",
            format: "meta",
            platform: "meta",
            goal: "leads",
            objective: "leads",
          },
        }),
        makeOpp({
          id: "meta-2",
          confidence: 88,
          generator: {
            target: "ad",
            format: "meta",
            platform: "meta",
            goal: "leads",
            objective: "leads",
          },
        }),
        makeOpp({
          id: "google-1",
          confidence: 81,
          generator: {
            target: "ad",
            format: "google_search",
            platform: "google",
            goal: "traffic",
            objective: "leads",
          },
        }),
      ],
    );
    const slots = topAdPerFormat(report);
    expect(slots.find((s) => s.format === "meta")?.opportunity?.id).toBe(
      "meta-2",
    );
    expect(
      slots.find((s) => s.format === "google_search")?.opportunity?.id,
    ).toBe("google-1");
    expect(slots.find((s) => s.format === "linkedin")?.opportunity).toBeNull();
  });

  it("does NOT match instagram_promo to any ad slot", () => {
    const report = makeReport(
      [],
      [
        makeOpp({
          id: "promo",
          confidence: 95,
          generator: {
            target: "ad",
            format: "instagram_promo",
            platform: "instagram",
            goal: "engagement",
            objective: "engagement",
          },
        }),
      ],
    );
    const slots = topAdPerFormat(report);
    expect(slots.every((s) => s.opportunity === null)).toBe(true);
  });
});


describe("topReels", () => {
  it("returns [] for null report", () => {
    expect(topReels(null)).toEqual([]);
  });

  it("picks reel-formatted opportunities across both arrays", () => {
    const report = makeReport(
      [
        makeOpp({
          id: "content-reel",
          confidence: 70,
          generator: {
            target: "content",
            format: "reel",
            platform: "instagram",
            goal: "engagement",
            objective: null,
          },
        }),
      ],
      [
        makeOpp({
          id: "ad-reel-script",
          confidence: 85,
          generator: {
            target: "ad",
            format: "short_video_script",
            platform: "tiktok",
            goal: "awareness",
            objective: "awareness",
          },
        }),
      ],
    );
    const reels = topReels(report);
    expect(reels.map((r) => r.id)).toEqual(["ad-reel-script", "content-reel"]);
  });

  it("honours the limit parameter", () => {
    const report = makeReport(
      Array.from({ length: 5 }).map((_, i) =>
        makeOpp({
          id: `reel-${i}`,
          confidence: 50 + i * 5,
          generator: {
            target: "content",
            format: "reel",
            platform: "instagram",
            goal: "engagement",
            objective: null,
          },
        }),
      ),
    );
    expect(topReels(report, 3)).toHaveLength(3);
  });

  it("excludes non-reel formats", () => {
    const report = makeReport([
      makeOpp({
        id: "carousel",
        generator: {
          target: "content",
          format: "carousel",
          platform: "instagram",
          goal: "leads",
          objective: null,
        },
      }),
    ]);
    expect(topReels(report)).toEqual([]);
  });
});


describe("isReelOpportunity", () => {
  it("detects 'reel' format", () => {
    expect(isReelOpportunity(makeOpp({
      id: "x",
      generator: {
        target: "content",
        format: "reel",
        platform: "instagram",
        goal: "engagement",
        objective: null,
      },
    }))).toBe(true);
  });

  it("detects 'short_video_script' format", () => {
    expect(isReelOpportunity(makeOpp({
      id: "x",
      generator: {
        target: "content",
        format: "short_video_script",
        platform: "tiktok",
        goal: "awareness",
        objective: null,
      },
    }))).toBe(true);
  });

  it("rejects non-reel formats", () => {
    expect(isReelOpportunity(makeOpp({
      id: "x",
      generator: {
        target: "content",
        format: "carousel",
        platform: "linkedin",
        goal: "leads",
        objective: null,
      },
    }))).toBe(false);
  });
});


describe("labels", () => {
  it("adFormatLabel renders founder-friendly names", () => {
    expect(adFormatLabel("meta")).toBe("Meta Ad");
    expect(adFormatLabel("google_search")).toBe("Google Search Ad");
    expect(adFormatLabel("linkedin")).toBe("LinkedIn Ad");
  });

  it("postPlatformLabel renders founder-friendly names", () => {
    expect(postPlatformLabel("instagram")).toBe("Instagram");
    expect(postPlatformLabel("twitter")).toBe("Twitter / X");
  });
});
