/**
 * Single source of truth for translating engineering labels into business
 * language. Used across the lead drawer, analytics tables, share blocks,
 * and studio result cards.
 *
 * Why a separate file: Phase 2.3 is purely about hiding technical exposure.
 * Centralising the maps means later edits (e.g. renaming an asset type
 * presentation) happen in one place — and any surface that imports these
 * helpers automatically stays consistent.
 */

import type { AssetType } from "./api";

// ----------------------------------------------------------------------
//  Asset type — the polymorphic "what kind of thing produced this lead"
// ----------------------------------------------------------------------

/** What a row from the leads/top-assets tables represents, in human words. */
export const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  content: "Social post",
  ad: "Ad",
  visual: "Visual brief",
  campaign: "Campaign series",
};

/** Short verb-phrase suitable for chain-text like "what they saw". */
export const ASSET_TYPE_PHRASE: Record<AssetType, string> = {
  content: "A social post",
  ad: "An ad",
  visual: "A visual brief",
  campaign: "A campaign series",
};

// ----------------------------------------------------------------------
//  Content / ad / visual subtype labels
// ----------------------------------------------------------------------

export const CONTENT_SUBTYPE_LABEL: Record<string, string> = {
  social_post: "Social post",
  reel: "Reel / Short",
  carousel: "Carousel",
  ad_copy: "Ad copy",
};

export const AD_SUBTYPE_LABEL: Record<string, string> = {
  meta: "Meta ad",
  google_search: "Google search ad",
  instagram_promo: "Instagram promo",
  linkedin: "LinkedIn ad",
  youtube: "YouTube ad",
};

export const VISUAL_SUBTYPE_LABEL: Record<string, string> = {
  ad_creative: "Poster / Ad",
  carousel: "Carousel design",
  reel: "Reel storyboard",
  thumbnail: "Thumbnail",
};

export const CAMPAIGN_SUBTYPE_LABEL: Record<string, string> = {
  product_launch: "Product launch",
  brand_awareness: "Brand awareness",
  lead_generation: "Lead generation",
  seasonal: "Seasonal push",
  engagement_growth: "Engagement growth",
  retargeting: "Re-engagement",
};

/** Pick the right subtype label for a given asset_type + subtype string. */
export function subtypeLabel(assetType: AssetType, subtype: string): string {
  const map =
    assetType === "content"
      ? CONTENT_SUBTYPE_LABEL
      : assetType === "ad"
        ? AD_SUBTYPE_LABEL
        : assetType === "visual"
          ? VISUAL_SUBTYPE_LABEL
          : CAMPAIGN_SUBTYPE_LABEL;
  return map[subtype] ?? prettifyEnum(subtype);
}

// ----------------------------------------------------------------------
//  Generic enum prettifier — fallback when no explicit label exists
// ----------------------------------------------------------------------

/**
 * Turn "social_post" → "Social post", "ad_copy" → "Ad copy".
 * Used as the default when a more specific label isn't defined.
 */
export function prettifyEnum(raw: string | null | undefined): string {
  if (!raw) return "";
  const spaced = raw.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

// ----------------------------------------------------------------------
//  Marketing-objective humanizer (Founder Experience Audit B2 / H3)
// ----------------------------------------------------------------------

/**
 * Translate raw ad / campaign objective enums into the verb phrase a
 * non-marketer would actually say. The backend keeps `lead_generation`,
 * `brand_awareness`, etc. as canonical IDs; this map is purely cosmetic.
 *
 * Falls back to `prettifyEnum` for unknown values so the surface never
 * crashes if a new objective ships before we update this map.
 */
const OBJECTIVE_LABELS: Record<string, string> = {
  lead_generation: "Get more leads",
  leads: "Get more leads",
  awareness: "Get noticed",
  brand_awareness: "Get noticed",
  engagement: "Spark conversation",
  sales: "Close more sales",
  conversions: "Close more sales",
  conversion: "Close more sales",
  traffic: "Send people to the site",
  app_installs: "Get app installs",
  retargeting: "Bring back past visitors",
  retention: "Keep customers coming back",
};

export function humanizeObjective(raw: string | null | undefined): string {
  if (!raw) return "";
  return OBJECTIVE_LABELS[raw.toLowerCase()] ?? prettifyEnum(raw);
}

// ----------------------------------------------------------------------
//  UTM translators — replace tracking jargon with English
// ----------------------------------------------------------------------

/**
 * "instagram" → "Instagram", "google" → "Google", but also map our internal
 * source slugs ("facebook_meta", "google_search") to their human-readable
 * platform name.
 */
const UTM_SOURCE_LABELS: Record<string, string> = {
  facebook: "Facebook",
  facebook_meta: "Facebook / Instagram",
  meta: "Facebook / Instagram",
  instagram: "Instagram",
  google: "Google",
  google_search: "Google search",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  twitter: "X (Twitter)",
  x: "X (Twitter)",
  youtube: "YouTube",
  pinterest: "Pinterest",
  email: "Email",
  direct: "Direct visit",
};

const UTM_MEDIUM_LABELS: Record<string, string> = {
  // Common values produced by our distribution module's MEDIUM_BY_* maps.
  paid_social: "Paid social",
  paid_search: "Search ads",
  social: "Organic social",
  organic: "Organic",
  email: "Email",
  story: "Story",
  reel: "Reel / Short",
  carousel: "Carousel",
  display: "Display ad",
};

/** "instagram" → "Instagram", unknown stays unchanged-but-prettified. */
export function humanizeSource(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw.toLowerCase();
  return UTM_SOURCE_LABELS[key] ?? prettifyEnum(raw);
}

export function humanizeMedium(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw.toLowerCase();
  return UTM_MEDIUM_LABELS[key] ?? prettifyEnum(raw);
}

/**
 * Build a one-line "how they got here" description from UTM bits.
 * Returns null when there's nothing meaningful to say.
 */
export function describeClickPath(parts: {
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
}): string | null {
  const src = humanizeSource(parts.utm_source);
  const medium = humanizeMedium(parts.utm_medium);
  const campaign = parts.utm_campaign;

  // Compose:  "From Instagram · Paid social · Spring Launch"
  const bits = [
    src ? `From ${src}` : null,
    medium && medium !== src ? medium : null,
    campaign ? `Campaign: ${campaign}` : null,
  ].filter((x): x is string => Boolean(x));

  return bits.length ? bits.join(" · ") : null;
}

// ----------------------------------------------------------------------
//  utm_content special-case — campaigns emit "day_1", "day_7", etc.
// ----------------------------------------------------------------------

/**
 * "day_1" → "Day 1 of the campaign", "social_post" → "Social post".
 * Pure cosmetic — the field stays raw on the backend.
 */
export function humanizeUtmContent(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const match = raw.match(/^day_(\d+)$/);
  if (match) return `Day ${match[1]} of the campaign`;
  if (raw in CONTENT_SUBTYPE_LABEL) return CONTENT_SUBTYPE_LABEL[raw];
  if (raw in AD_SUBTYPE_LABEL) return AD_SUBTYPE_LABEL[raw];
  if (raw in VISUAL_SUBTYPE_LABEL) return VISUAL_SUBTYPE_LABEL[raw];
  return prettifyEnum(raw);
}
