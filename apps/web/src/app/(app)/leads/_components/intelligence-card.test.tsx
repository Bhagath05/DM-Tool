/**
 * Phase 5 — LeadIntelligenceCard tests.
 *
 * The card sits at the top of /leads and answers three Constitution
 * questions immediately:
 *   1. What is happening with my leads right now?
 *   2. What should I do today?
 *   3. What result can I expect?
 *
 * Tests pin:
 *   - Loading skeleton → ready states
 *   - The full hero `<AiRecommendation>` renders with the Constitution
 *     6-section structure (proven via business-metric's testids)
 *   - Per-lead priority rows render with action + expected + reason
 *   - Single 'focus' under "Start here", rest under "Then work through"
 *   - Skip list + signals collapse render when populated
 *   - Empty inbox (zero priorities) doesn't render the priority list
 *   - 409 "no profile" gets its own friendly state
 *   - Generic errors render a "Try again" button
 *   - Cache is honoured on second mount
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type LeadIntelligenceReport } from "@/lib/api";

const intelligenceMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      leads: {
        intelligence: () => intelligenceMock(),
      },
    },
  };
});

import {
  LeadIntelligenceCard,
  __LEAD_INTELLIGENCE_CACHE_KEY,
} from "./intelligence-card";

const SAMPLE_REPORT: LeadIntelligenceReport = {
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
  ],
  skip_for_now: [
    "Don't bulk-email — your inbox is small enough to write 1:1 replies.",
  ],
  counts: {
    total: 8,
    new_count: 5,
    hot_count: 2,
    last_7d: 8,
    last_24h: 3,
  },
  signals_used: [
    "3 fresh leads in the last 24h.",
    "Top channel so far: june-launch — 4 leads, 2 hot.",
  ],
  generated_at: new Date().toISOString(),
};

beforeEach(() => {
  intelligenceMock.mockReset();
  try {
    window.localStorage.removeItem(__LEAD_INTELLIGENCE_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

afterEach(() => {
  intelligenceMock.mockReset();
  try {
    window.localStorage.removeItem(__LEAD_INTELLIGENCE_CACHE_KEY);
  } catch {
    /* jsdom guard */
  }
});

// ---------------------------------------------------------------------
//  Loading / error / no-profile lifecycle
// ---------------------------------------------------------------------

