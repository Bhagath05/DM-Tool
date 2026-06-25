/**
 * Phase 10.3c — Growth Insights composition.
 *
 * Pure function that turns raw data the Market Intelligence page
 * already loads into 1–3 "AI Growth Insight" cards. Lives in /lib so
 * it can be unit-tested without rendering anything.
 *
 * Composition rules:
 *
 *   - One insight per signal source — never duplicate.
 *   - Insights MUST have a CTA target. No information-only cards.
 *   - Skip a source rather than fabricate. Better to surface fewer
 *     real insights than three thin ones.
 *
 * Sources:
 *   1. Top opportunity → "X opportunities detected — highest scores Y%"
 *   2. Top posting window (today) → "Post on {platform} at HH:MM"
 *   3. Strongest perf winner → "{whatIsHappening}"
 */

import type { OpportunityCenterReport } from "./api";
import type { PerformanceCards } from "./performance-translator";
import {
  formatWindow,
  type PlatformPostingPlan,
} from "./posting-time";

import type { GrowthInsight } from "../app/(app)/grow/market-intelligence/_components/growth-insights";

export interface GrowthInsightInputs {
  opportunities: OpportunityCenterReport | null;
  postingPlans: PlatformPostingPlan[];
  performance: PerformanceCards | null;
}

const PLATFORM_LABEL: Record<PlatformPostingPlan["platform"], string> = {
  instagram: "Instagram",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  twitter: "Twitter / X",
  tiktok: "TikTok",
  youtube: "YouTube",
};

export function composeGrowthInsights(
  inputs: GrowthInsightInputs,
): GrowthInsight[] {
  const out: GrowthInsight[] = [];

  // 1. Opportunities — surface the count + top-score line.
  const opp = topOpportunityInsight(inputs.opportunities);
  if (opp) out.push(opp);

  // 2. Posting time — surface the top window today.
  const post = topPostingInsight(inputs.postingPlans);
  if (post) out.push(post);

  // 3. Performance winner — surface the strongest movement.
  const perf = topPerformanceInsight(inputs.performance);
  if (perf) out.push(perf);

  return out;
}

// ---------------------------------------------------------------------
//  Per-source composers (exported for tests)
// ---------------------------------------------------------------------

export function topOpportunityInsight(
  report: OpportunityCenterReport | null,
): GrowthInsight | null {
  if (!report) return null;
  const all = [
    ...(report.content_opportunities ?? []),
    ...(report.ad_opportunities ?? []),
  ];
  if (all.length === 0) return null;
  const top = all.reduce((a, b) => (b.confidence > a.confidence ? b : a));
  return {
    id: "insight-opportunities",
    tone: "good",
    title: `${all.length} opportunit${all.length === 1 ? "y" : "ies"} detected`,
    detail: `Top score ${top.confidence}% · ${truncate(top.headline, 60)}`,
    ctaLabel: "See opportunities",
    ctaHref: "/grow/opportunities",
  };
}

export function topPostingInsight(
  plans: PlatformPostingPlan[],
): GrowthInsight | null {
  if (plans.length === 0) return null;
  // Pick the highest-confidence window across all platforms.
  let bestPlan: PlatformPostingPlan | null = null;
  let bestConf = -1;
  let bestWindow: PlatformPostingPlan["windows"][number] | null = null;
  for (const plan of plans) {
    for (const w of plan.windows) {
      if (w.confidence_score > bestConf) {
        bestConf = w.confidence_score;
        bestPlan = plan;
        bestWindow = w;
      }
    }
  }
  if (!bestPlan || !bestWindow) return null;
  const platformLabel = PLATFORM_LABEL[bestPlan.platform];
  const time = formatWindow(bestWindow);
  return {
    id: "insight-posting-time",
    tone: bestPlan.source === "derived" ? "good" : "neutral",
    title: `Post on ${platformLabel} at ${time} today`,
    detail:
      bestPlan.source === "derived"
        ? `Your winning pattern · ${bestConf}% confidence`
        : `Industry norm · estimated`,
    ctaLabel: "Open studio",
    ctaHref: "/create/social-posts",
  };
}

export function topPerformanceInsight(
  perf: PerformanceCards | null,
): GrowthInsight | null {
  if (!perf || !perf.cards || perf.cards.length === 0) return null;
  // Find the strongest "shift" card — winner or loser.
  const SHIFT = new Set([
    "winner",
    "audience_winner",
    "concept_winner",
    "creative_dna",
    "budget_waste",
    "audience_loser",
  ]);
  const shifts = perf.cards.filter((c) => SHIFT.has(c.kind));
  if (shifts.length === 0) return null;
  const top = shifts.reduce((a, b) => (b.confidence > a.confidence ? b : a));
  const isLoser = top.kind === "budget_waste" || top.kind === "audience_loser";
  return {
    id: "insight-performance",
    tone: isLoser ? "watch" : "good",
    title: truncate(top.whatIsHappening, 80),
    detail: truncate(top.recommendation, 70),
    ctaLabel: "View performance",
    ctaHref: "/results",
  };
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max - 1).trimEnd() + "…";
}
