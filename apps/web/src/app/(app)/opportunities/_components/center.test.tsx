/**
 * Phase 6 — OpportunityCenter (page-level) tests.
 *
 * Loading / 409 / generic-error / ready lifecycle. Verifies the hero
 * AiRecommendation renders with all 5 Constitution headers, and the
 * three section blocks (content / ad / skip) only render when the
 * report has data for them. Also confirms the 30-minute cache is
 * honoured on second mount.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type OpportunityCenterReport } from "@/lib/api";

const centerMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      opportunities: {
        center: () => centerMock(),
      },
    },
  };
});

import {
  OpportunityCenter,
  __OPPORTUNITY_CACHE_KEY,
} from "./center";

const SAMPLE: OpportunityCenterReport = {
  headline:
    "Instagram is your winning channel — trends are aligning. This week is about doubling down.",
  hero_recommendation: {
    what_is_happening:
      "Instagram is producing 60% of your leads and 'specialty coffee guides' is trending.",
    impact_category: "lead",
    recommendation:
      "Ship one Instagram reel riding the 'specialty coffee guides' trend before Friday.",
    expected_result: "Likely 5-12 new visitors and 1-2 leads over the following 7 days.",
    confidence: 78,
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
      reason:
        "Based on pricing volume +22% and 3 lead-message hits.",
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
      what_is_happening:
        "Facebook accounts for 6 of your last 10 leads.",
      why_it_matters:
        "Allocating budget to the proven channel beats spreading thin.",
      recommended_action:
        "Increase Facebook ad budget by 20% for 7 days.",
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
  skip_for_now: [
    "Don't add a 5th platform — none of the current 4 are working yet.",
  ],
  signals_used: [
    "8 leads in the inbox, 3 in the last 7 days.",
    "Winning channel so far: Instagram — 5 leads, 1 hot.",
  ],
  generated_at: new Date().toISOString(),
};

beforeEach(() => {
  centerMock.mockReset();
  try {
    window.localStorage.removeItem(__OPPORTUNITY_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

afterEach(() => {
  centerMock.mockReset();
  try {
    window.localStorage.removeItem(__OPPORTUNITY_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

describe("OpportunityCenter — lifecycle", () => {
  it("renders loading state immediately on mount", () => {
    centerMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<OpportunityCenter />);
    expect(screen.getByTestId("opportunities-loading")).toBeInTheDocument();
  });

  it("renders 'finish onboarding' card on 409", async () => {
    centerMock.mockRejectedValue(
      new ApiError("nope", 409, { detail: "onboard first" }),
    );
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByTestId("opportunities-no-profile"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(/finish business onboarding/i),
    ).toBeInTheDocument();
  });

  it("renders try-again card on transient errors", async () => {
    centerMock.mockRejectedValue(new Error("503 unavailable"));
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByTestId("opportunities-error"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });
});

describe("OpportunityCenter — ready state", () => {
  it("renders the hero AiRecommendation with full Constitution sections", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("opportunities")).toBeInTheDocument();
    });
    const hero = screen.getByTestId("opportunities-hero");
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

  it("renders the headline strip", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByText(/Instagram is your winning channel/i),
      ).toBeInTheDocument();
    });
  });

  it("renders content + ad sections with the right cards", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("opportunities")).toBeInTheDocument();
    });
    const contentSection = screen.getByTestId("content-opportunities");
    expect(contentSection).toHaveTextContent(/People are asking about pricing/i);
    const adSection = screen.getByTestId("ad-opportunities");
    expect(adSection).toHaveTextContent(/Facebook is producing most leads/i);
  });

  it("renders the skip-for-now strip when non-empty", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("opportunities-skip")).toBeInTheDocument();
    });
    expect(screen.getByTestId("opportunities-skip")).toHaveTextContent(
      /5th platform/i,
    );
  });

  it("renders the 'how this was built' signals disclosure", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByText(/how this was built/i),
      ).toBeInTheDocument();
    });
  });

  it("renders empty-state copy when no content opportunities", async () => {
    centerMock.mockResolvedValue({
      ...SAMPLE,
      content_opportunities: [],
    });
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByTestId("content-opportunities-empty"),
      ).toBeInTheDocument();
    });
  });

  it("renders empty-state copy when no ad opportunities", async () => {
    centerMock.mockResolvedValue({
      ...SAMPLE,
      ad_opportunities: [],
    });
    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(
        screen.getByTestId("ad-opportunities-empty"),
      ).toBeInTheDocument();
    });
  });
});

describe("OpportunityCenter — cache", () => {
  it("uses cached report on second mount within TTL (no second API call)", async () => {
    centerMock.mockResolvedValue(SAMPLE);
    const { unmount } = render(<OpportunityCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("opportunities")).toBeInTheDocument();
    });
    expect(centerMock).toHaveBeenCalledTimes(1);
    unmount();

    render(<OpportunityCenter />);
    await waitFor(() => {
      expect(screen.getByTestId("opportunities")).toBeInTheDocument();
    });
    // No additional API call — cache hit.
    expect(centerMock).toHaveBeenCalledTimes(1);
  });
});
