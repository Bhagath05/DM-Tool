/**
 * Posting Time Intelligence — typed structure + parser + placeholder.
 *
 * Per Phase 10.3c directive: **no hardcoded "best times"**. This module
 * provides the data shape that posting-time recommendations live in,
 * plus two source paths:
 *
 *   1. `deriveFromPatterns(patterns)` — parse `WinningPattern.posting_time_pattern`
 *      strings (e.g. "Tuesday 8 AM, Thursday 11 AM") into structured
 *      windows. The backend stores these as free text today because
 *      that's how the LLM emits them; we structure them at the edge.
 *
 *   2. `placeholderPlan(day)` — industry-norm windows the founder
 *      sees when no patterns exist yet. Marked `source: "placeholder"`
 *      so the UI can show "estimated based on industry norms — connect
 *      a handle to personalise". Honest, never lies.
 *
 * When the backend ships a real posting-time endpoint, swap the data
 * source — the schema doesn't change.
 */

import type { SocialPlatform, WinningPattern } from "./api";

// ---------------------------------------------------------------------
//  Types
// ---------------------------------------------------------------------

export type Weekday =
  | "Mon"
  | "Tue"
  | "Wed"
  | "Thu"
  | "Fri"
  | "Sat"
  | "Sun";

/** A single posting window. All numbers are 0-bounded for safety. */
export interface TimeWindow {
  /** 0–23 */
  start_hour: number;
  /** 0 / 15 / 30 / 45 — quarter-hour granularity is enough for marketing */
  start_minute: 0 | 15 | 30 | 45;
  /** 0–100, how confident the engine is in this window */
  confidence_score: number;
  /** 0–100, historical engagement strength at this window */
  engagement_score: number;
}

/**
 * One platform's posting plan for one day. A platform can have multiple
 * windows (early-morning + lunch + evening, etc.).
 */
export interface PlatformPostingPlan {
  platform: SocialPlatform | "twitter";
  day: Weekday;
  windows: TimeWindow[];
  /**
   * Where this plan came from. The UI surfaces a footnote when source
   * is "placeholder" so a founder never mistakes industry-norm guesses
   * for personalised intelligence.
   */
  source: "derived" | "placeholder";
}

// ---------------------------------------------------------------------
//  Industry-norm placeholders
// ---------------------------------------------------------------------
//
// Sourced from widely-cited Buffer / Hootsuite / Sprout Social public
// benchmarks (2024 averages). These are NOT presented as "best times
// for you" — the UI labels them as estimated industry norms. When the
// founder connects a social handle and the LLM extracts real patterns,
// `deriveFromPatterns` takes over.

const PLACEHOLDER_BY_PLATFORM: Record<
  PlatformPostingPlan["platform"],
  TimeWindow[]
> = {
  instagram: [
    { start_hour: 11, start_minute: 0, confidence_score: 55, engagement_score: 60 },
    { start_hour: 14, start_minute: 0, confidence_score: 50, engagement_score: 55 },
    { start_hour: 19, start_minute: 0, confidence_score: 60, engagement_score: 65 },
  ],
  linkedin: [
    { start_hour: 8, start_minute: 30, confidence_score: 60, engagement_score: 65 },
    { start_hour: 12, start_minute: 0, confidence_score: 55, engagement_score: 55 },
    { start_hour: 17, start_minute: 30, confidence_score: 50, engagement_score: 50 },
  ],
  facebook: [
    { start_hour: 13, start_minute: 0, confidence_score: 50, engagement_score: 50 },
    { start_hour: 18, start_minute: 0, confidence_score: 55, engagement_score: 55 },
  ],
  twitter: [
    { start_hour: 9, start_minute: 0, confidence_score: 50, engagement_score: 55 },
    { start_hour: 15, start_minute: 0, confidence_score: 50, engagement_score: 55 },
  ],
  tiktok: [
    { start_hour: 18, start_minute: 0, confidence_score: 50, engagement_score: 60 },
    { start_hour: 21, start_minute: 0, confidence_score: 55, engagement_score: 65 },
  ],
  youtube: [
    { start_hour: 15, start_minute: 0, confidence_score: 50, engagement_score: 55 },
    { start_hour: 20, start_minute: 0, confidence_score: 55, engagement_score: 60 },
  ],
};

/**
 * Generate placeholder posting plans for every supported platform on
 * the given day. UI marks them as "industry norm" so the founder
 * knows they're not personalised yet.
 */
export function placeholderPlans(day: Weekday): PlatformPostingPlan[] {
  return (
    Object.keys(PLACEHOLDER_BY_PLATFORM) as PlatformPostingPlan["platform"][]
  ).map((platform) => ({
    platform,
    day,
    windows: PLACEHOLDER_BY_PLATFORM[platform],
    source: "placeholder",
  }));
}

// ---------------------------------------------------------------------
//  Parser — extract structured windows from free-text patterns
// ---------------------------------------------------------------------
//
// `WinningPattern.posting_time_pattern` is whatever the LLM emits.
// Typical shapes:
//
//   "Tuesday 8 AM, Thursday 11 AM"
//   "Weekdays around 6 PM"
//   "Mornings 8–10 AM"
//
// We extract `<weekday-name>? <hour>(:<minute>)? (am|pm)?` clauses
// best-effort. Anything we can't confidently parse is skipped — better
// to under-surface than show garbage. Confidence is anchored to the
// pattern's `performance_score`.

