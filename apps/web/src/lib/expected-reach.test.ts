/**
 * Phase 10.4 — Expected Reach lib unit tests.
 *
 * Three concerns to pin:
 *   1. Confidence → band mapping honours the Constitution thresholds
 *      (80 / 60 / 40 — anything below is "speculative" and we must
 *      NOT pretend to predict reach).
 *   2. Reach band display string varies per platform and never lies
 *      ("Awaiting data" when input is null / low-confidence / unknown
 *      platform).
 *   3. `parseExpectedResult` tolerates the LLM's free-text shapes
 *      ("+15 leads", "₹15k–₹25k") without inventing data.
 */

import { describe, expect, it } from "vitest";

import {
  confidenceToReachBand,
  normalisePlatform,
  parseExpectedResult,
  reachBand,
} from "./expected-reach";


describe("confidenceToReachBand", () => {
  it("maps ≥80 to high", () => {
    expect(confidenceToReachBand(80)).toBe("high");
    expect(confidenceToReachBand(95)).toBe("high");
  });

  it("maps 60–79 to medium", () => {
    expect(confidenceToReachBand(60)).toBe("medium");
    expect(confidenceToReachBand(79)).toBe("medium");
  });

  it("maps 40–59 to low", () => {
    expect(confidenceToReachBand(40)).toBe("low");
    expect(confidenceToReachBand(59)).toBe("low");
  });

  it("maps <40 to unknown (Constitution: speculative — don't predict)", () => {
    expect(confidenceToReachBand(39)).toBe("unknown");
    expect(confidenceToReachBand(0)).toBe("unknown");
  });
});


describe("normalisePlatform", () => {
  it("returns the canonical key for known synonyms", () => {
    expect(normalisePlatform("instagram")).toBe("instagram");
    expect(normalisePlatform("IG")).toBe("instagram");
    expect(normalisePlatform("meta")).toBe("facebook");
    expect(normalisePlatform("FB")).toBe("facebook");
    expect(normalisePlatform("twitter")).toBe("twitter");
    expect(normalisePlatform("X")).toBe("twitter");
    expect(normalisePlatform("YouTube")).toBe("youtube");
  });

  it("returns null for unknown platforms (we don't fabricate a baseline)", () => {
    expect(normalisePlatform("pinterest")).toBeNull();
    expect(normalisePlatform("snapchat")).toBeNull();
    expect(normalisePlatform("google_search")).toBeNull();
    expect(normalisePlatform(null)).toBeNull();
    expect(normalisePlatform(undefined)).toBeNull();
  });
});


describe("reachBand", () => {
  it("returns 'Awaiting data' when confidence is speculative", () => {
    const r = reachBand({ platform: "instagram", confidence: 30 });
    expect(r.display).toBe("Awaiting data");
    expect(r.band).toBe("unknown");
    expect(r.source).toBe("unknown");
  });

  it("returns 'Awaiting data' when platform is unknown", () => {
    const r = reachBand({ platform: "pinterest", confidence: 90 });
    expect(r.display).toBe("Awaiting data");
    expect(r.source).toBe("unknown");
  });

  it("returns the high band for high-confidence + known platform", () => {
    const r = reachBand({ platform: "instagram", confidence: 90 });
    expect(r.band).toBe("high");
    expect(r.display).toBe("10k–18k");
    expect(r.source).toBe("baseline");
  });

  it("marks source as 'personalised' when pattern data exists", () => {
    const r = reachBand({
      platform: "linkedin",
      confidence: 85,
      hasPattern: true,
    });
    expect(r.source).toBe("personalised");
  });

  it("differentiates bands across platforms (TikTok > LinkedIn)", () => {
    const li = reachBand({ platform: "linkedin", confidence: 90 });
    const tt = reachBand({ platform: "tiktok", confidence: 90 });
    // Both high band, but TikTok's baseline is much larger by industry norm.
    expect(li.display).not.toEqual(tt.display);
  });
});


describe("parseExpectedResult", () => {
  it("returns nulls on empty input", () => {
    expect(parseExpectedResult(null)).toEqual({
      leads: null,
      revenue: null,
      summary: null,
    });
    expect(parseExpectedResult("")).toEqual({
      leads: null,
      revenue: null,
      summary: null,
    });
  });

  it("extracts a +N leads phrase", () => {
    const r = parseExpectedResult("Expected: +15 leads next week");
    expect(r.leads).toBe("+15 leads");
  });

  it("extracts a ranged leads phrase", () => {
    const r = parseExpectedResult("+15–25 leads in 14 days");
    expect(r.leads).toContain("15");
    expect(r.leads).toContain("25");
    expect(r.leads).toContain("leads");
  });

  it("extracts a revenue range (₹)", () => {
    const r = parseExpectedResult(
      "Could add ₹15,000-₹25,000 in revenue this month",
    );
    expect(r.revenue).toContain("₹15,000");
    expect(r.revenue).toContain("₹25,000");
  });

  it("extracts a single revenue figure ($)", () => {
    const r = parseExpectedResult("Adds $2k of pipeline");
    expect(r.revenue).toContain("$2k");
  });

  it("falls back to summary when nothing parses", () => {
    const r = parseExpectedResult(
      "Warmer audience, qualified leads more likely",
    );
    expect(r.leads).toBeNull();
    expect(r.revenue).toBeNull();
    expect(r.summary).toContain("Warmer audience");
  });
});
