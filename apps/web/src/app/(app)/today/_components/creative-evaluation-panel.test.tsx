/**
 * CreativeEvaluationPanel — proves the panel is honest and human-first:
 *  - AI_UNDERPERFORMING surfaces the verdict + a human recommendation (never
 *    "generate more AI") + the mandatory human-approval line;
 *  - INSUFFICIENT_EVIDENCE shows the honest "not enough evidence" state with
 *    no fabricated verdict / confidence.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CreativeEvaluation } from "@/lib/api";

const { mockEval } = vi.hoisted(() => ({ mockEval: vi.fn() }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { ...actual.api, advisor: { ...actual.api.advisor, creativeEvaluation: mockEval } },
  };
});

import { CreativeEvaluationPanel } from "./creative-evaluation-panel";

const BASE: CreativeEvaluation = {
  verdict: "AI_UNDERPERFORMING",
  confidence: 78,
  evidence_source: "local_only",
  ai_sample_size: 4,
  human_sample_size: 4,
  unknown_sample_size: 2,
  diagnosis: "AI-generated creative is underperforming the human-created baseline on engagement.",
  recommended_action:
    "Test human creators / professional UGC before increasing AI-video production. Do not scale AI creative while it trails the human baseline.",
  expected_impact: "A human-created test could recover the gap where AI trails.",
  alternatives: ["Commission human creators / influencers for UGC", "Hire a photographer or videographer"],
  assumptions: ["Provenance labels are correct."],
  risks: ["This is an observed relationship, not proven causation."],
  evidence: ["4 AI-generated vs 4 human-created comparable samples."],
  evidence_limitations: ["No per-creative attributed revenue data available."],
  metric_deltas: [
    { metric: "engagement_rate", label: "engagement", ai_value: 0.02, human_value: 0.03, relative_delta: -0.33, ai_better: false, significant: true },
  ],
  human_approval_required: true,
  generated_at: "2026-09-11T00:00:00Z",
};

beforeEach(() => mockEval.mockReset());
afterEach(() => vi.clearAllMocks());

describe("CreativeEvaluationPanel", () => {
  it("AI_UNDERPERFORMING: shows the verdict, a human recommendation, and the approval line — never 'generate more AI'", async () => {
    mockEval.mockResolvedValue(BASE);
    render(<CreativeEvaluationPanel />);

    expect(await screen.findByTestId("ce-verdict")).toHaveTextContent(/underperforming/i);
    expect(screen.getByTestId("ce-confidence")).toHaveTextContent("78%");
    const rec = screen.getByTestId("ce-recommendation").textContent!.toLowerCase();
    expect(rec).toMatch(/human|ugc/);
    expect(rec).not.toContain("generate more ai");
    // limitation surfaced, and human approval is always shown
    expect(screen.getByTestId("ce-limitations")).toHaveTextContent(/revenue/i);
    expect(screen.getByTestId("ce-approval")).toHaveTextContent(/approve/i);
    // fixture evidence is labelled honestly, not as live data
    expect(screen.getByTestId("ce-evidence-source")).toHaveTextContent(/local/i);
  });

  it("labels provider-verified evidence distinctly from fixtures", async () => {
    mockEval.mockResolvedValue({ ...BASE, evidence_source: "provider_verified" });
    render(<CreativeEvaluationPanel />);
    expect(await screen.findByTestId("ce-evidence-source")).toHaveTextContent(/provider-verified/i);
  });

  it("INSUFFICIENT_EVIDENCE: shows the honest state with no fabricated verdict or confidence", async () => {
    mockEval.mockResolvedValue({
      ...BASE,
      verdict: "INSUFFICIENT_EVIDENCE",
      confidence: 0,
      ai_sample_size: 1,
      human_sample_size: 0,
      metric_deltas: [],
      recommended_action: "Collect more comparable data before shifting creative strategy.",
    });
    render(<CreativeEvaluationPanel />);

    expect(await screen.findByTestId("ce-insufficient")).toHaveTextContent(/enough/i);
    // no confidence badge and no recommendation card in the insufficient state
    expect(screen.queryByTestId("ce-confidence")).toBeNull();
    expect(screen.queryByTestId("ce-recommendation")).toBeNull();
  });

  it("AI_OUTPERFORMING: favors AI but still requires approval and keeps a human control", async () => {
    mockEval.mockResolvedValue({
      ...BASE,
      verdict: "AI_OUTPERFORMING",
      diagnosis: "AI-generated creative is outperforming the human-created baseline on engagement.",
      recommended_action:
        "Keep producing AI creative variations, and run one human-created control against the next batch to confirm the advantage holds.",
      metric_deltas: [
        { metric: "engagement_rate", label: "engagement", ai_value: 0.04, human_value: 0.03, relative_delta: 0.33, ai_better: true, significant: true },
      ],
    });
    render(<CreativeEvaluationPanel />);

    expect(await screen.findByTestId("ce-verdict")).toHaveTextContent(/outperforming/i);
    const rec = screen.getByTestId("ce-recommendation").textContent!.toLowerCase();
    expect(rec).toContain("control"); // even when AI wins, keep a human control
    expect(screen.getByTestId("ce-approval")).toHaveTextContent(/approve/i);
  });
});
