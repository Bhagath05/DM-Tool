/**
 * Translate raw `TrendingTopic` → Constitution-shaped opportunity card.
 *
 * Pure functions, tested in isolation. The trends LLM produces a
 * relevance_score (1-100) and a couple of suggested_angles per topic;
 * the translator turns that into a full AiRecommendation card with an
 * inferred impact category and calibrated confidence.
 *
 * Discipline:
 *   - Confidence is capped at 90 — LLM relevance is an educated guess,
 *     not measured outcome. We never ship "98% confidence" for a trend.
 *   - Topics with relevance < 40 are dropped (Speculative band — the
 *     Constitution says "don't ship as CTA"). The caller surfaces a
 *     Coming Soon card instead.
 *   - Impact category is inferred from topic + why_it_matters via a
 *     keyword classifier. Default = "lead" (most marketing trends drive
 *     interest, not direct revenue).
 */

import type {
  AiRecommendationProps,
  ImpactCategory,
} from "@/components/ui/business-metric";
import type { TrendingTopic } from "@/lib/api";

// ---------------------------------------------------------------------
//  Impact-category classifier
// ---------------------------------------------------------------------

/**
 * Loose keyword groups. Order matters — first match wins. Specific
 * categories (revenue, customer, time, cost) get a chance before the
 * "lead" default, which is the catch-all because most marketing trends
 * drive interest.
 */
const CATEGORY_KEYWORDS: Array<{ category: ImpactCategory; words: string[] }> = [
  {
    category: "revenue",
    words: [
      "revenue", "sales", "purchase", "buy", "buying", "shopping",
      "checkout", "transaction", "monetis", "monetiz", "pricing",
      "discount", "promo", "offer", "spend",
    ],
  },
  {
    category: "customer",
    words: [
      "customer retention", "loyalty", "repeat", "returning", "lifetime",
      "subscription", "churn", "renewal", "upsell", "upgrade",
      "community", "membership", "advocate",
    ],
  },
  {
    category: "time",
    words: [
      "automation", "automate", "save time", "faster", "efficient",
      "workflow", "productivity", "streamlin", "shortcut", "ai-assist",
      "no-code", "template",
    ],
  },
  {
    category: "cost",
    words: [
      "cost", "cheaper", "budget", "save money", "low-cost", "free",
      "diy", "bootstrap", "organic", "frugal",
    ],
  },
];

export function classifyTrendImpact(
  topic: string,
  whyItMatters: string,
): ImpactCategory {
  const haystack = `${topic} ${whyItMatters}`.toLowerCase();
  for (const { category, words } of CATEGORY_KEYWORDS) {
    for (const w of words) {
      if (haystack.includes(w)) return category;
    }
  }
  return "lead";
}

// ---------------------------------------------------------------------
//  Confidence translation
// ---------------------------------------------------------------------

/**
 * Cap LLM-supplied relevance at 90 — that's the High-band ceiling for
 * the trends domain since relevance is an inference, not an observed
 * outcome. Anything the LLM rated below 40 is dropped upstream.
 */
function relevanceToConfidence(relevance: number): number {
  if (relevance >= 90) return 90;
  if (relevance < 0) return 0;
  if (relevance > 100) return 90;
  return Math.round(relevance);
}

// ---------------------------------------------------------------------
//  Per-topic translator → AiRecommendation props
// ---------------------------------------------------------------------

export interface TrendOpportunity extends AiRecommendationProps {
  /** Used as React `key` upstream. */
  id: string;
}

export function translateTrendingTopic(
  topic: TrendingTopic,
  index: number,
): TrendOpportunity | null {
  // Speculative-band drop. Per Constitution: < 40 doesn't ship as CTA.
  if (
    typeof topic.relevance_score !== "number" ||
    topic.relevance_score < 40
  ) {
    return null;
  }

  const category = classifyTrendImpact(topic.topic, topic.why_it_matters);
  const angle =
    topic.suggested_angles?.[0]?.trim() ||
    `Make a piece of content about ${topic.topic.toLowerCase()}.`;
  const angles = topic.suggested_angles ?? [];

  const expectedResult = expectedResultForCategory(category, topic);

  return {
    id: `trend-${index}-${topic.topic.slice(0, 32).toLowerCase().replace(/\s+/g, "-")}`,
    whatIsHappening: `${topic.topic} is gaining attention in your industry right now.`,
    impactCategory: category,
    recommendation: angle,
    expectedResult,
    confidence: relevanceToConfidence(topic.relevance_score),
    reason:
      topic.why_it_matters && topic.why_it_matters.trim().length > 0
        ? topic.why_it_matters.trim()
        : `Topic flagged as relevant to your audience by trend analysis.`,
    technicalDetails: {
      "Topic": topic.topic,
      "Relevance score": topic.relevance_score,
      "Suggested angles": angles.length || 0,
      "Detected category": category,
    },
  };
}

function expectedResultForCategory(
  category: ImpactCategory,
  topic: TrendingTopic,
): string {
  // Optional in the API type — caller already gated <40 in translateTrendingTopic,
  // but we coerce here defensively so the comparison below is type-safe.
  const conf = topic.relevance_score ?? 0;
  // Higher-relevance trends get bolder ranges; speculative gets cautious.
  if (category === "revenue") {
    return conf >= 75
      ? "Higher buying intent — could lift inquiries or orders 5-15% over 2-3 weeks."
      : "Worth testing — small lift in buying intent possible.";
  }
  if (category === "customer") {
    return conf >= 75
      ? "Stronger retention signal — could measurably reduce drop-off if leaned into."
      : "May deepen relationships with existing customers if tested.";
  }
  if (category === "time") {
    return conf >= 75
      ? "Could save several hours per week if adopted as part of your workflow."
      : "May save some time once integrated into a routine.";
  }
  if (category === "cost") {
    return conf >= 75
      ? "Could meaningfully reduce cost-per-result if applied to your top channel."
      : "Worth testing for cost savings.";
  }
  // lead (default)
  return conf >= 75
    ? "Likely lifts engagement and new leads 10-20% over the next 1-2 weeks."
    : "May modestly lift engagement — worth one short experiment.";
}

// ---------------------------------------------------------------------
//  Page-level — group opportunities by impact category
// ---------------------------------------------------------------------

export interface OpportunitiesByCategory {
  revenue: TrendOpportunity[];
  lead: TrendOpportunity[];
  customer: TrendOpportunity[];
  time: TrendOpportunity[];
  cost: TrendOpportunity[];
  /** Sorted by confidence desc. */
  all: TrendOpportunity[];
  /** Highest-confidence opportunity across all categories. May be null. */
  biggest: TrendOpportunity | null;
  /** Topics the translator dropped (relevance < 40). */
  droppedCount: number;
}

export function groupOpportunities(
  topics: TrendingTopic[],
): OpportunitiesByCategory {
  const buckets: OpportunitiesByCategory = {
    revenue: [],
    lead: [],
    customer: [],
    time: [],
    cost: [],
    all: [],
    biggest: null,
    droppedCount: 0,
  };
  topics.forEach((t, i) => {
    const opp = translateTrendingTopic(t, i);
    if (!opp) {
      buckets.droppedCount += 1;
      return;
    }
    buckets[opp.impactCategory].push(opp);
    buckets.all.push(opp);
  });
  buckets.all.sort((a, b) => b.confidence - a.confidence);
  for (const cat of ["revenue", "lead", "customer", "time", "cost"] as const) {
    buckets[cat].sort((a, b) => b.confidence - a.confidence);
  }
  buckets.biggest = buckets.all[0] ?? null;
  return buckets;
}
