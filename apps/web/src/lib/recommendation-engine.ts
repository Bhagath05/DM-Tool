/**
 * Phase 10.4 — Recommendation Engine (frontend composition layer).
 *
 * Pure functions that pivot the raw OpportunityCenterReport into the
 * Command Center's slot shape:
 *
 *   topPostPerPlatform(report)  → 1 best post per IG/LI/FB/X
 *   topAdPerPlatform(report)    → 1 best ad per Meta/Google/LinkedIn
 *   topReels(report)            → up to N reel opportunities
 *
 * Pivots happen on the frontend so we don't need a new backend endpoint
 * per slot. Each pivot is idempotent + side-effect-free.
 */

import type { Opportunity, OpportunityCenterReport } from "./api";
import { normalisePlatform, type CommandPlatform } from "./expected-reach";

const POST_PLATFORMS: CommandPlatform[] = [
  "instagram",
  "linkedin",
  "facebook",
  "twitter",
];

const AD_FORMATS = ["meta", "google_search", "linkedin"] as const;
export type AdFormat = (typeof AD_FORMATS)[number];

const REEL_FORMATS = new Set(["reel", "short_video_script"]);

export interface PlatformPostSlot {
  platform: CommandPlatform;
  opportunity: Opportunity | null;
}

export interface AdFormatSlot {
  format: AdFormat;
  opportunity: Opportunity | null;
}

// ---------------------------------------------------------------------
//  Content opportunities → post slots
// ---------------------------------------------------------------------

/**
 * For each of the 4 supported post platforms, surface the highest-
 * confidence content opportunity targeted at it. Returns a slot per
 * platform even when no matching opportunity exists (null → UI shows
 * "Awaiting signal" empty state). Keeps card grid layout stable.
 *
 * Reel-formatted opportunities are intentionally EXCLUDED — they live
 * in a separate Reels section.
 */
export function topPostPerPlatform(
  report: OpportunityCenterReport | null,
): PlatformPostSlot[] {
  const contentOpps = (report?.content_opportunities ?? []).filter(
    (o) => !isReelOpportunity(o),
  );

  return POST_PLATFORMS.map((platform) => {
    const matches = contentOpps.filter(
      (o) => normalisePlatform(o.generator?.platform) === platform,
    );
    matches.sort((a, b) => b.confidence - a.confidence);
    return {
      platform,
      opportunity: matches[0] ?? null,
    };
  });
}

// ---------------------------------------------------------------------
//  Ad opportunities → ad slots
// ---------------------------------------------------------------------

/**
 * For each of the 3 supported ad formats (Meta, Google Search,
 * LinkedIn), surface the highest-confidence ad opportunity. Returns
 * a slot per format — empty when no opportunity targets that format.
 *
 * Format match is exact on `generator.format`. `instagram_promo` is
 * intentionally NOT a top-level slot — it's a content opportunity in
 * disguise and lives in the Posts grid.
 */
export function topAdPerFormat(
  report: OpportunityCenterReport | null,
): AdFormatSlot[] {
  const adOpps = report?.ad_opportunities ?? [];

  return AD_FORMATS.map((format) => {
    const matches = adOpps.filter(
      (o) => (o.generator?.format ?? "").toLowerCase() === format,
    );
    matches.sort((a, b) => b.confidence - a.confidence);
    return {
      format,
      opportunity: matches[0] ?? null,
    };
  });
}

// ---------------------------------------------------------------------
//  Reel opportunities — separate surface
// ---------------------------------------------------------------------

/**
 * Top N reel opportunities across both content and ad arrays (reels
 * occasionally surface as ad-target if the recommendation is "boost
 * this reel as an ad"). Sorted by confidence DESC.
 */
export function topReels(
  report: OpportunityCenterReport | null,
  limit = 2,
): Opportunity[] {
  if (!report) return [];
  const all = [
    ...(report.content_opportunities ?? []),
    ...(report.ad_opportunities ?? []),
  ];
  const reels = all.filter(isReelOpportunity);
  reels.sort((a, b) => b.confidence - a.confidence);
  return reels.slice(0, limit);
}

// ---------------------------------------------------------------------
//  Helpers (exported for testing)
// ---------------------------------------------------------------------

export function isReelOpportunity(opp: Opportunity): boolean {
  const fmt = (opp.generator?.format ?? "").toLowerCase();
  return REEL_FORMATS.has(fmt);
}

/**
 * Display label for an ad format. Kept in one place so cards stay
 * consistent across the page.
 */
export function adFormatLabel(format: AdFormat): string {
  switch (format) {
    case "meta":
      return "Meta Ad";
    case "google_search":
      return "Google Search Ad";
    case "linkedin":
      return "LinkedIn Ad";
  }
}

/**
 * Display label for a post platform.
 */
export function postPlatformLabel(platform: CommandPlatform): string {
  switch (platform) {
    case "instagram":
      return "Instagram";
    case "linkedin":
      return "LinkedIn";
    case "facebook":
      return "Facebook";
    case "twitter":
      return "Twitter / X";
    case "tiktok":
      return "TikTok";
    case "youtube":
      return "YouTube";
  }
}
