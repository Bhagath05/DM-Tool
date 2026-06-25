/**
 * Translate the backend `PerformanceDiagnosticCard` payload into
 * Constitution-shaped `<AiRecommendation>` props.
 *
 * The backend already enforces the AI Recommendation Contract — every
 * field is non-empty by the time it leaves Pydantic. The translator's
 * job is just to:
 *
 *   1. Adapt naming (snake_case backend → camelCase props).
 *   2. Hide the rare card with insufficient text (defence-in-depth —
 *      should never happen because backend's `min_length=3` already
 *      rejects, but we belt-and-braces here too).
 *   3. Surface raw evidence as `technicalDetails` for Pro mode.
 *
 * Pure functions. Easy to test. No fetching, no React.
 */

import type {
  AiRecommendationProps,
  ImpactCategory,
} from "@/components/ui/business-metric";
import type {
  PerformanceDiagnosticCard,
  PerformanceImpactCategory,
  PerformanceOverview,
} from "@/lib/api";

// ---------------------------------------------------------------------
//  Per-card translator
// ---------------------------------------------------------------------

export interface PerformanceOpportunity extends AiRecommendationProps {
  /** React key. Server-side id. */
  id: string;
  /** For analytics / dismissals. */
  kind: PerformanceDiagnosticCard["kind"];
  /** UI sectioning hint — assigned by the translator from `kind`. */
  section: PerformanceSection;
  /**
   * Pass-through of the backend evidence blob — used by Phase 10.0
   * derivations (`lib/performance-derived.ts`) and the apex
   * `<WinningCreativeFormula>` component to read the underlying tags
   * (audience, concept_family, etc.) without re-fetching. The
   * Constitution contract is still enforced via the top-level fields;
   * evidence is supplemental.
   */
  evidence: Record<string, unknown>;
}

/**
 * Phase 9.1.5 — UI sections. Maps each diagnostic kind to one of five
 * sub-section buckets the dashboard groups by. No new section is added
 * after creative_dna because the apex card has its own permanent slot.
 */
export type PerformanceSection =
  | "baseline" // 9.1 winner + budget_reallocation
  | "audience"
  | "creative"
  | "offer"
  | "scaling"
  | "dna";

const KIND_TO_SECTION: Record<PerformanceDiagnosticCard["kind"], PerformanceSection> = {
  // 9.1
  winner: "baseline",
  loser: "baseline",
  fatigue: "baseline",
  audience_shift: "baseline",
  budget_reallocation: "baseline",
  // 9.1.5
  audience_winner: "audience",
  audience_loser: "audience",
  concept_winner: "creative",
  emotion_winner: "creative",
  funnel_winner: "creative",
  pattern_winner: "creative",
  offer_winner: "offer",
  offer_pricing_sensitivity: "offer",
  scale_candidate: "scaling",
  budget_waste: "scaling",
  creative_dna: "dna",
};

/**
 * Human-readable section label. Founder-facing, no jargon.
 * Kept here next to the kind→section map so they don't drift.
 */
export const SECTION_LABEL: Record<PerformanceSection, string> = {
  baseline: "Top opportunity",
  audience: "Audience insight",
  creative: "Creative insight",
  offer: "Offer insight",
  scaling: "Where to spend next",
  dna: "Winning pattern",
};

const REQUIRED_TEXT_FIELDS: Array<keyof PerformanceDiagnosticCard> = [
  "what_happened",
  "why",
  "recommendation",
  "expected_result",
  "reason",
];

/**
 * Map a single backend diagnostic to an `<AiRecommendation>`-ready
 * shape. Returns `null` if any contract field is empty (defensive —
 * the backend should never let this happen).
 */
export function translateDiagnostic(
  card: PerformanceDiagnosticCard,
): PerformanceOpportunity | null {
  for (const field of REQUIRED_TEXT_FIELDS) {
    const v = card[field];
    if (typeof v !== "string" || v.trim().length < 3) {
      return null;
    }
  }
  if (
    typeof card.confidence !== "number" ||
    !Number.isFinite(card.confidence) || // NaN / ±Infinity slip past <,>
    card.confidence < 0 ||
    card.confidence > 100
  ) {
    return null;
  }

  // Combine `what_happened` + `why` into the single "what is happening"
  // slot the Constitution component owns. Why precedes the action
  // visually but the why is causal context.
  const whatIsHappening = `${card.what_happened.trim()} ${card.why.trim()}`.trim();

  return {
    id: card.id,
    kind: card.kind,
    section: KIND_TO_SECTION[card.kind] ?? "baseline",
    whatIsHappening,
    impactCategory: card.impact_category as ImpactCategory,
    recommendation: card.recommendation.trim(),
    expectedResult: card.expected_result.trim(),
    confidence: Math.round(card.confidence),
    reason: card.reason.trim(),
    technicalDetails: extractTechnicalDetails(card),
    // Pass-through for Phase 10.0 derivations + apex visualization.
    // The evidence shape isn't part of the public Constitution
    // contract; treat as best-effort supplemental data.
    evidence: (card.evidence ?? {}) as Record<string, unknown>,
  };
}

