/**
 * Phase 10.4 — Landing Page Audit (heuristic, frontend-only).
 *
 * No backend "audit this landing page" endpoint exists. We compute the
 * 5 directive-named issue types client-side from data the existing
 * `api.landingPages.list()` already returns:
 *
 *   Missing CTA       — cta_text empty / one-word generic
 *   Weak headline     — too short, generic phrasing, all-caps
 *   Low trust         — no social_proof AND no privacy_blurb
 *   No testimonials   — social_proof[] is empty
 *   Poor offer        — benefits[] is empty OR all benefit titles are generic
 *
 * Each finding includes a founder-friendly title + recommendation + a
 * confidence score (heuristic — not LLM-derived, capped at 70). The
 * UI labels these as heuristic to avoid implying LLM-grade insight.
 */

import type { LandingPage } from "./api";

export type AuditFindingKind =
  | "missing_cta"
  | "weak_headline"
  | "low_trust"
  | "no_testimonials"
  | "poor_offer";

export type FindingSeverity = "high" | "medium" | "low";

export interface AuditFinding {
  id: string;
  page_id: string;
  page_title: string;
  page_slug: string;
  kind: AuditFindingKind;
  severity: FindingSeverity;
  /** Founder-friendly title. */
  title: string;
  /** What to do about it. */
  recommendation: string;
  /** Heuristic confidence 0-70 (capped — we're not an LLM). */
  confidence: number;
}

const GENERIC_CTAS = new Set([
  "submit", "send", "go", "click", "sign up", "sign-up",
  "get started", "continue", "next", "ok",
]);

const WEAK_HEADLINE_HINTS = [
  "welcome to",
  "hello",
  "home",
  "our website",
  "untitled",
];

const GENERIC_BENEFIT_WORDS = new Set([
  "great", "amazing", "best", "quality", "professional",
  "experienced", "trusted",
]);

// ---------------------------------------------------------------------
//  Per-rule heuristics
// ---------------------------------------------------------------------

function checkMissingCta(page: LandingPage): AuditFinding | null {
  const cta = (page.content.cta_text ?? "").trim().toLowerCase();
  if (!cta) {
    return finding(page, "missing_cta", "high", 65, {
      title: "No call-to-action",
      recommendation:
        "Add a specific CTA like 'Get a free audit' or 'Book a 15-min call'. Generic blank buttons cost ~30% of would-be leads.",
    });
  }
  if (GENERIC_CTAS.has(cta) || cta.length < 4) {
    return finding(page, "missing_cta", "medium", 55, {
      title: `Weak CTA: "${page.content.cta_text}"`,
      recommendation:
        "Swap the generic CTA for one that names the value (e.g. 'See your custom plan', 'Book a free strategy call').",
    });
  }
  return null;
}

function checkWeakHeadline(page: LandingPage): AuditFinding | null {
  const headline = (page.content.headline ?? "").trim();
  if (!headline) {
    return finding(page, "weak_headline", "high", 65, {
      title: "No headline",
      recommendation:
        "Add a headline that names the outcome ('Get 5 qualified leads next week') in 7-12 words.",
    });
  }
  const lower = headline.toLowerCase();
  if (WEAK_HEADLINE_HINTS.some((h) => lower.startsWith(h))) {
    return finding(page, "weak_headline", "medium", 55, {
      title: "Generic headline opening",
      recommendation:
        "Replace '" + headline.split(" ").slice(0, 2).join(" ") +
        "...' with a benefit-led line — what does the visitor get if they fill the form?",
    });
  }
  if (headline.length < 18) {
    return finding(page, "weak_headline", "low", 45, {
      title: "Headline is shorter than 18 characters",
      recommendation:
        "Extend the headline to 7-12 words so the value proposition is unmistakable above the fold.",
    });
  }
  if (headline === headline.toUpperCase() && headline.length > 12) {
    return finding(page, "weak_headline", "low", 45, {
      title: "Headline is in ALL CAPS",
      recommendation:
        "All-caps headlines test ~20% lower on engagement. Use sentence case to feel less shouty.",
    });
  }
  return null;
}

