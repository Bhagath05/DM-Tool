/**
 * Phase 10.5 — AssetFooter prop derivation.
 *
 * The Founder Rule says every generated asset must answer:
 *
 *   1. Why this works         → whyItWorks
 *   2. Expected outcome       → expectedOutcome
 *   3. Best time to publish   → bestTimeToPublish
 *   4. Estimated effort       → estimatedEffort
 *
 * Backend payloads (`GeneratedContent`, `GeneratedAd`) don't ship
 * those four fields verbatim. We derive them client-side from:
 *
 *   - the LLM strategy fields already on each payload
 *   - the platform's posting-time window (lib/posting-time.ts)
 *   - the content/ad format's difficulty + time (lib/action-scoring.ts)
 *
 * Synthetic confidence: generated assets carry no LLM-graded
 * confidence. We use 75 as the "the LLM thought this was worth
 * shipping" calibration — Constitution medium band, primary CTA-
 * appropriate, but not high enough to imply certainty.
 */

import type { AssetFooterProps } from "@/components/ui/asset-footer";
import type {
  ContentStrategy,
  GeneratedAd,
  GeneratedContent,
  WinningPattern,
} from "./api";
import { humaniseDifficulty } from "./action-scoring";
import { normalisePlatform, reachBand } from "./expected-reach";
import {
  formatWindow,
  planForDay,
  todayWeekday,
} from "./posting-time";

const SYNTHETIC_CONFIDENCE = 75;

const CONTENT_FORMAT_TO_EFFORT: Record<string, { diff: "easy" | "medium" | "hard"; time: string }> = {
  social_post: { diff: "easy", time: "10 mins" },
  carousel: { diff: "medium", time: "25 mins" },
  reel: { diff: "hard", time: "45 mins" },
  ad_copy: { diff: "easy", time: "15 mins" },
};

const AD_FORMAT_TO_EFFORT: Record<string, { diff: "easy" | "medium" | "hard"; time: string }> = {
  meta: { diff: "medium", time: "20 mins" },
  google_search: { diff: "medium", time: "20 mins" },
  instagram_promo: { diff: "medium", time: "20 mins" },
  linkedin: { diff: "medium", time: "20 mins" },
  youtube: { diff: "hard", time: "30 mins" },
};

// ---------------------------------------------------------------------
//  Content
// ---------------------------------------------------------------------

/**
 * Build AssetFooter props for a generated content item.
 *
 * Accepts an optional `patterns` array — when present, used to mark
 * the posting-time recommendation as personalised vs industry-norm.
 * Without it, the function falls back to placeholder windows (still
 * useful, just honestly labelled).
 */
export function contentFooterProps(
  item: GeneratedContent,
  patterns: WinningPattern[] = [],
): AssetFooterProps {
  const why = strategyToWhy(item.strategy);
  const reach = reachBand({
    platform: item.platform,
    confidence: SYNTHETIC_CONFIDENCE,
    hasPattern: patterns.length > 0,
  });
  const effort =
    CONTENT_FORMAT_TO_EFFORT[item.content_type] ?? {
      diff: "medium" as const,
      time: "20 mins",
    };

  return {
    whyItWorks: why,
    expectedOutcome:
      reach.band === "unknown"
        ? "Outcome calibrates after first post"
        : `Estimated reach ${reach.display} (${reach.source === "personalised" ? "personalised" : "industry norm"})`,
    bestTimeToPublish: bestPostingTimeFor(item.platform, patterns),
    estimatedEffort: `${humaniseDifficulty(effort.diff)} · ${effort.time}`,
    confidence: SYNTHETIC_CONFIDENCE,
  };
}

// ---------------------------------------------------------------------
//  Ads
// ---------------------------------------------------------------------

/**
 * Build AssetFooter props for a generated ad. Ads are always-on
 * (no "best time" in the same sense as organic posts), so we surface
 * the launch-readiness window instead.
 */
export function adFooterProps(item: GeneratedAd): AssetFooterProps {
  const why = adStrategyToWhy(item);
  const effort =
    AD_FORMAT_TO_EFFORT[item.ad_type ?? ""] ?? {
      diff: "medium" as const,
      time: "20 mins",
    };

  return {
    whyItWorks: why,
    expectedOutcome: deriveAdOutcome(item),
    // Ads run continuously once launched. Honest framing — there's
    // no "best posting time" for a paid campaign.
    bestTimeToPublish: "Always-on once launched · review weekly",
    estimatedEffort: `${humaniseDifficulty(effort.diff)} · ${effort.time}`,
    confidence: SYNTHETIC_CONFIDENCE,
  };
}

// ---------------------------------------------------------------------
//  Helpers — exported for tests
// ---------------------------------------------------------------------

export function strategyToWhy(strategy: ContentStrategy): string {
  // ContentStrategy has trend_influence / audience_angle / strategy_note.
  // The most "why" of the three is strategy_note (the LLM's own
  // rationale). Fall through to audience_angle, then trend.
  return (
    strategy.strategy_note?.trim() ||
    strategy.audience_angle?.trim() ||
    strategy.trend_influence?.trim() ||
    "Generated for your audience and goal."
  );
}

export function adStrategyToWhy(item: GeneratedAd): string {
  const s = item.strategy;
  if (!s) return "Generated for your audience and goal.";
  // AdStrategy fields: trend_influence, audience_angle,
  // emotional_trigger, conversion_strategy. The most "why" of these
  // is conversion_strategy (rationale for the format/CTA).
  return (
    s.conversion_strategy?.trim() ||
    s.audience_angle?.trim() ||
    s.emotional_trigger?.trim() ||
    s.trend_influence?.trim() ||
    "Generated for your audience and goal."
  );
}

export function bestPostingTimeFor(
  platform: string,
  patterns: WinningPattern[],
): string {
  const normalised = normalisePlatform(platform);
  if (!normalised) return "Test a few times to find your window";
  const plans = planForDay(patterns, todayWeekday()).filter(
    (p) => p.platform === normalised,
  );
  const plan = plans[0];
  if (!plan || plan.windows.length === 0) {
    return "Test a few times to find your window";
  }
  const w = plan.windows[0];
  // PlatformPostingPlan.source is "derived" | "placeholder". Derived
  // means we extracted it from the user's WinningPattern — personalised.
  const suffix = plan.source === "derived" ? "(personalised)" : "(industry norm)";
  return `${formatWindow(w)} today ${suffix}`;
}

/**
 * Derive an "Expected outcome" line for an ad. AdStrategy doesn't
 * carry an explicit outcome field, so we frame the truthful default:
 * CPL needs a few days of runtime before it stabilises.
 *
 * Future improvement: when backend adds `expected_outcome` to
 * AdStrategy, prefer that value here.
 */
export function deriveAdOutcome(item: GeneratedAd): string {
  // Currently no LLM-provided expected_outcome field on AdStrategy.
  // Keep the parameter so the signature is stable for future use.
  void item;
  return "Lead cost stabilises after 3-5 days of runtime";
}