/**
 * Cherry-pick the evidence keys the founder might want to see in Pro
 * mode. We do not surface the entire evidence blob — only fields with
 * unambiguous, founder-readable meaning.
 */
function extractTechnicalDetails(
  card: PerformanceDiagnosticCard,
): Record<string, string | number> {
  const e = card.evidence ?? {};
  const out: Record<string, string | number> = {};

  const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;
  const str = (v: unknown): string | null =>
    typeof v === "string" && v.trim().length > 0 ? v : null;

  const currency = str(e["currency"]) ?? str(e["winner_currency"]) ?? null;
  const fmtMoney = (v: number | null) =>
    v === null ? null : currency ? `${currency} ${v.toLocaleString()}` : v.toLocaleString();

  // Common across kinds.
  if (str(e["creative_ref"])) out["Creative"] = str(e["creative_ref"])!;
  if (str(e["platform"])) out["Platform"] = str(e["platform"])!;
  if (num(e["impressions"]) !== null)
    out["Impressions"] = num(e["impressions"])!.toLocaleString();
  if (num(e["clicks"]) !== null) out["Clicks"] = num(e["clicks"])!;
  if (num(e["conversions"]) !== null) out["Conversions"] = num(e["conversions"])!;

  const spend = fmtMoney(num(e["spend"]));
  if (spend) out["Spend"] = spend;

  const cpl = num(e["cpl"]);
  if (cpl !== null) out["Cost per lead"] = fmtMoney(cpl)!;

  const roas = num(e["roas"]);
  if (roas !== null) out["ROAS"] = `${roas.toFixed(2)}x`;

  // Tags (when present).
  if (str(e["concept_family"]))
    out["Concept family"] = str(e["concept_family"])!.replace(/_/g, " ");
  if (str(e["audience"]))
    out["Audience"] = str(e["audience"])!.replace(/_/g, " ");
  if (str(e["offer_type"]) && e["offer_type"] !== "none")
    out["Offer"] = str(e["offer_type"])!.replace(/_/g, " ");

  // Reallocation-specific fields.
  if (str(e["winner_ref"])) out["Winning creative"] = str(e["winner_ref"])!;
  if (str(e["underperformer_ref"]))
    out["Underperforming creative"] = str(e["underperformer_ref"])!;
  const ratio = num(e["cpl_ratio"]);
  if (ratio !== null) out["Cost gap"] = `${ratio.toFixed(1)}x`;

  // 9.1.5 — audience layer
  if (str(e["audience"]) && card.kind.startsWith("audience_"))
    out["Audience group"] = str(e["audience"])!.replace(/_/g, " ");
  if (str(e["runner_up_audience"]))
    out["Runner-up audience"] = str(e["runner_up_audience"])!.replace(/_/g, " ");
  if (str(e["winner_audience"]) && card.kind === "audience_loser")
    out["Winning audience"] = str(e["winner_audience"])!.replace(/_/g, " ");

  // 9.1.5 — creative layer
  if (str(e["funnel_stage"]) && card.kind === "funnel_winner")
    out["Buyer stage"] = str(e["funnel_stage"])!.replace(/_/g, " ");
  if (str(e["emotion"]) && card.kind !== "winner")
    out["Feeling"] = str(e["emotion"])!.replace(/_/g, " ");
  if (str(e["pattern_label"]))
    out["Pattern"] = str(e["pattern_label"])!;
  if (str(e["runner_up"]) && card.kind !== "winner")
    out["Runner-up"] = str(e["runner_up"])!.replace(/_/g, " ");

  // 9.1.5 — offer layer
  if (str(e["offer_type"]) && card.kind === "offer_winner")
    out["Offer"] = str(e["offer_type"])!.replace(/_/g, " ");
  if (str(e["runner_up_offer"]))
    out["Runner-up offer"] = str(e["runner_up_offer"])!.replace(/_/g, " ");
  const cvr = num(e["cvr"]);
  if (cvr !== null) out["Conversion rate"] = `${(cvr * 100).toFixed(1)}%`;
  const cvrRatio = num(e["cvr_ratio"]);
  if (cvrRatio !== null && card.kind.startsWith("offer_"))
    out["Conversion ratio"] = `${cvrRatio.toFixed(1)}x`;

  // 9.1.5 — scaling layer
  const advRatio = num(e["cpl_advantage_ratio"]);
  if (advRatio !== null)
    out["Cheaper than average by"] = `${advRatio.toFixed(1)}x`;
  const overrunRatio = num(e["cpl_overrun_ratio"]);
  if (overrunRatio !== null)
    out["Cost overrun"] = `${overrunRatio.toFixed(1)}x average`;
  const brandCpl = num(e["brand_avg_cpl"]);
  if (brandCpl !== null) out["Brand average CPL"] = fmtMoney(brandCpl)!;
  const headroom = num(e["headroom_share"]);
  if (headroom !== null)
    out["Headroom (unspent share)"] = `${Math.round(headroom * 100)}%`;
  const spendShare = num(e["spend_share"]);
  if (spendShare !== null)
    out["Share of total spend"] = `${Math.round(spendShare * 100)}%`;
  const freed = num(e["freed_leads_estimate"]);
  if (freed !== null) out["Leads freed if shifted"] = freed;

  // 9.1.5 — creative DNA apex card
  if (card.kind === "creative_dna") {
    const dnaParts = [
      str(e["audience"]),
      str(e["concept_family"]),
      str(e["emotion"]),
      str(e["offer_type"]),
      str(e["funnel_stage"]),
    ];
    if (dnaParts.every((p) => p !== null)) {
      out["Winning pattern"] = dnaParts
        .map((p) => p!.replace(/_/g, " "))
        .join(" × ");
    }
    if (num(e["creatives_count"]) !== null)
      out["Creatives in this pattern"] = num(e["creatives_count"])!;
  }

  return out;
}

