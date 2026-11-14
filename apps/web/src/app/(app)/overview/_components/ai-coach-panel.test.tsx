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
import type { EvidenceGrounding, WeeklyPlan } from "@/lib/api";

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

const grounded: EvidenceGrounding = {
  status: "grounded",
  belief_count: 2,
  beliefs: [
    {
      category: "channel", subject_key: "channel:ig",
      statement: "Reels beat static for leads",
      confidence: 84, evidence_count: 4, status: "active",
      freshness_reason: "Current — evidence is fresh (≤30d old); confidence held at 84%.",
    },
    {
      category: "channel", subject_key: "channel:email",
      statement: "Email drove signups last year",
      confidence: 51, evidence_count: 3, status: "active",
      freshness_reason: "Aged down from 80% to 51% — evidence is stale (≥180d old).",
    },
  ],
  contradictions: [
    {
      category: "offer", subject_key: "offer:discount",
      statement: "Discounts hurt margin",
      confidence: 28, evidence_count: 2, status: "contradicted", freshness_reason: null,
    },
  ],
  note: "Grounded in measured outcomes; confidence is server-derived.",
};

function planWith(grounding: EvidenceGrounding | null): WeeklyPlan {
  return { ...plan(70), evidence_grounding: grounding };
}

afterEach(() => vi.clearAllMocks());

describe("AiCoachPanel evidence provenance (Phase 7.18a)", () => {
  it("surfaces supporting beliefs with server-derived confidence + freshness, and contradictions", async () => {
    weekly.mockResolvedValue(planWith(grounded));
    render(<AiCoachPanel />);
    expect(await screen.findByText("Why this recommendation?")).toBeInTheDocument();
    expect(screen.getByText("Reels beat static for leads")).toBeInTheDocument();
    expect(screen.getByText("84% sure")).toBeInTheDocument();
    expect(screen.getByText(/stale \(≥180d old\)/)).toBeInTheDocument();
    expect(screen.getByTestId("contradictions")).toBeInTheDocument();
    expect(screen.getByText("Discounts hurt margin")).toBeInTheDocument();
  });

  it("is honest when evidence is insufficient (hypothesis, not proven)", async () => {
    weekly.mockResolvedValue(
      planWith({
        status: "insufficient_evidence", belief_count: 0, beliefs: [], contradictions: [],
        note: "No validated beliefs from past results yet — a hypothesis.",
      }),
    );
    render(<AiCoachPanel />);
    expect(await screen.findByTestId("insufficient-evidence")).toBeInTheDocument();
    expect(screen.queryByTestId("supporting-belief")).not.toBeInTheDocument();
  });

  it("renders the card without a provenance panel when none is attached (missing provenance)", async () => {
    weekly.mockResolvedValue(planWith(null));
    render(<AiCoachPanel />);
    expect(await screen.findByTestId("ai-coach-card")).toBeInTheDocument();
    expect(screen.queryByText("Why this recommendation?")).not.toBeInTheDocument();
  });
});

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
