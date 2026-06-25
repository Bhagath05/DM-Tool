/**
 * Phase 10.0 — Performance card UI derivations.
 *
 * Pure functions over `PerformanceOpportunity` that compute the
 * founder-facing chips the new card layout displays:
 *
 *   - Priority        (HIGH / MEDIUM / LOW)        from confidence band
 *   - Effort          (e.g. "5 minutes")           from kind
 *   - Expected Leads  (e.g. "+30")                 from evidence
 *   - Revenue Impact  (e.g. "₹45,000 potential")   from evidence × value/lead
 *
 * Strict rules (Constitution-aligned):
 *   - We NEVER fabricate revenue numbers when there's no signal — return
 *     null and the UI hides the chip.
 *   - We NEVER ship "Expected Leads" as a fake number for diagnostics
 *     that can't produce one (e.g. a winner card whose evidence carries
 *     only existing conversions). For those, we surface the existing
 *     conversion volume framed as "this brought you N leads."
 *   - Priority is HARDCAPPED to MEDIUM unless confidence ≥ 80 — we
 *     don't ship "HIGH priority" off a medium-confidence rule.
 */

import type { PerformanceOpportunity } from "@/lib/performance-translator";

export type Priority = "HIGH" | "MEDIUM" | "LOW";

export interface DerivedCardChips {
  priority: Priority;
  effort: string;
  /** "+30 leads" or "Already delivered 30 leads" — never empty. */
  expectedLeads: string | null;
  /** "₹45,000 potential" — null when we have no value signal. */
  revenueImpact: string | null;
}

/**
 * Map diagnostic kind → estimated effort in plain English. Calibrated
 * to founder language ("5 minutes", "1 click") — never engineering
 * time ("M effort", "Story Point 3").
 */
const EFFORT_BY_KIND: Record<PerformanceOpportunity["kind"], string> = {
  // Baseline (9.1)
  winner: "5 minutes",
  loser: "5 minutes",
  fatigue: "10 minutes",
  audience_shift: "10 minutes",
  budget_reallocation: "1 click",
  // 9.1.5
  audience_winner: "5 minutes",
  audience_loser: "1 click",
  concept_winner: "20 minutes",
  emotion_winner: "20 minutes",
  funnel_winner: "20 minutes",
  pattern_winner: "30 minutes",
  offer_winner: "10 minutes",
  offer_pricing_sensitivity: "15 minutes",
  scale_candidate: "1 click",
  budget_waste: "1 click",
  creative_dna: "1 hour",
};

export function priorityFromConfidence(confidence: number): Priority {
  if (confidence >= 80) return "HIGH";
  if (confidence >= 60) return "MEDIUM";
  return "LOW";
}

function formatLeads(n: number): string {
  if (n <= 0) return "—";
  return `+${Math.round(n)}`;
}

function formatMoney(value: number, currency: string | null): string {
  if (!currency) return Math.round(value).toLocaleString();
  if (value >= 1000) {
    return `${currency} ${Math.round(value).toLocaleString()}`;
  }
  return `${currency} ${value.toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })}`;
}

/**
 * Best-effort extraction of currency from the evidence blob the
 * recommender wrote. Different kinds use different keys; we try the
 * known ones in order. Returns null if none are present — the caller
 * then hides the money chip.
 */
function pickCurrency(evidence: Record<string, unknown>): string | null {
  const candidates = [
    evidence["currency"],
    evidence["winner_currency"],
  ];
  for (const c of candidates) {
    if (typeof c === "string" && c.trim().length > 0) return c.trim();
  }
  return null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Estimate the expected extra leads from this card. Always honest:
 *   - scale_candidate → roughly `spend / cpl` (the same math the
 *     recommender uses in its expected_result line, made numeric).
 *   - budget_waste / audience_loser → freed_leads_estimate if the
 *     evidence carries one; else null.
 *   - audience_winner / concept/emotion/funnel/pattern/offer winners
 *     → 20% lift on the winner's converted leads (matches the
 *     copy's "15-30% more leads at the same spend").
 *   - creative_dna → 30% lift on the winning pattern's conversions
 *     (matches the recommender's "30-50% more leads" copy).
 *   - winner / budget_reallocation → fall back to the conversions
 *     the creative ALREADY delivered, framed as past tense — never
 *     fabricated future leads.
 */
function estimateExtraLeads(
  card: PerformanceOpportunity,
): { count: number | null; alreadyDelivered: number | null } {
  const e = card.evidence ?? {};
  const conv = num(e["conversions"]);

  switch (card.kind) {
    case "scale_candidate": {
      const cpl = num(e["cpl"]);
      const spend = num(e["spend"]);
      if (cpl && cpl > 0 && spend && spend > 0) {
        return { count: spend / cpl, alreadyDelivered: conv };
      }
      return { count: null, alreadyDelivered: conv };
    }
    case "budget_waste":
    case "audience_loser": {
      const freed = num(e["freed_leads_estimate"]);
      if (freed !== null && freed > 0) {
        return { count: freed, alreadyDelivered: conv };
      }
      return { count: null, alreadyDelivered: conv };
    }
    case "audience_winner":
    case "concept_winner":
    case "emotion_winner":
    case "funnel_winner":
    case "pattern_winner":
    case "offer_winner":
    case "offer_pricing_sensitivity":
      return { count: conv ? conv * 0.2 : null, alreadyDelivered: conv };
    case "creative_dna":
      return { count: conv ? conv * 0.3 : null, alreadyDelivered: conv };
    case "winner":
    case "budget_reallocation":
    default:
      return { count: null, alreadyDelivered: conv };
  }
}

/**
 * Value-per-lead heuristic. If the evidence carries
 * conversion_value AND conversions, we can compute it cleanly. We
 * NEVER carry forward a brand-default — that's the kind of fabrication
 * the Constitution forbids.
 */
function valuePerLead(evidence: Record<string, unknown>): number | null {
  const conv = num(evidence["conversions"]);
  const value = num(evidence["conversion_value"]);
  if (conv && conv > 0 && value && value > 0) return value / conv;
  return null;
}

/**
 * The single derive() entry point the card layout calls.
 */
export function derive(card: PerformanceOpportunity): DerivedCardChips {
  const priority = priorityFromConfidence(card.confidence);
  const effort = EFFORT_BY_KIND[card.kind] ?? "10 minutes";
  const { count, alreadyDelivered } = estimateExtraLeads(card);
  const currency = pickCurrency(card.evidence ?? {});

  // "Expected Leads" copy:
  //   - if we have a forward-looking estimate → "+N"
  //   - else if we have an already-delivered count → "N delivered"
  //   - else null (UI hides the chip)
  let expectedLeads: string | null;
  if (count !== null && count >= 1) {
    expectedLeads = `${formatLeads(count)} leads`;
  } else if (alreadyDelivered !== null && alreadyDelivered > 0) {
    expectedLeads = `${alreadyDelivered} delivered`;
  } else {
    expectedLeads = null;
  }

  // "Revenue Impact" only computed when we have a value/lead signal.
  // Multiply by forward-looking leads when available; else by the
  // already-delivered count framed as "already earned".
  let revenueImpact: string | null = null;
  const vpl = valuePerLead(card.evidence ?? {});
  if (vpl !== null) {
    if (count !== null && count >= 1) {
      revenueImpact = `${formatMoney(count * vpl, currency)} potential`;
    } else if (alreadyDelivered !== null && alreadyDelivered > 0) {
      revenueImpact = `${formatMoney(alreadyDelivered * vpl, currency)} delivered`;
    }
  }

  return { priority, effort, expectedLeads, revenueImpact };
}