// ---------------------------------------------------------------------
//  Page-level grouping
// ---------------------------------------------------------------------

export interface PerformanceCards {
  /** Sorted by confidence desc. */
  cards: PerformanceOpportunity[];
  /** True when we have any usable card. False = render ComingSoon. */
  hasUsableCards: boolean;
  /** Pass-through, for the header "Last upload" line. */
  lastUploadAt: string | null;
  rowsIngested: number;
  creativesTracked: number;
}

export function translateOverview(
  overview: PerformanceOverview,
): PerformanceCards {
  const cards = overview.diagnostics
    .map(translateDiagnostic)
    .filter((c): c is PerformanceOpportunity => c !== null)
    .sort((a, b) => b.confidence - a.confidence);

  return {
    cards,
    hasUsableCards: cards.length > 0,
    lastUploadAt: overview.last_upload_at,
    rowsIngested: overview.rows_ingested,
    creativesTracked: overview.creatives_tracked,
  };
}

/**
 * 9.1.5 — group cards into the dashboard's 4 intelligence sections
 * plus the baseline + DNA slots. Each section preserves
 * confidence-desc order. Sections with no cards are omitted by the
 * caller so the UI doesn't render empty headers.
 *
 * The DNA section is intentionally rendered FIRST in Simple Mode
 * because it's the highest-information card we ship — it summarises
 * the apex pattern.
 */
export const SECTION_ORDER: PerformanceSection[] = [
  "dna",
  "baseline",
  "scaling",
  "audience",
  "offer",
  "creative",
];

export function groupBySection(
  cards: PerformanceOpportunity[],
): Array<{ section: PerformanceSection; label: string; cards: PerformanceOpportunity[] }> {
  const buckets = new Map<PerformanceSection, PerformanceOpportunity[]>();
  for (const c of cards) {
    if (!buckets.has(c.section)) buckets.set(c.section, []);
    buckets.get(c.section)!.push(c);
  }
  // Stable section order, drop empties.
  return SECTION_ORDER.filter((s) => buckets.has(s)).map((s) => ({
    section: s,
    label: SECTION_LABEL[s],
    cards: buckets.get(s)!,
  }));
}

// Re-export so consumers don't need a second import path.
export type { PerformanceImpactCategory };
