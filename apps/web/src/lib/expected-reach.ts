/**
 * Phase 10.4 — Expected Reach derivation.
 *
 * Produces a founder-friendly reach band ("12k+", "5k–8k", "Awaiting
 * data") for a recommended action, given platform + confidence + the
 * presence of audience signal.
 *
 * Why a derivation lib instead of a backend field: no API today returns
 * a "predicted reach" number. The honest move is to:
 *   1. Use the recommendation's `confidence` as the calibrator.
 *   2. Multiply by a per-platform baseline (industry-norm impressions
 *      for a new-ish account on that platform).
 *   3. Surface as a BAND, not a precise number.
 *   4. Label the source ("Estimated" vs "Personalised") so the founder
 *      knows it's a directional signal, not a prediction.
 *
 * When the backend ships a real predicted-reach endpoint, this lib's
 * surface (`reachBand(...)`) doesn't change — just the implementation.
 */

import type { SocialPlatform } from "./api";

/** Platforms the Command Center surfaces. SocialPlatform from the API
 *  doesn't include "twitter" yet, so we widen here for display only. */
export type CommandPlatform = SocialPlatform | "twitter";

/**
 * Per-platform baseline impression bands for a "typical" new business
 * account, organised by confidence band. Sourced from widely-cited
 * Buffer / Sprout 2024 medians — NOT presented as predictions. The
 * UI labels these as "Estimated" unless overridden by a derived signal.
 *
 * Numbers are deliberately wide bands ("8k–12k") rather than point
 * estimates — encourages the founder to treat them as direction, not
 * commitment.
 */
const BASELINE: Record<
  CommandPlatform,
  { high: string; medium: string; low: string }
> = {
  instagram: { high: "10k–18k", medium: "5k–8k", low: "1k–3k" },
  linkedin: { high: "8k–14k", medium: "3k–6k", low: "800–2k" },
  facebook: { high: "12k–22k", medium: "5k–9k", low: "1k–3k" },
  twitter: { high: "6k–12k", medium: "2k–4k", low: "500–1.5k" },
  tiktok: { high: "20k–60k", medium: "8k–15k", low: "1k–4k" },
  youtube: { high: "5k–12k", medium: "2k–5k", low: "500–2k" },
};

export type ReachBand = "high" | "medium" | "low" | "unknown";

/**
 * Map a 0-100 confidence score to a reach band.
 *
 *   ≥80 → high       (Constitution: "High" band, primary CTA)
 *   ≥60 → medium     (Constitution: "Medium" band, suggest action)
 *   ≥40 → low        (Constitution: "Low" band, frame as experiment)
 *   <40 → unknown    (Constitution: "Speculative" — don't predict reach)
 */
export function confidenceToReachBand(confidence: number): ReachBand {
  if (confidence >= 80) return "high";
  if (confidence >= 60) return "medium";
  if (confidence >= 40) return "low";
  return "unknown";
}

export interface ReachEstimate {
  /** Display string — e.g. "10k–18k" or "Awaiting data". */
  display: string;
  /** Band that derives `display`. Useful for tone / icon. */
  band: ReachBand;
  /** How this estimate was produced. UI surfaces "Estimated" badge for
   *  industry-baseline-derived rows so the founder isn't misled. */
  source: "baseline" | "personalised" | "unknown";
}

export interface ReachInputs {
  platform: CommandPlatform | string | null;
  confidence: number;
  /** When true, use the personalised label (we have winning-pattern
   *  data for the user on this platform). Defaults to false. */
  hasPattern?: boolean;
}

/**
 * Compute a display-ready reach estimate.
 *
 * Returns "Awaiting data" honestly when:
 *   - confidence < 40 (speculative — don't pretend to know)
 *   - platform isn't in our baseline table (e.g. "pinterest")
 *   - platform is null
 */
export function reachBand(inputs: ReachInputs): ReachEstimate {
  const band = confidenceToReachBand(inputs.confidence);
  if (band === "unknown") {
    return { display: "Awaiting data", band, source: "unknown" };
  }
  const platformKey = normalisePlatform(inputs.platform);
  if (!platformKey) {
    return { display: "Awaiting data", band, source: "unknown" };
  }
  const baseline = BASELINE[platformKey];
  return {
    display: baseline[band],
    band,
    source: inputs.hasPattern ? "personalised" : "baseline",
  };
}

/**
 * Normalise an inbound platform string from the backend ("meta" → no
 * direct match, "instagram" → instagram, "google_search" → no match for
 * organic reach). Returns null when the platform isn't a "post here"
 * surface — ads don't have organic-reach baselines.
 */
export function normalisePlatform(
  p: CommandPlatform | string | null | undefined,
): CommandPlatform | null {
  if (!p) return null;
  const lower = p.toLowerCase();
  if (lower === "instagram" || lower === "ig") return "instagram";
  if (lower === "linkedin") return "linkedin";
  if (lower === "facebook" || lower === "meta" || lower === "fb")
    return "facebook";
  if (lower === "twitter" || lower === "x") return "twitter";
  if (lower === "tiktok") return "tiktok";
  if (lower === "youtube" || lower === "yt") return "youtube";
  return null;
}

/**
 * Best-effort parse of a "Expected: X leads" / "+15–25 leads" /
 * "₹15,000–₹25,000" string into a structured (label, range) shape that
 * the Action Scoring footer can render uniformly. Conservative — when
 * the text doesn't match a known shape, returns the original text under
 * the generic `summary` field so the founder still sees something
 * meaningful.
 */
export function parseExpectedResult(text: string | null | undefined): {
  leads: string | null;
  revenue: string | null;
  summary: string | null;
} {
  const out = { leads: null as string | null, revenue: null as string | null, summary: null as string | null };
  if (!text) return out;

  // Leads: "+15 leads", "5-10 leads", "5 to 10 leads"
  const leadsMatch = text.match(/(\+?\s*\d+(?:[\s-–]+\d+)?\+?\s*leads?)/i);
  if (leadsMatch) out.leads = leadsMatch[1].trim().replace(/\s+/g, " ");

  // Revenue: "₹15,000-₹25,000", "$2k-$4k", "+₹50k"
  const revenueMatch = text.match(
    /[+]?\s*(?:₹|\$|€|£)\s*[\d,.]+\s*[k]?(?:\s*[-–]\s*(?:₹|\$|€|£)?\s*[\d,.]+\s*[k]?)?/i,
  );
  if (revenueMatch) out.revenue = revenueMatch[0].trim();

  // Fall-through summary when neither leads nor revenue matched.
  if (!out.leads && !out.revenue) out.summary = text;

  return out;
}
