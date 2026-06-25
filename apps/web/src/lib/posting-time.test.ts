/**
 * Phase 10.3c — Posting Time Intelligence unit tests.
 *
 * Pin three things:
 *   1. The parser tolerates the messy free-text shapes the LLM emits
 *      ("Tuesday 8 AM", "Weekdays 6 PM", "20:00") and rejects garbage.
 *   2. Derivation from WinningPatterns honours platform isolation —
 *      a LinkedIn pattern never leaks into Instagram's plan.
 *   3. planForDay() always returns one row per supported platform,
 *      with derived plans taking precedence over placeholders.
 */

import { describe, expect, it } from "vitest";

import type { WinningPattern } from "./api";
import {
  deriveFromPatterns,
  formatWindow,
  parsePostingTimeText,
  placeholderPlans,
  planForDay,
  todayWeekday,
} from "./posting-time";


function pattern(over: Partial<WinningPattern> = {}): WinningPattern {
  return {
    id: "p1",
    platform: "instagram",
    summary: "summary",
    hook_pattern: null,
    visual_pattern: null,
    caption_pattern: null,
    cta_pattern: null,
    format_pattern: null,
    posting_time_pattern: "Tuesday 8 AM",
    performance_score: 75,
    source_asset_ids: [],
    created_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}


describe("parsePostingTimeText", () => {
  it("returns nothing on empty input", () => {
    expect(parsePostingTimeText("")).toEqual([]);
  });

  it("parses a single Tuesday 8 AM clause", () => {
    expect(parsePostingTimeText("Tuesday 8 AM")).toEqual([
      { day: "Tue", hour: 8, minute: 0 },
    ]);
  });

  it("parses comma-separated multi-clause text", () => {
    const r = parsePostingTimeText("Tuesday 8 AM, Thursday 11 AM");
    expect(r).toHaveLength(2);
    expect(r[0]).toEqual({ day: "Tue", hour: 8, minute: 0 });
    expect(r[1]).toEqual({ day: "Thu", hour: 11, minute: 0 });
  });

  it("handles 'and' as a separator", () => {
    const r = parsePostingTimeText("Mon 9 AM and Fri 5 PM");
    expect(r).toHaveLength(2);
    expect(r[0].day).toBe("Mon");
    expect(r[1].day).toBe("Fri");
    expect(r[1].hour).toBe(17);
  });

  it("converts PM correctly (8 PM → 20)", () => {
    expect(parsePostingTimeText("8 PM")).toEqual([
      { day: null, hour: 20, minute: 0 },
    ]);
  });

  it("converts 12 AM → 0", () => {
    expect(parsePostingTimeText("12 AM")).toEqual([
      { day: null, hour: 0, minute: 0 },
    ]);
  });

  it("snaps minutes to quarter-hour buckets", () => {
    // Buckets: 0-7 → 0, 8-22 → 15, 23-37 → 30, 38+ → 45 (clamped, no
    // hour wrap — see snapMinute() docstring).
    expect(parsePostingTimeText("8:17 AM")[0]?.minute).toBe(15);
    expect(parsePostingTimeText("8:38 AM")[0]?.minute).toBe(45);
    expect(parsePostingTimeText("8:53 AM")[0]?.minute).toBe(45);
    expect(parsePostingTimeText("8:23 AM")[0]?.minute).toBe(30);
    expect(parsePostingTimeText("8:07 AM")[0]?.minute).toBe(0);
  });

  it("accepts 24-hour times", () => {
    expect(parsePostingTimeText("20:30")).toEqual([
      { day: null, hour: 20, minute: 30 },
    ]);
  });

  it("rejects garbage hours", () => {
    expect(parsePostingTimeText("25 PM")).toEqual([]);
  });

  it("works with no day name (returns day=null)", () => {
    expect(parsePostingTimeText("5 PM")).toEqual([
      { day: null, hour: 17, minute: 0 },
    ]);
  });

  it("returns empty when no recognisable time is present", () => {
    expect(parsePostingTimeText("sometime mid-morning")).toEqual([]);
  });
});


describe("deriveFromPatterns", () => {
  it("returns empty when given no patterns", () => {
    expect(deriveFromPatterns([])).toEqual([]);
  });

  it("skips patterns without a platform", () => {
    expect(
      deriveFromPatterns([pattern({ platform: null })]),
    ).toEqual([]);
  });

  it("skips patterns without a posting_time_pattern", () => {
    expect(
      deriveFromPatterns([pattern({ posting_time_pattern: null })]),
    ).toEqual([]);
  });

  it("buckets a single Tuesday 8 AM Instagram pattern correctly", () => {
    const plans = deriveFromPatterns([
      pattern({ platform: "instagram", posting_time_pattern: "Tuesday 8 AM" }),
    ]);
    expect(plans).toHaveLength(1);
    expect(plans[0]).toMatchObject({
      platform: "instagram",
      day: "Tue",
      source: "derived",
    });
    expect(plans[0].windows).toEqual([
      {
        start_hour: 8,
        start_minute: 0,
        confidence_score: 75,
        engagement_score: 75,
      },
    ]);
  });

  it("does NOT leak a LinkedIn pattern into Instagram's plan", () => {
    const plans = deriveFromPatterns([
      pattern({ platform: "linkedin", posting_time_pattern: "Mon 9 AM" }),
    ]);
    expect(plans.every((p) => p.platform === "linkedin")).toBe(true);
  });

  it("expands a no-day pattern across Mon-Fri", () => {
    const plans = deriveFromPatterns([
      pattern({ platform: "linkedin", posting_time_pattern: "5 PM" }),
    ]);
    const days = plans.map((p) => p.day).sort();
    expect(days).toEqual(["Fri", "Mon", "Thu", "Tue", "Wed"]);
  });

  it("de-duplicates identical windows for the same (platform, day)", () => {
    const plans = deriveFromPatterns([
      pattern({
        platform: "instagram",
        posting_time_pattern: "Tuesday 8 AM, Tuesday 8 AM, Tuesday 8 AM",
      }),
    ]);
    expect(plans).toHaveLength(1);
    expect(plans[0].windows).toHaveLength(1);
  });

  it("anchors confidence_score to performance_score", () => {
    const plans = deriveFromPatterns([
      pattern({
        platform: "facebook",
        posting_time_pattern: "Wed 1 PM",
        performance_score: 88,
      }),
    ]);
    expect(plans[0].windows[0].confidence_score).toBe(88);
    expect(plans[0].windows[0].engagement_score).toBe(88);
  });
});


describe("placeholderPlans", () => {
  it("returns one plan per supported platform", () => {
    const plans = placeholderPlans("Mon");
    const platforms = plans.map((p) => p.platform).sort();
    expect(platforms).toEqual([
      "facebook",
      "instagram",
      "linkedin",
      "tiktok",
      "twitter",
      "youtube",
    ]);
  });

  it("marks every plan as source=placeholder", () => {
    for (const plan of placeholderPlans("Tue")) {
      expect(plan.source).toBe("placeholder");
    }
  });

  it("provides at least one window per platform", () => {
    for (const plan of placeholderPlans("Fri")) {
      expect(plan.windows.length).toBeGreaterThan(0);
    }
  });
});


describe("planForDay", () => {
  it("falls back to placeholders for every platform when no patterns", () => {
    const plans = planForDay([], "Mon");
    // All 6 supported platforms come back as placeholders.
    expect(plans).toHaveLength(6);
    expect(plans.every((p) => p.source === "placeholder")).toBe(true);
  });

  it("uses the derived plan when available (and placeholder for the rest)", () => {
    const plans = planForDay(
      [pattern({ platform: "instagram", posting_time_pattern: "Mon 10 AM" })],
      "Mon",
    );
    const ig = plans.find((p) => p.platform === "instagram");
    expect(ig?.source).toBe("derived");
    const others = plans.filter((p) => p.platform !== "instagram");
    expect(others.every((p) => p.source === "placeholder")).toBe(true);
  });

  it("filters by day — a Tuesday-only pattern does not appear on Monday", () => {
    const plans = planForDay(
      [pattern({ platform: "instagram", posting_time_pattern: "Tuesday 8 AM" })],
      "Mon",
    );
    const ig = plans.find((p) => p.platform === "instagram");
    expect(ig?.source).toBe("placeholder");
  });
});


describe("formatWindow + todayWeekday", () => {
  it("formats single-digit hours/minutes with leading zero", () => {
    expect(
      formatWindow({
        start_hour: 8,
        start_minute: 0,
        confidence_score: 0,
        engagement_score: 0,
      }),
    ).toBe("08:00");
  });

  it("formats 24-hour times", () => {
    expect(
      formatWindow({
        start_hour: 20,
        start_minute: 30,
        confidence_score: 0,
        engagement_score: 0,
      }),
    ).toBe("20:30");
  });

  it("returns the correct weekday short label", () => {
    expect(todayWeekday(new Date("2026-06-08T12:00:00Z"))).toBe("Mon");
    expect(todayWeekday(new Date("2026-06-12T12:00:00Z"))).toBe("Fri");
  });
});
