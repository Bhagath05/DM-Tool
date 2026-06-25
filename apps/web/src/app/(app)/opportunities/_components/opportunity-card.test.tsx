/**
 * Phase 6 — OpportunityCard tests.
 *
 * Pins the Constitution contract surface for a single opportunity:
 *   1. All 4 Constitution sections render (what's happening, why it
 *      matters, recommended action, expected result).
 *   2. Confidence pill + reason citation always visible.
 *   3. Generate-this button deep-links to the right studio with the
 *      right URL params for both `target='content'` and `target='ad'`.
 *   4. Simple Mode HIDES the supporting evidence list.
 *   5. Professional Mode SHOWS the supporting evidence list.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Opportunity } from "@/lib/api";
import {
  __resetViewModeForTests,
  setViewMode,
} from "@/lib/view-mode";

import {
  OpportunityCard,
  buildGeneratorHref,
} from "./opportunity-card";

const CONTENT_OPP: Opportunity = {
  id: "00000000-0000-0000-0000-00000000c001",
  kind: "content",
  headline: "People are asking about pricing",
  what_is_happening:
    "Pricing-related questions show up in 3 of your 8 recent lead messages.",
  why_it_matters:
    "Pricing confusion is the most common reason a hot lead goes cold.",
  recommended_action:
    "Create a 60-second pricing comparison reel for Instagram.",
  expected_result: "Could surface 10-20 qualified leads over the following month.",
  confidence: 78,
  reason:
    "Based on pricing search volume +22%, 3 lead messages mention price, Instagram is your winning channel.",
  impact_category: "lead",
  evidence: [
    "Top channel: Instagram (4 of 6 recent leads).",
    "Trending: pricing transparency.",
  ],
  generator: {
    target: "content",
    format: "reel",
    platform: "Instagram",
    goal: "Build brand awareness",
    objective: null,
  },
};

const AD_OPP: Opportunity = {
  id: "00000000-0000-0000-0000-00000000a001",
  kind: "ad",
  headline: "Facebook is producing most leads",
  what_is_happening:
    "Facebook accounts for 6 of your last 10 leads — your clearest winning paid channel.",
  why_it_matters:
    "Allocating budget to the proven channel beats spreading thin across new ones.",
  recommended_action:
    "Increase your Facebook ad budget by 20% for the next 7 days.",
  expected_result: "A 15-30% lift in weekly leads if the offer fits.",
  confidence: 74,
  reason:
    "Based on 6 of 10 recent leads coming from Facebook, conversion holding steady.",
  impact_category: "lead",
  evidence: ["Top channel: Facebook (6/10 leads)."],
  generator: {
    target: "ad",
    format: "meta",
    platform: null,
    goal: "Drive conversions / sales",
    objective: "leads",
  },
};

beforeEach(() => {
  __resetViewModeForTests();
});

afterEach(() => {
  __resetViewModeForTests();
});

describe("OpportunityCard — Constitution contract", () => {
  it("renders all four Constitution sections", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    expect(screen.getByTestId("opportunity-what-is-happening")).toHaveTextContent(
      CONTENT_OPP.what_is_happening,
    );
    expect(screen.getByTestId("opportunity-why-it-matters")).toHaveTextContent(
      CONTENT_OPP.why_it_matters,
    );
    expect(
      screen.getByTestId("opportunity-recommended-action"),
    ).toHaveTextContent(CONTENT_OPP.recommended_action);
    expect(screen.getByTestId("opportunity-expected-result")).toHaveTextContent(
      CONTENT_OPP.expected_result,
    );
  });

  it("renders the headline + confidence + reason citation", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      CONTENT_OPP.headline,
    );
    expect(screen.getByTestId("opportunity-confidence")).toHaveTextContent(
      "78%",
    );
    // Confidence band is plain English, not just a number.
    expect(screen.getByTestId("opportunity-confidence")).toHaveTextContent(
      /confidence/i,
    );
    expect(screen.getByTestId("opportunity-reason")).toHaveTextContent(
      CONTENT_OPP.reason,
    );
  });

  it("renders kind + impact chips", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    expect(screen.getByTestId("opportunity-impact-chip")).toHaveTextContent(
      /lead/i,
    );
    expect(screen.getByTestId("opportunity-card-content")).toBeInTheDocument();
  });
});

describe("OpportunityCard — view mode (Simple vs Professional)", () => {
  it("HIDES supporting evidence in Simple Mode", () => {
    setViewMode("simple");
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    expect(screen.queryByTestId("opportunity-evidence")).toBeNull();
  });

  it("SHOWS supporting evidence in Professional Mode", () => {
    setViewMode("professional");
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    const evidence = screen.getByTestId("opportunity-evidence");
    expect(evidence).toBeInTheDocument();
    expect(evidence).toHaveTextContent(/Top channel: Instagram/);
    expect(evidence).toHaveTextContent(/Trending: pricing transparency/);
  });

  it("doesn't render an empty evidence block even in Professional Mode", () => {
    setViewMode("professional");
    render(
      <OpportunityCard
        opportunity={{ ...CONTENT_OPP, evidence: [] }}
      />,
    );
    expect(screen.queryByTestId("opportunity-evidence")).toBeNull();
  });
});

describe("OpportunityCard — Generate-this deep-link", () => {
  it("deep-links a CONTENT opportunity to /content with type+goal+platform", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    const link = screen.getByTestId("opportunity-generate-link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(
      "/content?type=reel&platform=Instagram&goal=Build+brand+awareness",
    );
  });

  it("deep-links an AD opportunity to /ads with ad_type+objective+goal", () => {
    render(<OpportunityCard opportunity={AD_OPP} />);
    const link = screen.getByTestId("opportunity-generate-link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(
      "/ads?ad_type=meta&objective=leads&goal=Drive+conversions+%2F+sales",
    );
  });
});

// Phase 8 — One-Click Execution. Content opportunities ship a
// Quick Generate primary CTA next to (and ahead of) the deep-link;
// ad opportunities keep the old deep-link as primary because ads
// have their own studio surface with budget/audience inputs.
describe("OpportunityCard — Phase 8 Quick Generate", () => {
  it("renders the Quick Generate button on content opportunities", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    expect(
      screen.getByTestId("opportunity-quick-generate"),
    ).toBeInTheDocument();
  });

  it("demotes the deep-link label to 'Customize first' when Quick Generate is the primary CTA", () => {
    render(<OpportunityCard opportunity={CONTENT_OPP} />);
    const link = screen.getByTestId("opportunity-generate-link");
    expect(link).toHaveTextContent(/customize first/i);
  });

  it("HIDES Quick Generate on AD opportunities and keeps 'Generate this' as the primary CTA", () => {
    render(<OpportunityCard opportunity={AD_OPP} />);
    expect(screen.queryByTestId("opportunity-quick-generate")).toBeNull();
    expect(screen.getByTestId("opportunity-generate-link")).toHaveTextContent(
      /generate this/i,
    );
  });

  it("HIDES Quick Generate when the content format isn't backend-supported (e.g. blog_outline)", () => {
    render(
      <OpportunityCard
        opportunity={{
          ...CONTENT_OPP,
          generator: { ...CONTENT_OPP.generator, format: "blog_outline" },
        }}
      />,
    );
    expect(screen.queryByTestId("opportunity-quick-generate")).toBeNull();
    expect(screen.getByTestId("opportunity-generate-link")).toHaveTextContent(
      /generate this/i,
    );
  });
});

describe("buildGeneratorHref — unit", () => {
  it("omits platform when null on content opps", () => {
    expect(
      buildGeneratorHref({
        target: "content",
        format: "blog_outline",
        platform: null,
        goal: "Educate the audience",
        objective: null,
      }),
    ).toBe("/content?type=blog_outline&goal=Educate+the+audience");
  });

  it("omits objective when null on ad opps", () => {
    expect(
      buildGeneratorHref({
        target: "ad",
        format: "google_search",
        platform: null,
        goal: "Drive engagement",
        objective: null,
      }),
    ).toBe("/ads?ad_type=google_search&goal=Drive+engagement");
  });
});
