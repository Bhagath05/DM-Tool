/**
 * Phase 6.7 — AI Coach evidence honesty.
 *
 * The weekly-focus confidence is the AI's OWN estimate of the recommendation
 * (LLM self-assessed, or a heuristic in the deterministic fallback). It must be
 * framed as such — never as a number "calibrated to the data we've seen", which
 * is false for a new or low-data workspace with nothing to calibrate against.
 * The lead projection is a forecast and must read as one ("Expected result"),
 * never as measured customer data.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { weekly } = vi.hoisted(() => ({ weekly: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, coach: { ...actual.api.coach, weekly } },
  };
});

import { AiCoachPanel } from "./ai-coach-panel";
import type { WeeklyPlan } from "@/lib/api";

function plan(confidence = 70): WeeklyPlan {
  return {
    headline: "Launch your first lead page.",
    week_focus: "Get one page live so traffic becomes leads.",
    actions: [
      {
        action_title: "Publish your first lead page",
        why: "Without a page, no channel can capture leads.",
        business_impact: "First real path to capturing leads.",
        impact_category: "lead",
        expected_result:
          "Expect to capture 5-10 leads once the page is live and promoted.",
        confidence,
        reason: "Based on the missing lead-page signal.",
        cta_label: "Build a page",
        cta_target: "lead_pages",
        priority: "focus",
        estimated_time: "half a day",
      },
    ],
    skip_this_week: [],
    signals_used: [],
    generated_at: "2026-10-09T00:00:00Z",
  };
}

afterEach(() => vi.clearAllMocks());

describe("AiCoachPanel evidence honesty", () => {
  it("frames confidence as the AI's own estimate, not 'calibrated to the data'", async () => {
    weekly.mockResolvedValue(plan(70));
    render(<AiCoachPanel />);
    const conf = await screen.findByTestId("ai-coach-confidence");
    expect(conf).toHaveTextContent("70%");
    expect(conf.textContent ?? "").not.toMatch(/calibrated to the data/i);
    expect(conf).toHaveTextContent(/the AI's confidence/i);
  });

  it("labels the lead projection as an Expected result (forecast), not measured data", async () => {
    weekly.mockResolvedValue(plan(70));
    render(<AiCoachPanel />);
    const expected = await screen.findByTestId("ai-coach-expected");
    expect(expected).toHaveTextContent(/expected result/i);
    expect(expected).toHaveTextContent(/5-10 leads/);
  });
});