const WEEKDAY_NORMAL: Record<string, Weekday> = {
  mon: "Mon", monday: "Mon",
  tue: "Tue", tues: "Tue", tuesday: "Tue",
  wed: "Wed", weds: "Wed", wednesday: "Wed",
  thu: "Thu", thur: "Thu", thurs: "Thu", thursday: "Thu",
  fri: "Fri", friday: "Fri",
  sat: "Sat", saturday: "Sat",
  sun: "Sun", sunday: "Sun",
};

interface ParsedClause {
  day: Weekday | null;
  hour: number;
  minute: 0 | 15 | 30 | 45;
}

/**
 * Parse the free-text `posting_time_pattern` into 0..N concrete
 * day+time clauses. Exposed for unit testing.
 */
export function parsePostingTimeText(text: string): ParsedClause[] {
  if (!text) return [];

  // Split on commas / semicolons / "and" / newlines. Treat each chunk
  // as a potential clause.
  const chunks = text
    .toLowerCase()
    .split(/,|;|\band\b|\n/g)
    .map((c) => c.trim())
    .filter(Boolean);

  const out: ParsedClause[] = [];
  for (const chunk of chunks) {
    // Day name (optional). Word boundary so "fri" doesn't match "friday"
    // twice.
    const dayMatch = chunk.match(
      /\b(mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/,
    );
    const day = dayMatch ? WEEKDAY_NORMAL[dayMatch[1]] : null;

    // Time: "8 AM" / "8:30 PM" / "20:00" / "8pm"
    const timeMatch = chunk.match(
      /(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b/,
    );
    if (!timeMatch) continue;

    let hour = parseInt(timeMatch[1], 10);
    const minuteRaw = timeMatch[2] ? parseInt(timeMatch[2], 10) : 0;
    const ampm = timeMatch[3];

    if (Number.isNaN(hour) || hour < 0 || hour > 23) continue;

    if (ampm === "pm" && hour < 12) hour += 12;
    if (ampm === "am" && hour === 12) hour = 0;

    // Snap minute to 15-minute bucket — keeps the structure tidy.
    const minute = snapMinute(minuteRaw);

    out.push({ day, hour, minute });
  }
  return out;
}

function snapMinute(m: number): 0 | 15 | 30 | 45 {
  // Nearest 15-minute bucket. Clamps at 45 rather than wrapping to 0
  // — wrapping would silently bump the *hour* without us tracking it,
  // so we'd report 8:00 when the source said 8:53. Wrong direction.
  if (m < 8) return 0;
  if (m < 23) return 15;
  if (m < 38) return 30;
  return 45;
}

/**
 * Build PlatformPostingPlans from a list of WinningPatterns.
 *
 *   - Patterns without a `posting_time_pattern` are skipped.
 *   - Patterns with `platform: null` are skipped (can't bucket them).
 *   - Patterns with `platform: "tiktok" | "youtube"` are kept (the
 *     UI may filter them out, but the structure tolerates them).
 *   - Multiple windows per (platform, day) are de-duplicated by hour.
 *
 * Confidence + engagement scores are anchored to the source pattern's
 * `performance_score` (which is 0–100 by backend contract).
 */
export function deriveFromPatterns(
  patterns: WinningPattern[],
): PlatformPostingPlan[] {
  // Map of "<platform>|<day>" → windows being collected
  const buckets = new Map<string, { plan: PlatformPostingPlan; seen: Set<string> }>();

  for (const p of patterns) {
    if (!p.platform) continue;
    if (!p.posting_time_pattern) continue;
    const clauses = parsePostingTimeText(p.posting_time_pattern);
    for (const clause of clauses) {
      // Patterns without an explicit day apply to "every weekday" —
      // bucket them under each Mon-Fri so the UI can render them
      // on the active day.
      const days: Weekday[] = clause.day
        ? [clause.day]
        : ["Mon", "Tue", "Wed", "Thu", "Fri"];
      for (const day of days) {
        const key = `${p.platform}|${day}`;
        let bucket = buckets.get(key);
        if (!bucket) {
          bucket = {
            plan: {
              platform: p.platform,
              day,
              windows: [],
              source: "derived",
            },
            seen: new Set(),
          };
          buckets.set(key, bucket);
        }
        const windowKey = `${clause.hour}:${clause.minute}`;
        if (bucket.seen.has(windowKey)) continue;
        bucket.seen.add(windowKey);
        bucket.plan.windows.push({
          start_hour: clause.hour,
          start_minute: clause.minute,
          confidence_score: p.performance_score,
          engagement_score: p.performance_score,
        });
      }
    }
  }
  return Array.from(buckets.values()).map((b) => b.plan);
}

// ---------------------------------------------------------------------
//  Public helpers
// ---------------------------------------------------------------------

/** Today's weekday short label. */
export function todayWeekday(now: Date = new Date()): Weekday {
  const days: Weekday[] = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return days[now.getDay()];
}

/** Format a TimeWindow as "11:00" / "8:30" for display. */
export function formatWindow(w: TimeWindow): string {
  const h = String(w.start_hour).padStart(2, "0");
  const m = String(w.start_minute).padStart(2, "0");
  return `${h}:${m}`;
}

/**
 * Combine derived + placeholder so every supported platform always
 * has a plan for `day`. Derived plans win when they exist; placeholders
 * fill in for platforms the founder hasn't connected. Result is always
 * the same length (one row per supported platform) for stable layout.
 */
export function planForDay(
  patterns: WinningPattern[],
  day: Weekday,
): PlatformPostingPlan[] {
  const derived = deriveFromPatterns(patterns).filter((p) => p.day === day);
  const derivedPlatforms = new Set(derived.map((p) => p.platform));
  const placeholders = placeholderPlans(day).filter(
    (p) => !derivedPlatforms.has(p.platform),
  );
  return [...derived, ...placeholders];
}
