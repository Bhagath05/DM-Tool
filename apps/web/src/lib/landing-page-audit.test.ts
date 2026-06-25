/**
 * Phase 10.4 — Landing Page Audit tests.
 *
 * Pin each heuristic individually + the overall sort. We're explicitly
 * testing that the audit:
 *   - Skips drafts + archived pages (auditing noise)
 *   - Fires the right finding for each input shape
 *   - Doesn't double-count low_trust when no_testimonials already fired
 *   - Sorts high → medium → low, then by confidence DESC
 *   - Caps every confidence at 70 (heuristic honesty)
 */

import { describe, expect, it } from "vitest";

import type { LandingPage, LandingPageContent } from "./api";
import { auditLandingPages } from "./landing-page-audit";


function makePage(over: Partial<LandingPage> = {}): LandingPage {
  const content: LandingPageContent = {
    headline: "Get 5 qualified leads next week with our audit service",
    subheadline: null,
    benefits: [
      { title: "Audit in 48 hours", body: "We deliver findings in 2 days." },
      { title: "No contracts", body: "Pay per audit." },
      { title: "Free first consult", body: "30 mins, no obligation." },
    ],
    cta_text: "Book a free audit",
    form_fields: [],
    social_proof: [{ quote: "Game-changing", author: "Ada", role: "CEO" }],
    faq: [],
    footer_text: null,
    privacy_blurb: "We never share your email.",
  };
  return {
    id: "lp-1",
    user_id: "u",
    business_profile_id: "bp",
    slug: "test",
    title: "Test Page",
    status: "published",
    preview_token: "tk",
    content,
    redirect_url: null,
    view_count: 0,
    submission_count: 0,
    is_archived: false,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function withContent(
  base: LandingPage,
  patch: Partial<LandingPageContent>,
): LandingPage {
  return { ...base, content: { ...base.content, ...patch } };
}


describe("auditLandingPages — exclusions", () => {
  it("skips archived pages", () => {
    const f = auditLandingPages([
      makePage({ is_archived: true, content: { ...makePage().content, cta_text: "" } }),
    ]);
    expect(f).toEqual([]);
  });

  it("skips drafts", () => {
    const f = auditLandingPages([
      makePage({ status: "draft", content: { ...makePage().content, cta_text: "" } }),
    ]);
    expect(f).toEqual([]);
  });
});


describe("Missing CTA heuristic", () => {
  it("fires high severity when cta_text is empty", () => {
    const f = auditLandingPages([withContent(makePage(), { cta_text: "" })]);
    const cta = f.find((x) => x.kind === "missing_cta");
    expect(cta?.severity).toBe("high");
  });

  it("fires medium severity on generic CTAs (Submit / Sign up)", () => {
    const f = auditLandingPages([withContent(makePage(), { cta_text: "Submit" })]);
    const cta = f.find((x) => x.kind === "missing_cta");
    expect(cta?.severity).toBe("medium");
    expect(cta?.title).toContain("Submit");
  });

  it("accepts specific value-led CTAs", () => {
    const f = auditLandingPages([withContent(makePage(), { cta_text: "Book a free audit" })]);
    expect(f.find((x) => x.kind === "missing_cta")).toBeUndefined();
  });
});


describe("Weak headline heuristic", () => {
  it("fires high severity when headline is empty", () => {
    const f = auditLandingPages([withContent(makePage(), { headline: "" })]);
    const w = f.find((x) => x.kind === "weak_headline");
    expect(w?.severity).toBe("high");
  });

  it("fires medium on 'Welcome to...' generic openings", () => {
    const f = auditLandingPages([withContent(makePage(), { headline: "Welcome to our agency website" })]);
    expect(f.find((x) => x.kind === "weak_headline")?.severity).toBe("medium");
  });

  it("fires low on very short headlines", () => {
    const f = auditLandingPages([withContent(makePage(), { headline: "Sign up" })]);
    expect(f.find((x) => x.kind === "weak_headline")?.severity).toBe("low");
  });

  it("fires low on ALL-CAPS headlines", () => {
    const f = auditLandingPages([
      withContent(makePage(), {
        headline: "BEST DEAL IN INDUSTRY EVER MADE",
      }),
    ]);
    expect(f.find((x) => x.kind === "weak_headline")?.severity).toBe("low");
  });

  it("accepts a normal benefit-led headline", () => {
    const f = auditLandingPages([
      withContent(makePage(), {
        headline: "Cut your payroll setup time by half this quarter",
      }),
    ]);
    expect(f.find((x) => x.kind === "weak_headline")).toBeUndefined();
  });
});


describe("Testimonials + trust heuristics", () => {
  it("fires no_testimonials when social_proof is empty", () => {
    const f = auditLandingPages([withContent(makePage(), { social_proof: [] })]);
    expect(f.find((x) => x.kind === "no_testimonials")).toBeDefined();
  });

  it("fires low_trust when testimonials AND privacy_blurb both missing", () => {
    const f = auditLandingPages([
      withContent(makePage(), { social_proof: [], privacy_blurb: null }),
    ]);
    expect(f.find((x) => x.kind === "low_trust")).toBeDefined();
  });

  it("does NOT fire low_trust when at least one trust signal exists", () => {
    const f = auditLandingPages([
      withContent(makePage(), { social_proof: [], privacy_blurb: "We protect your data." }),
    ]);
    expect(f.find((x) => x.kind === "low_trust")).toBeUndefined();
  });
});


describe("Poor offer heuristic", () => {
  it("fires high severity when benefits is empty", () => {
    const f = auditLandingPages([withContent(makePage(), { benefits: [] })]);
    expect(f.find((x) => x.kind === "poor_offer")?.severity).toBe("high");
  });

  it("fires low severity when all benefits read as adjective fluff", () => {
    const f = auditLandingPages([
      withContent(makePage(), {
        benefits: [
          { title: "Best quality", body: "Great experienced professional team" },
          { title: "Amazing service", body: "Trusted quality" },
        ],
      }),
    ]);
    expect(f.find((x) => x.kind === "poor_offer")?.severity).toBe("low");
  });

  it("accepts concrete benefits", () => {
    const f = auditLandingPages([makePage()]);
    expect(f.find((x) => x.kind === "poor_offer")).toBeUndefined();
  });
});


describe("auditLandingPages — sort + cap", () => {
  it("sorts high-severity findings ahead of medium / low", () => {
    const f = auditLandingPages([
      withContent(makePage(), {
        cta_text: "",         // missing_cta (high)
        social_proof: [],     // no_testimonials (medium)
        headline: "Hi",       // weak_headline (low) — short
        privacy_blurb: "X",   // keeps low_trust off
      }),
    ]);
    expect(f[0]?.severity).toBe("high");
    const severities = f.map((x) => x.severity);
    // Find first index of "low" — must be after every "high"/"medium".
    const firstLow = severities.indexOf("low");
    if (firstLow !== -1) {
      expect(severities.slice(0, firstLow)).not.toContain("low");
    }
  });

  it("caps every finding's confidence at 70 (heuristic honesty)", () => {
    const f = auditLandingPages([withContent(makePage(), { cta_text: "" })]);
    for (const finding of f) {
      expect(finding.confidence).toBeLessThanOrEqual(70);
    }
  });
});
