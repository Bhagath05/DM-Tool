/**
 * Phase 10.4 — Action Scoring Engine.
 *
 * Every Command Center card surfaces the same 6 measures so the founder
 * can compare apples-to-apples across opportunities, weekly actions,
 * and lead priorities:
 *
 *     confidence       — 0-100 (Constitution contract)
 *     expectedReach    — band string ("12k+", "Awaiting data")
 *     expectedLeads    — parsed from expected_result
 *     expectedRevenue  — parsed from expected_result
 *     difficulty       — "easy" | "medium" | "hard" (derived from format)
 *     timeRequired     — string ("10 mins", "1 hr")
 *
 * This module normalises three different backend shapes
 * (Opportunity, WeeklyAction, LeadPriorityItem) into a single
 * `ScoredAction` shape so the cards share one renderer.
 */

import type {
  LeadPriorityItem,
  Opportunity,
  WeeklyAction,
} from "./api";
import {
  parseExpectedResult,
  reachBand,
  type ReachBand,
} from "./expected-reach";

export type Difficulty = "easy" | "medium" | "hard";

export interface ScoredAction {
  /** Source shape — for icon/colour decisions. */
  source: "opportunity" | "weekly_action" | "lead_priority";
  confidence: number;
  expectedReach: { display: string; band: ReachBand };
  expectedLeads: string | null;
  expectedRevenue: string | null;
  difficulty: Difficulty;
  timeRequired: string;
}

// ---------------------------------------------------------------------
//  Difficulty + time heuristics
// ---------------------------------------------------------------------
//
// The backend doesn't return a "difficulty" or "time" field for
// opportunities yet — we derive both from the format token. WeeklyAction
// already carries `estimated_time`; we use it directly.

const FORMAT_DIFFICULTY: Record<string, Difficulty> = {
  social_post: "easy",
  carousel: "medium",
  ad_copy: "easy",
  reel: "hard",
  short_video_script: "hard",
  blog_outline: "medium",
  meta: "medium",
  google_search: "medium",
  instagram_promo: "medium",
  linkedin: "medium",
};

const FORMAT_TIME: Record<string, string> = {
  social_post: "10 mins",
  carousel: "25 mins",
  ad_copy: "15 mins",
  reel: "45 mins",
  short_video_script: "30 mins",
  blog_outline: "1 hr",
  meta: "20 mins",
  google_search: "20 mins",
  instagram_promo: "20 mins",
  linkedin: "20 mins",
};

function difficultyForFormat(format: string | null): Difficulty {
  if (!format) return "medium";
  return FORMAT_DIFFICULTY[format.toLowerCase()] ?? "medium";
}

function timeForFormat(format: string | null): string {
  if (!format) return "20 mins";
  return FORMAT_TIME[format.toLowerCase()] ?? "20 mins";
}

// ---------------------------------------------------------------------
//  Scorers — one per source shape
// ---------------------------------------------------------------------

export function scoreOpportunity(opp: Opportunity): ScoredAction {
  const parsed = parseExpectedResult(opp.expected_result);
  const reach = reachBand({
    platform: opp.generator?.platform ?? null,
    confidence: opp.confidence,
  });
  return {
    source: "opportunity",
    confidence: opp.confidence,
    expectedReach: { display: reach.display, band: reach.band },
    expectedLeads: parsed.leads,
    expectedRevenue: parsed.revenue,
    difficulty: difficultyForFormat(opp.generator?.format ?? null),
    timeRequired: timeForFormat(opp.generator?.format ?? null),
  };
}

export function scoreWeeklyAction(action: WeeklyAction): ScoredAction {
  const parsed = parseExpectedResult(action.expected_result);
  // WeeklyActions don't carry a platform → no reach band (honest).
  const reach = reachBand({ platform: null, confidence: action.confidence });
  return {
    source: "weekly_action",
    confidence: action.confidence,
    expectedReach: { display: reach.display, band: reach.band },
    expectedLeads: parsed.leads,
    expectedRevenue: parsed.revenue,
    difficulty: "medium",
    // WeeklyAction has its own time string — prefer it.
    timeRequired: action.estimated_time?.trim() || "30 mins",
  };
}

export function scoreLeadPriority(item: LeadPriorityItem): ScoredAction {
  const parsed = parseExpectedResult(item.expected_result);
  // Lead priorities don't carry a platform → reach isn't the right
  // signal anyway (it's about contacting one person). Surface band as
  // unknown so the UI hides the reach chip on lead cards.
  return {
    source: "lead_priority",
    confidence: item.confidence,
    expectedReach: { display: "n/a", band: "unknown" },
    expectedLeads: parsed.leads,
    expectedRevenue:
      parsed.revenue ?? humaniseValueBand(item.estimated_value_band),
    difficulty: "easy",
    timeRequired: "5 mins",
  };
}

// ---------------------------------------------------------------------
//  Helpers (exported for testing)
// ---------------------------------------------------------------------

/**
 * Render the lead's `estimated_value_band` as a founder-friendly hint
 * when the LLM didn't include a revenue figure in `expected_result`.
 * Returns null when band is "unknown" — we don't invent a value.
 */
export function humaniseValueBand(
  band: LeadPriorityItem["estimated_value_band"],
): string | null {
  switch (band) {
    case "high":
      return "High-value lead";
    case "medium":
      return "Mid-value lead";
    case "low":
      return "Low-value lead";
    case "unknown":
      return null;
    default:
      return null;
  }
}

/**
 * Convert a Difficulty into a short founder-friendly label. Kept in
 * one place so cards stay consistent.
 */
export function humaniseDifficulty(d: Difficulty): string {
  switch (d) {
    case "easy":
      return "Quick win";
    case "medium":
      return "Some effort";
    case "hard":
      return "Bigger lift";
  }
}