function checkNoTestimonials(page: LandingPage): AuditFinding | null {
  if ((page.content.social_proof ?? []).length === 0) {
    return finding(page, "no_testimonials", "medium", 55, {
      title: "No testimonials",
      recommendation:
        "Add 1-3 short customer quotes with name + role. Pages with social proof convert ~15-25% better.",
    });
  }
  return null;
}

function checkLowTrust(page: LandingPage): AuditFinding | null {
  const hasTestimonials = (page.content.social_proof ?? []).length > 0;
  const hasPrivacy = !!page.content.privacy_blurb?.trim();
  // Only fire when BOTH trust signals are missing — testimonials alone
  // is covered by checkNoTestimonials.
  if (!hasTestimonials && !hasPrivacy) {
    return finding(page, "low_trust", "medium", 50, {
      title: "Low trust signals",
      recommendation:
        "Add a one-line privacy reassurance under the form ('We never share your email') — costs a sentence, lifts conversion.",
    });
  }
  return null;
}

function checkPoorOffer(page: LandingPage): AuditFinding | null {
  const benefits = page.content.benefits ?? [];
  if (benefits.length === 0) {
    return finding(page, "poor_offer", "high", 60, {
      title: "No benefits listed",
      recommendation:
        "List 3-5 concrete benefits the visitor gets (each 1-2 sentences). Without them, the headline does all the convincing.",
    });
  }
  const allGeneric = benefits.every((b) => {
    const text = (b.title + " " + b.body).toLowerCase();
    const words = text.split(/\s+/);
    const genericRatio =
      words.filter((w) => GENERIC_BENEFIT_WORDS.has(w)).length /
      Math.max(words.length, 1);
    return genericRatio > 0.2;
  });
  if (allGeneric && benefits.length > 0) {
    return finding(page, "poor_offer", "low", 40, {
      title: "Benefits read as generic adjectives",
      recommendation:
        "Replace adjective benefits ('great quality') with specifics ('audit in 48 hrs', 'no contracts').",
    });
  }
  return null;
}

// ---------------------------------------------------------------------
//  Orchestrator
// ---------------------------------------------------------------------

const CHECKS: ((page: LandingPage) => AuditFinding | null)[] = [
  checkMissingCta,
  checkWeakHeadline,
  checkNoTestimonials,
  checkLowTrust,
  checkPoorOffer,
];

/**
 * Run every heuristic against every published landing page. Returns
 * findings sorted by severity (high > medium > low) then confidence
 * DESC so the founder sees the most actionable issues first.
 *
 * Archived + draft pages are skipped — auditing a draft is noise.
 */
export function auditLandingPages(pages: LandingPage[]): AuditFinding[] {
  const findings: AuditFinding[] = [];
  for (const page of pages) {
    if (page.is_archived) continue;
    if (page.status !== "published") continue;
    for (const check of CHECKS) {
      const f = check(page);
      if (f) findings.push(f);
    }
  }
  const severityRank: Record<FindingSeverity, number> = {
    high: 0,
    medium: 1,
    low: 2,
  };
  findings.sort((a, b) => {
    if (a.severity !== b.severity) {
      return severityRank[a.severity] - severityRank[b.severity];
    }
    return b.confidence - a.confidence;
  });
  return findings;
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function finding(
  page: LandingPage,
  kind: AuditFindingKind,
  severity: FindingSeverity,
  confidence: number,
  body: Pick<AuditFinding, "title" | "recommendation">,
): AuditFinding {
  return {
    id: `${page.id}:${kind}`,
    page_id: page.id,
    page_title: page.title,
    page_slug: page.slug,
    kind,
    severity,
    confidence: Math.min(70, confidence), // heuristic cap
    ...body,
  };
}
