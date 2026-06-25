/**
 * Phase 7 — Founder Daily Command Center tests.
 *
 * The /today page exists so a non-marketer doesn't have to open
 * four other screens to figure out their morning. These tests pin
 * the contract that makes that possible:
 *
 *   - Both data sources (leads / advisor intelligence) load in
 *     parallel; a 409 from EITHER core advisor surfaces the
 *     "finish onboarding" empty state for the whole page.
 *   - Every section that renders carries the four Constitution
 *     questions (what's happening · what to do · what to expect · why).
 *   - The hero selection policy is deterministic and locked in:
 *       hot inbox → leads
 *       no hot leads → highest-confidence advisor
 *       trends only counted when they carry the advisory contract
 *   - Ad section ONLY renders when there's an ad opportunity.
 *   - Legacy trend reports (missing recommended_action / confidence)
 *     gracefully degrade to a "Generate trends" nudge instead of
 *     forcing the page to violate the contract.
 *   - The 30-min localStorage cache short-circuits the second mount.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  type LeadIntelligenceReport,
  type OpportunityCenterReport,
  type TrendReport,
} from "@/lib/api";

import {
  intelligenceToAdvisoryTrend,
  type IntelligenceReport,
} from "@/lib/intelligence-adapter";

const leadsMock = vi.fn();
const advisorMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      leads: { intelligence: () => leadsMock() },
      advisor: { intelligence: () => advisorMock() },
    },
  };
});

import {
  CommandCenter,
  __TODAY_CACHE_KEY,
  deriveHeroQuickGenerate,
  pickAdvisoryTrend,
  pickHero,
} from "./command-center";

// ----------------------------------------------------------------------
//  Fixtures
// ----------------------------------------------------------------------

const SAMPLE_LEADS: LeadIntelligenceReport = {
  headline: "8 leads in the inbox — start with the warmest ones from this week.",
  hero_recommendation: {
    what_is_happening:
      "3 fresh leads arrived in the last 48 hours — none contacted yet.",
    impact_category: "revenue",
    recommendation:
      "Reply to the 3 newest leads today, starting with the one who left a phone.",
    expected_result:
      "Typically 1-2 quick conversations booked within 48 hours, with one likely to convert.",
    confidence: 78,
    reason: "Based on 3 fresh leads in the last 48h and none with notes.",
  },
  priorities: [
    {
      lead_id: "lead-1",
      email: "alex@acme.com",
      name: "Alex Founder",
      company: "Acme",
      rank: 1,
      priority: "focus",
      why_now:
        "Marked hot, came in 6h ago via the june-launch campaign, left a phone number.",
      recommended_action:
        "Call within the next 4 hours while the page visit is still fresh.",
      expected_result:
        "A conversation booked within 24h, 1-in-3 chance of converting.",
      confidence: 85,
      reason: "Hot status, recent submission, phone number provided.",
      impact_category: "revenue",
      estimated_value_band: "high",
      cta_label: "Call now",
    },
    {
      lead_id: "lead-2",
      email: "bee@example.com",
      name: null,
      company: null,
      rank: 2,
      priority: "hot",
      why_now: "Marked hot 36 hours ago but never followed up.",
      recommended_action: "Send a one-line follow-up asking a single question.",
      expected_result: "A reply within 48h with a 1-in-4 chance of converting.",
      confidence: 68,
      reason: "Hot status, 36h old, no notes recorded.",
      impact_category: "revenue",
      estimated_value_band: "medium",
      cta_label: "Send email",
    },
    {
      lead_id: "lead-3",
      email: "carol@example.com",
      name: "Carol",
      company: "Tea Co",
      rank: 3,
      priority: "warm",
      why_now: "Recent organic submission with a longer message.",
      recommended_action: "Reply to their message with a personalised note.",
      expected_result: "A reply this week if the offer fits.",
      confidence: 55,
      reason: "Organic source, message length over 20 chars.",
      impact_category: "customer",
      estimated_value_band: "low",
      cta_label: "Reply today",
    },
    {
      lead_id: "lead-4",
      email: "dee@example.com",
      name: null,
      company: null,
      rank: 4,
      priority: "warm",
      why_now: "Old but never replied to.",
      recommended_action: "Send a quick reminder.",
      expected_result: "A reply this week if the offer fits.",
      confidence: 40,
      reason: "Old warm lead.",
      impact_category: "lead",
      estimated_value_band: "low",
      cta_label: "Reply",
    },
  ],
  skip_for_now: [
    "Don't bulk-email — your inbox is small enough to write 1:1 replies.",
  ],
  counts: { total: 8, new_count: 5, hot_count: 2, last_7d: 8, last_24h: 3 },
  signals_used: ["3 fresh leads in the last 24h."],
  generated_at: new Date().toISOString(),
};

const SAMPLE_OPPORTUNITIES: OpportunityCenterReport = {
  headline:
    "Instagram is your winning channel — trends are aligning. This week is about doubling down.",
  hero_recommendation: {
    what_is_happening:
      "Instagram is producing 60% of your leads and 'specialty coffee guides' is trending.",
    impact_category: "lead",
    recommendation:
      "Ship one Instagram reel riding the 'specialty coffee guides' trend before Friday.",
    expected_result:
      "Likely 5-12 new visitors and 1-2 leads over the following 7 days.",
    confidence: 72,
    reason:
      "Based on Instagram producing 60% of leads and trends showing rising interest in specialty guides.",
  },
  content_opportunities: [
    {
      id: "00000000-0000-0000-0000-00000000c001",
      kind: "content",
      headline: "People are asking about pricing",
      what_is_happening:
        "Pricing questions show up in 3 of your 8 recent lead messages.",
      why_it_matters:
        "Pricing confusion is the most common reason a hot lead goes cold.",
      recommended_action:
        "Create a 60-second pricing comparison reel for Instagram.",
      expected_result: "Could surface 10-20 qualified leads over the next month.",
      confidence: 78,
      reason: "Based on pricing volume +22% and 3 lead-message hits.",
      impact_category: "lead",
      evidence: ["Top channel: Instagram (4/6 leads)."],
      generator: {
        target: "content",
        format: "reel",
        platform: "Instagram",
        goal: "Build brand awareness",
        objective: null,
      },
    },
  ],
  ad_opportunities: [
    {
      id: "00000000-0000-0000-0000-00000000a001",
      kind: "ad",
      headline: "Facebook is producing most leads",
      what_is_happening: "Facebook accounts for 6 of your last 10 leads.",
      why_it_matters:
        "Allocating budget to the proven channel beats spreading thin.",
      recommended_action: "Increase Facebook ad budget by 20% for 7 days.",
      expected_result: "A 15-30% lift in weekly leads if the offer fits.",
      confidence: 74,
      reason: "Based on 6 of 10 leads from Facebook.",
      impact_category: "lead",
      evidence: [],
      generator: {
        target: "ad",
        format: "meta",
        platform: null,
        goal: "Drive conversions / sales",
        objective: "leads",
      },
    },
  ],
  skip_for_now: ["Don't add a 5th platform yet."],
  signals_used: ["Winning channel so far: Instagram — 5 leads, 1 hot."],
  generated_at: new Date().toISOString(),
};

const SAMPLE_TREND: TrendReport = {
  id: "trend-1",
  user_id: "u-1",
  status: "completed",
  raw_trends: {
    google_trends: [],
    reddit_posts: [],
    sources_attempted: ["google", "reddit"],
    sources_failed: [],
  },
  analysis: {
    summary: "Specialty coffee interest is climbing across your platforms.",
    trending_topics: [
      {
        topic: "Specialty coffee guides",
        why_it_matters: "Your audience is asking espresso questions on Reddit.",
        suggested_angles: ["Bean-by-bean walkthrough"],
        relevance_score: 78,
        recommended_action:
          "Post a 60-second Instagram reel walking through your espresso bean selection.",
        expected_result:
          "Likely 80-150 extra people see it; 1-3 walk in this week.",
        confidence: 78,
        reason:
          "'Espresso bean comparison' is rising +45% on Google Trends and your audience is on Instagram.",
      },
    ],
    content_ideas: [
      {
        platform: "Instagram",
        format: "reel",
        hook: "The 30-second bean test we use every morning.",
        description: "Show how you taste-test a new bean shipment.",
      },
    ],
    hashtag_clusters: [
      {
        theme: "Specialty coffee",
        hashtags: ["#coffee", "#specialtycoffee", "#barista"],
      },
    ],
    marketing_angles: ["Lead with the bean origin story."],
  },
  analysis_error: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const LEADS_NO_HOT: LeadIntelligenceReport = {
  ...SAMPLE_LEADS,
  counts: { ...SAMPLE_LEADS.counts, hot_count: 0 },
  hero_recommendation: { ...SAMPLE_LEADS.hero_recommendation, confidence: 55 },
};

function buildAdvisorIntelligence(
  overrides: Partial<IntelligenceReport> = {},
): IntelligenceReport {
  const topic = SAMPLE_TREND.analysis!.trending_topics[0];
  const base: IntelligenceReport = {
    ready: true,
    hero: {
      observation: SAMPLE_OPPORTUNITIES.hero_recommendation.what_is_happening,
      root_cause: SAMPLE_OPPORTUNITIES.hero_recommendation.reason,
      recommended_action: SAMPLE_OPPORTUNITIES.hero_recommendation.recommendation,
      expected_impact: SAMPLE_OPPORTUNITIES.hero_recommendation.expected_result,
      confidence: SAMPLE_OPPORTUNITIES.hero_recommendation.confidence,
      data_sources_used: [],
      impact_category: SAMPLE_OPPORTUNITIES.hero_recommendation.impact_category,
    },
    content_opportunities: SAMPLE_OPPORTUNITIES.content_opportunities.map((o) => ({
      kind: "content" as const,
      headline: o.headline,
      observation: o.what_is_happening,
      root_cause: o.why_it_matters,
      recommended_action: o.recommended_action,
      expected_impact: o.expected_result,
      confidence: o.confidence,
      data_sources_used: [],
      impact_category: o.impact_category,
      generator_hint: o.generator,
      id: o.id,
    })),
    ad_opportunities: SAMPLE_OPPORTUNITIES.ad_opportunities.map((o) => ({
      kind: "ad" as const,
      headline: o.headline,
      observation: o.what_is_happening,
      root_cause: o.why_it_matters,
      recommended_action: o.recommended_action,
      expected_impact: o.expected_result,
      confidence: o.confidence,
      data_sources_used: [],
      impact_category: o.impact_category,
      generator_hint: o.generator,
      id: o.id,
    })),
    trend: {
      observation: topic.why_it_matters,
      root_cause: topic.reason!,
      recommended_action: topic.recommended_action!,
      expected_impact: topic.expected_result!,
      confidence: topic.confidence!,
      data_sources_used: [],
    },
    daily_brief: null,
    signals_used: SAMPLE_OPPORTUNITIES.signals_used,
    confidence_cap: 95,
    generated_at: SAMPLE_OPPORTUNITIES.generated_at,
  };
  return { ...base, ...overrides };
}

const SAMPLE_ADVISOR = buildAdvisorIntelligence();

const SAMPLE_INTEL_TREND = intelligenceToAdvisoryTrend(SAMPLE_ADVISOR.trend)!;

function combinedReport(
  partial: {
    leads: LeadIntelligenceReport;
    opportunities: OpportunityCenterReport;
    intelligenceTrend?: ReturnType<typeof intelligenceToAdvisoryTrend>;
    dailyBrief?: IntelligenceReport["daily_brief"];
    trend?: TrendReport | null;
  },
) {
  return {
    intelligenceTrend: null,
    dailyBrief: null,
    trend: null,
    ...partial,
  };
}

// ----------------------------------------------------------------------
//  Setup / teardown
// ----------------------------------------------------------------------

beforeEach(() => {
  leadsMock.mockReset();
  advisorMock.mockReset();
  try {
    window.localStorage.removeItem(__TODAY_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

afterEach(() => {
  leadsMock.mockReset();
  advisorMock.mockReset();
  try {
    window.localStorage.removeItem(__TODAY_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

// ----------------------------------------------------------------------
//  Lifecycle
// ----------------------------------------------------------------------

describe("CommandCenter — lifecycle", () => {
  it("renders the loading shell while the two fetches are in-flight", () => {
    leadsMock.mockReturnValue(new Promise(() => {}));
    advisorMock.mockReturnValue(new Promise(() => {}));
    render(<CommandCenter />);
    expect(screen.getByTestId("today-loading")).toBeInTheDocument();
  });

  it("surfaces the no-profile card when EITHER core advisor returns 409", async () => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockRejectedValue(new ApiError("nope", 409, {}));

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-no-profile")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/finish business onboarding first/i),
    ).toBeInTheDocument();
  });

  it("surfaces no-profile when the LEADS endpoint returns 409 too", async () => {
    leadsMock.mockRejectedValue(new ApiError("nope", 409, {}));
    advisorMock.mockResolvedValue(SAMPLE_ADVISOR);

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-no-profile")).toBeInTheDocument();
    });
  });

  it("falls through to a 'try again' error card on transient failures", async () => {
    leadsMock.mockRejectedValue(new Error("503 unavailable"));
    advisorMock.mockResolvedValue(SAMPLE_ADVISOR);

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-error")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
//  Full ready state — all six sections
// ----------------------------------------------------------------------

describe("CommandCenter — full ready state", () => {
  beforeEach(() => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockResolvedValue(SAMPLE_ADVISOR);
  });

  async function mount() {
    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
  }

  it("renders all six sections in the prescribed order", async () => {
    await mount();
    const root = screen.getByTestId("today-command-center");
    const sectionOrder = [
      "today-hero",
      "today-leads",
      "today-opportunity",
      "today-trend",
      "today-ad",
      "today-impact",
    ];
    const seen = sectionOrder
      .map((id) => root.querySelector(`[data-testid="${id}"]`))
      .filter(Boolean);
    expect(seen).toHaveLength(sectionOrder.length);

    // Verify DOM order matches the prescribed sequence (each section
    // must precede the next).
    for (let i = 0; i < seen.length - 1; i++) {
      // eslint-disable-next-line no-bitwise
      const rel = seen[i]!.compareDocumentPosition(seen[i + 1]!);
      expect(rel & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("hero renders the full Constitution 6-section AiRecommendation", async () => {
    await mount();
    const hero = screen.getByTestId("today-hero-recommendation");
    const headers = Array.from(hero.querySelectorAll("h4")).map(
      (h) => h.textContent,
    );
    expect(headers).toEqual(
      expect.arrayContaining([
        "What is happening?",
        "What should I do?",
        "What result can I expect?",
        "Confidence",
        "Why this recommendation?",
      ]),
    );
  });

  it("section 2 shows only the top 3 lead rows, never more", async () => {
    await mount();
    const leadsSection = screen.getByTestId("today-leads");
    // PriorityRow stamps data-testid="lead-priority-<bucket>"; count
    // them inside the leads section only.
    const rows = leadsSection.querySelectorAll(
      "[data-testid^='lead-priority-']",
    );
    expect(rows.length).toBe(3);
    // The 4th lead in the fixture must NOT show up here.
    expect(leadsSection).not.toHaveTextContent(/dee@example\.com/);
  });

  it("section 2 surfaces a link back to the full inbox", async () => {
    await mount();
    const link = screen.getByTestId("today-leads-open-inbox");
    expect(link).toHaveAttribute("href", "/leads");
  });

  it("growth opportunity renders the content opportunity card with a Generate link", async () => {
    await mount();
    const oppSection = screen.getByTestId("today-opportunity");
    expect(oppSection).toHaveTextContent(/people are asking about pricing/i);
    const generateLink = oppSection.querySelector(
      "[data-testid='opportunity-generate-link']",
    ) as HTMLAnchorElement | null;
    expect(generateLink).not.toBeNull();
    // Deep-link should target /content with the format pre-filled.
    expect(generateLink!.getAttribute("href")).toMatch(/^\/content\?/);
    expect(generateLink!.getAttribute("href")).toContain("type=reel");
  });

  it("trend section answers the four Constitution questions and shows a tier pill", async () => {
    await mount();
    const trend = screen.getByTestId("today-trend-card");
    expect(trend).toHaveTextContent(/post a 60-second instagram reel/i);
    expect(trend).toHaveTextContent(/post a 60-second instagram reel/i);
    expect(trend).toHaveTextContent(/80-150 extra people see it/i);
    expect(trend).toHaveTextContent(/espresso bean comparison/i);
    // 78% confidence → Medium tier in the local band map.
    expect(screen.getByTestId("today-trend-confidence")).toHaveTextContent(
      /medium/i,
    );
  });

  it("ad section renders when an ad opportunity exists", async () => {
    await mount();
    const ad = screen.getByTestId("today-ad");
    expect(ad).toHaveTextContent(/facebook is producing most leads/i);
    // Deep-link should target /ads with the ad_type pre-filled.
    const generateLink = ad.querySelector(
      "[data-testid='opportunity-generate-link']",
    ) as HTMLAnchorElement | null;
    expect(generateLink).not.toBeNull();
    expect(generateLink!.getAttribute("href")).toMatch(/^\/ads\?/);
    expect(generateLink!.getAttribute("href")).toContain("ad_type=meta");
  });

  it("expected-impact section lists one line per active surface", async () => {
    await mount();
    const impact = screen.getByTestId("today-impact");
    // Four lines: leads, content opp, trend, ad opp.
    expect(impact.querySelector("[data-testid='today-impact-line-0']")).not.toBeNull();
    expect(impact.querySelector("[data-testid='today-impact-line-1']")).not.toBeNull();
    expect(impact.querySelector("[data-testid='today-impact-line-2']")).not.toBeNull();
    expect(impact.querySelector("[data-testid='today-impact-line-3']")).not.toBeNull();
    // The headline echoes the hero's expected result.
    expect(impact).toHaveTextContent(
      /typically 1-2 quick conversations booked within 48 hours/i,
    );
  });

  // Phase 8 — One-Click Execution. The trend section ships a Quick
  // Generate primary CTA next to the secondary "See full report" link.
  it("trend section renders a Quick Generate button for advisory trends", async () => {
    await mount();
    expect(
      screen.getByTestId("today-trend-quick-generate"),
    ).toBeInTheDocument();
  });

  // The hero is a leads recommendation in the default fixture (hot_count
  // ≥ 1), so Quick Generate must be hidden — replying to leads isn't
  // a content-generation action.
  it("HIDES the hero Quick Generate when the hero source is leads", async () => {
    await mount();
    expect(screen.queryByTestId("today-hero-quick-generate")).toBeNull();
  });
});

// ----------------------------------------------------------------------
//  Conditional / graceful-degrade behaviour
// ----------------------------------------------------------------------

describe("CommandCenter — section conditionals", () => {
  it("hides the ad section when no ad opportunities exist", async () => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockResolvedValue(
      buildAdvisorIntelligence({ ad_opportunities: [] }),
    );

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("today-ad")).not.toBeInTheDocument();
  });

  it("degrades the trend section to a 'Generate trends' nudge when no report exists", async () => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockResolvedValue(buildAdvisorIntelligence({ trend: null }));

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-trend")).toBeInTheDocument();
    });
    // No trend card, but an empty-state nudge with a deep-link.
    expect(screen.queryByTestId("today-trend-card")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open trends/i })).toHaveAttribute(
      "href",
      "/trends",
    );
  });

  it("degrades the trend section when intelligence has no trend signal", async () => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockResolvedValue(buildAdvisorIntelligence({ trend: null }));

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-trend")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("today-trend-card")).not.toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------
//  Phase 8 — Hero Quick Generate by source
// ----------------------------------------------------------------------

describe("CommandCenter — Phase 8 hero Quick Generate", () => {
  it("RENDERS the hero Quick Generate when the hero source is opportunities", async () => {
    // No hot leads → hero falls through to the opportunities advisor,
    // which has a higher confidence than LEADS_NO_HOT.
    leadsMock.mockResolvedValue(LEADS_NO_HOT);
    advisorMock.mockResolvedValue(SAMPLE_ADVISOR);

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("today-hero-quick-generate"),
    ).toBeInTheDocument();
  });

  it("RENDERS the hero Quick Generate when the hero source is a trend", async () => {
    leadsMock.mockResolvedValue(LEADS_NO_HOT);
    advisorMock.mockResolvedValue(
      buildAdvisorIntelligence({
        hero: {
          ...SAMPLE_ADVISOR.hero!,
          confidence: 50,
        },
      }),
    );

    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("today-hero-quick-generate"),
    ).toBeInTheDocument();
  });
});

describe("deriveHeroQuickGenerate — policy", () => {
  it("returns null when the hero source is leads (reply, don't post)", () => {
    expect(
      deriveHeroQuickGenerate({
        hero: {
          source: "leads",
          what: "x",
          action: "y",
          expected: "z",
          confidence: 50,
          reason: "r",
          impact: "lead",
        },
        topContentOpp: SAMPLE_OPPORTUNITIES.content_opportunities[0],
        topTrend: pickAdvisoryTrend(SAMPLE_TREND),
      }),
    ).toBeNull();
  });

  it("returns the opportunity-backed context when hero source is opportunities", () => {
    const ctx = deriveHeroQuickGenerate({
      hero: {
        source: "opportunities",
        what: "Instagram is winning.",
        action: "Ship one Instagram reel by Friday.",
        expected: "1-2 leads over the following week.",
        confidence: 72,
        reason: "Instagram drives 60% of your leads.",
        impact: "lead",
      },
      topContentOpp: SAMPLE_OPPORTUNITIES.content_opportunities[0],
      topTrend: null,
    });
    expect(ctx).not.toBeNull();
    expect(ctx?.request.content_type).toBe("reel");
    // Hero wording overrides the opportunity wording so the modal
    // reads as a literal follow-through of the button.
    expect(ctx?.source.headline).toMatch(/ship one instagram reel/i);
    expect(ctx?.source.confidence).toBe(72);
  });

  it("returns the trend-backed context when hero source is trend", () => {
    const ctx = deriveHeroQuickGenerate({
      hero: {
        source: "trend",
        what: "x",
        action: "Ride the espresso wave with a reel this week.",
        expected: "1-3 walk-ins this week.",
        confidence: 78,
        reason: "+45% on Google Trends.",
        impact: "lead",
      },
      topContentOpp: null,
      topTrend: pickAdvisoryTrend(SAMPLE_TREND),
    });
    expect(ctx).not.toBeNull();
    expect(ctx?.request.content_type).toBe("social_post");
    expect(ctx?.source.headline).toMatch(/ride the espresso wave/i);
  });

  it("returns null when no underlying signal is available", () => {
    expect(
      deriveHeroQuickGenerate({
        hero: {
          source: "opportunities",
          what: "x",
          action: "y",
          expected: "z",
          confidence: 50,
          reason: "r",
          impact: "lead",
        },
        topContentOpp: null,
        topTrend: null,
      }),
    ).toBeNull();
  });
});

// ----------------------------------------------------------------------
//  Cache
// ----------------------------------------------------------------------

describe("CommandCenter — cache", () => {
  it("short-circuits to localStorage on second mount without re-firing the network", async () => {
    leadsMock.mockResolvedValue(SAMPLE_LEADS);
    advisorMock.mockResolvedValue(SAMPLE_ADVISOR);

    const first = render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
    expect(leadsMock).toHaveBeenCalledTimes(1);
    expect(advisorMock).toHaveBeenCalledTimes(1);

    first.unmount();
    render(<CommandCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("today-command-center")).toBeInTheDocument();
    });
    // Cache hit — no new calls on second mount.
    expect(leadsMock).toHaveBeenCalledTimes(1);
    expect(advisorMock).toHaveBeenCalledTimes(1);
  });
});

// ----------------------------------------------------------------------
//  pickHero — deterministic policy
// ----------------------------------------------------------------------

describe("pickHero — deterministic selection", () => {
  it("returns the lead hero whenever the inbox has at least one hot lead", () => {
    const hero = pickHero(
      combinedReport({
        leads: SAMPLE_LEADS, // hot_count = 2
        opportunities: SAMPLE_OPPORTUNITIES,
        intelligenceTrend: SAMPLE_INTEL_TREND,
      }),
    );
    expect(hero.source).toBe("leads");
  });

  it("falls back to the opportunities hero when no hot leads + opportunities have higher confidence", () => {
    const hero = pickHero(
      combinedReport({
        leads: LEADS_NO_HOT, // hot_count = 0, hero confidence = 55
        opportunities: SAMPLE_OPPORTUNITIES, // hero confidence = 72
      }),
    );
    expect(hero.source).toBe("opportunities");
  });

  it("promotes the trend hero when it has the highest confidence and the contract is satisfied", () => {
    const hero = pickHero(
      combinedReport({
        leads: LEADS_NO_HOT, // 55
        opportunities: {
          ...SAMPLE_OPPORTUNITIES,
          hero_recommendation: {
            ...SAMPLE_OPPORTUNITIES.hero_recommendation,
            confidence: 60,
          },
        },
        intelligenceTrend: SAMPLE_INTEL_TREND, // 78
      }),
    );
    expect(hero.source).toBe("trend");
  });

  it("ignores trend candidates whose topics lack the advisory contract", () => {
    const hero = pickHero(
      combinedReport({
        leads: LEADS_NO_HOT,
        opportunities: SAMPLE_OPPORTUNITIES,
        trend: {
          ...SAMPLE_TREND,
          analysis: {
            ...SAMPLE_TREND.analysis!,
            trending_topics: [
              {
                topic: "legacy",
                why_it_matters: "x",
                suggested_angles: ["y"],
                relevance_score: 90,
                recommended_action: null,
                expected_result: null,
                confidence: null,
                reason: null,
              },
            ],
          },
        },
        intelligenceTrend: null,
      }),
    );
    expect(hero.source).toBe("opportunities");
  });
});

// ----------------------------------------------------------------------
//  pickAdvisoryTrend — pure helper
// ----------------------------------------------------------------------

describe("pickAdvisoryTrend", () => {
  it("returns null when the trend report is null", () => {
    expect(pickAdvisoryTrend(null)).toBeNull();
  });

  it("returns null when the report is still pending", () => {
    expect(
      pickAdvisoryTrend({ ...SAMPLE_TREND, status: "pending", analysis: null }),
    ).toBeNull();
  });

  it("returns null when every topic is legacy (no advisory fields)", () => {
    expect(
      pickAdvisoryTrend({
        ...SAMPLE_TREND,
        analysis: {
          ...SAMPLE_TREND.analysis!,
          trending_topics: [
            {
              topic: "Old topic",
              why_it_matters: "x",
              suggested_angles: ["y"],
              relevance_score: 50,
              recommended_action: null,
              expected_result: null,
              confidence: null,
              reason: null,
            },
          ],
        },
      }),
    ).toBeNull();
  });

  it("picks the highest-confidence advisory topic", () => {
    const t = pickAdvisoryTrend({
      ...SAMPLE_TREND,
      analysis: {
        ...SAMPLE_TREND.analysis!,
        trending_topics: [
          {
            ...SAMPLE_TREND.analysis!.trending_topics[0],
            topic: "A",
            confidence: 60,
          },
          {
            ...SAMPLE_TREND.analysis!.trending_topics[0],
            topic: "B",
            confidence: 88,
          },
          {
            ...SAMPLE_TREND.analysis!.trending_topics[0],
            topic: "C",
            confidence: 40,
          },
        ],
      },
    });
    expect(t?.topic).toBe("B");
  });
});