describe("LeadIntelligenceCard lifecycle", () => {
  it("renders loading state immediately on mount", async () => {
    intelligenceMock.mockReturnValue(new Promise(() => {})); // never resolves
    render(<LeadIntelligenceCard />);
    expect(
      screen.getByTestId("lead-intelligence-loading"),
    ).toBeInTheDocument();
  });

  it("renders friendly 'finish onboarding' card on 409", async () => {
    intelligenceMock.mockRejectedValue(
      new ApiError("nope", 409, { detail: "onboard first" }),
    );
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(
        screen.getByTestId("lead-intelligence-no-profile"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/finish business onboarding/i)).toBeInTheDocument();
  });

  it("renders try-again card on transient errors", async () => {
    intelligenceMock.mockRejectedValue(new Error("503 unavailable"));
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence-error")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------
//  Ready state — hero + priorities + skip
// ---------------------------------------------------------------------

describe("LeadIntelligenceCard ready state", () => {
  it("renders the hero AiRecommendation with full Constitution sections", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    render(<LeadIntelligenceCard />);

    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence")).toBeInTheDocument();
    });

    const hero = screen.getByTestId("lead-intelligence-hero");
    expect(hero).toBeInTheDocument();
    // 5 user-facing section headers (AiRecommendation has no technical details)
    const headers = hero.querySelectorAll("h4");
    const headerTexts = Array.from(headers).map((h) => h.textContent);
    expect(headerTexts).toEqual(
      expect.arrayContaining([
        "What is happening?",
        "What should I do?",
        "What result can I expect?",
        "Confidence",
        "Why this recommendation?",
      ]),
    );
  });

  it("surfaces the inbox counts strip", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence")).toBeInTheDocument();
    });
    // The headline is rendered as the card title above the counts.
    expect(
      screen.getByText(/8 leads in the inbox/i),
    ).toBeInTheDocument();
    // Count tiles render their labels in <dt> elements — scope the
    // assertion so we don't collide with "Hot" priority badges below.
    const tileLabels = Array.from(document.querySelectorAll("dt")).map(
      (n) => n.textContent,
    );
    expect(tileLabels).toEqual(
      expect.arrayContaining(["Total", "New", "Hot", "Last 24h"]),
    );
  });

  it("renders priorities split into Start here + Then work through", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(
        screen.getByTestId("lead-intelligence-priorities"),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/start here/i)).toBeInTheDocument();
    expect(screen.getByText(/then work through/i)).toBeInTheDocument();
    // Exactly one 'focus' row
    expect(screen.getAllByTestId("lead-priority-focus")).toHaveLength(1);
    expect(screen.getAllByTestId("lead-priority-hot")).toHaveLength(1);
    expect(screen.getAllByTestId("lead-priority-warm")).toHaveLength(1);
  });

  it("each priority row shows action + expected + reason", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(
        screen.getByTestId("lead-intelligence-priorities"),
      ).toBeInTheDocument();
    });
    const focusRow = screen.getByTestId("lead-priority-focus");
    expect(focusRow).toHaveTextContent("Call within the next 4 hours");
    expect(focusRow).toHaveTextContent("conversation booked within 24h");
    expect(focusRow).toHaveTextContent(/Hot status.*phone number/i);
    expect(focusRow).toHaveTextContent("High value");
    expect(focusRow).toHaveTextContent("Call now");
  });

  it("renders skip list when populated", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence-skip")).toBeInTheDocument();
    });
    expect(screen.getByText(/don't bulk-email/i)).toBeInTheDocument();
  });

  it("hides priority list when there are zero priorities", async () => {
    const zero: LeadIntelligenceReport = {
      ...SAMPLE_REPORT,
      priorities: [],
      counts: { total: 0, new_count: 0, hot_count: 0, last_7d: 0, last_24h: 0 },
      headline: "Your lead inbox is empty — let's get your first one in.",
      hero_recommendation: {
        ...SAMPLE_REPORT.hero_recommendation,
        what_is_happening: "Your lead inbox is empty — nobody has filled out a form yet.",
        recommendation: "Publish a lead page and share its link today.",
      },
    };
    intelligenceMock.mockResolvedValue(zero);
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("lead-intelligence-priorities"),
    ).not.toBeInTheDocument();
  });

  it("calls onReport callback with the ready report", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    const onReport = vi.fn();
    render(<LeadIntelligenceCard onReport={onReport} />);
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(SAMPLE_REPORT);
    });
  });

  it("calls onReport with null on 409 so the parent can clear stale state", async () => {
    intelligenceMock.mockRejectedValue(new ApiError("x", 409, null));
    const onReport = vi.fn();
    render(<LeadIntelligenceCard onReport={onReport} />);
    await waitFor(() => {
      expect(onReport).toHaveBeenCalledWith(null);
    });
  });
});

// ---------------------------------------------------------------------
//  Local cache
// ---------------------------------------------------------------------

describe("LeadIntelligenceCard cache", () => {
  it("uses cached report on second mount, no extra API call", async () => {
    intelligenceMock.mockResolvedValue(SAMPLE_REPORT);
    const { unmount } = render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence")).toBeInTheDocument();
    });
    expect(intelligenceMock).toHaveBeenCalledTimes(1);

    unmount();

    // Re-mount — cache should serve. No new API call.
    render(<LeadIntelligenceCard />);
    await waitFor(() => {
      expect(screen.getByTestId("lead-intelligence")).toBeInTheDocument();
    });
    expect(intelligenceMock).toHaveBeenCalledTimes(1);
  });
});
