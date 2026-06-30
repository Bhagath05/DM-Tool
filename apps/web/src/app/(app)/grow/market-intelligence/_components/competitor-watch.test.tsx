/**
 * Competitor Watch — live AI analysis wired to GET /competitors/analysis.
 * Pins: real results render, the 409 "add competitors" empty state, the
 * error+retry state, and the analytics.view RBAC gate.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CompetitorAnalysisResponse } from "@/lib/api";

const analysisMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { ...actual.api, competitors: { analysis: () => analysisMock() } },
  };
});

let canValue = true;
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({ can: () => canValue }),
}));

import { CompetitorWatch } from "./competitor-watch";
import { ApiError } from "@/lib/api";

const DATA: CompetitorAnalysisResponse = {
  market_summary: "Customers choose on vibe and price.",
  competitors: [
    {
      name: "Roasted Down the Road",
      positioning: "Fast and cheap, grab-and-go.",
      strengths: ["Speed"],
      gaps: ["No seating to linger"],
      content_angles: ["Daily deal posts"],
      your_move: "Own the cozy work-from-here vibe they can't match.",
      confidence: 70,
    },
  ],
  recommendation: "Launch a weekday 'work from here' loyalty card.",
  reason: "Your seating + remote-worker audience is the clearest edge.",
  confidence: 72,
  expected_result: "Likely 5-12 more weekday regulars within 6-8 weeks.",
};

describe("CompetitorWatch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    canValue = true;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the live AI analysis with the recommendation contract", async () => {
    analysisMock.mockResolvedValue(DATA);
    render(<CompetitorWatch />);

    expect(
      await screen.findByTestId("competitor-watch-results"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Customers choose on vibe and price."),
    ).toBeInTheDocument();
    expect(screen.getByText("Roasted Down the Road")).toBeInTheDocument();
    expect(
      screen.getByText(/Own the cozy work-from-here vibe/),
    ).toBeInTheDocument();
    // Constitution recommendation block: recommendation + why + expected.
    const rec = screen.getByTestId("competitor-watch-recommendation");
    expect(rec).toHaveTextContent("work from here");
    expect(rec).toHaveTextContent("What to expect:");
  });

  it("shows an actionable empty state when no competitors are listed (409)", async () => {
    analysisMock.mockRejectedValue(
      new ApiError("Add the competitors you want to track.", 409, null),
    );
    render(<CompetitorWatch />);

    expect(
      await screen.findByTestId("competitor-watch-empty"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Add the competitors you want to track."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /add competitors/i }),
    ).toHaveAttribute("href", "/onboarding/profile");
  });

  it("shows an error + retry on a non-409 failure", async () => {
    analysisMock.mockRejectedValue(new ApiError("server boom", 500, null));
    render(<CompetitorWatch />);

    expect(
      await screen.findByTestId("competitor-watch-error"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("gates on analytics.view RBAC and does not call the API when denied", async () => {
    canValue = false;
    render(<CompetitorWatch />);

    expect(
      await screen.findByTestId("competitor-watch-locked"),
    ).toBeInTheDocument();
    expect(analysisMock).not.toHaveBeenCalled();
  });
});
