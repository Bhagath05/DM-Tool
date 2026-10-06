/**
 * T4 — trust-aware generative UI.
 *
 * These prove the frontend is PRESENTATION ONLY: it renders exactly the
 * server-authoritative trust envelope, never computing, upgrading, or
 * re-deriving a status/confidence. Status is conveyed by text (not color
 * alone); an AI-inference source never reads as verified; evidence disclosure
 * never exposes chain-of-thought.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentAnswer } from "./agent-response";
import {
  ClaimBlock,
  SourceBadge,
  TrustMetricCard,
  TrustRecommendation,
  TrustStatusPill,
  TrustSummaryBlock,
} from "./blocks";
import type {
  AgentResponse,
  TrustClaimView,
  TrustEnvelope,
  TrustStatus,
} from "@/lib/api";

const ALL_STATUSES: TrustStatus[] = [
  "supported",
  "qualified",
  "downgraded",
  "insufficient_evidence",
  "contradicted",
  "mixed_evidence",
  "high_risk_requires_review",
];

function claim(over: Partial<TrustClaimView> = {}): TrustClaimView {
  return {
    statement: "CTR increased after the new creative launched.",
    claim_type: "observation",
    claim_type_label: "Observation",
    trust_status: "supported",
    confidence: 72,
    source: "First-party data",
    causal_level: null,
    evidence_labels: ["performance"],
    limitations: [],
    safe_language: "The available verified evidence supports this conclusion.",
    ...over,
  };
}

function envelope(over: Partial<TrustEnvelope> = {}): TrustEnvelope {
  return {
    status: "supported",
    safe_language: "The available verified evidence supports this conclusion.",
    server_confidence: 72,
    verdict: "accept",
    disclosures: [],
    claims: [],
    metrics: [],
    recommendations: [],
    summary: {
      supported: 0, qualified: 0, downgraded: 0, insufficient: 0,
      contradicted: 0, mixed: 0, not_computable_metrics: 0, high_risk_recommendations: 0,
    },
    enforced: true,
    degraded: false,
    ...over,
  };
}

function response(trust: TrustEnvelope | null, over: Partial<AgentResponse> = {}): AgentResponse {
  return {
    conversation_id: "c1",
    message_id: "m1",
    answer: "Here is what the data shows.",
    evidence_status: "ok",
    confidence: 72,
    tools_consulted: ["performance"],
    evidence: [],
    actions_blocked: [],
    approval_required: false,
    proposed_actions: [],
    reasoning_summary: {
      intent: "assess performance",
      tools_consulted: ["performance"],
      evidence_used: ["performance"],
      key_observations: ["CTR rose"],
      uncertainty: "Attribution window is short.",
      conclusion: "CTR rose.",
    },
    trust,
    ...over,
  };
}

describe("trust status presentation", () => {
  it("renders every trust status with an accessible text label (not color alone)", () => {
    for (const status of ALL_STATUSES) {
      const { unmount } = render(<TrustStatusPill status={status} />);
      // A human-readable label is always present as text.
      expect(screen.getByText(/supported|qualified|adjusted|insufficient|contradicted|mixed|review/i)).toBeInTheDocument();
      unmount();
    }
  });

  it("status glyphs are decorative (aria-hidden), label carries meaning", () => {
    render(<TrustStatusPill status="contradicted" />);
    expect(screen.getByText("Contradicted")).toBeInTheDocument();
    // the glyph is aria-hidden
    const glyph = screen.getByText("×");
    expect(glyph).toHaveAttribute("aria-hidden");
  });
});

describe("source provenance", () => {
  it("AI inference is visually cautious and never labeled verified", () => {
    render(<SourceBadge source="AI inference" />);
    const badge = screen.getByTestId("brain-source");
    expect(badge).toHaveTextContent("AI inference");
    expect(badge).not.toHaveTextContent(/verified/i);
    expect(badge.className).toMatch(/dashed/); // distinct cautious styling
  });

  it("verified data is NOT styled cautiously", () => {
    render(<SourceBadge source="Verified" />);
    expect(screen.getByTestId("brain-source").className).not.toMatch(/dashed/);
  });
});

describe("ClaimBlock", () => {
  it("renders the claim, its type, status, confidence and source exactly as given", () => {
    render(<ClaimBlock claim={claim({ confidence: 87, claim_type_label: "Observation" })} />);
    const block = screen.getByTestId("brain-claim");
    expect(block).toHaveTextContent("CTR increased after the new creative launched.");
    expect(block).toHaveTextContent("Observation");
    expect(block).toHaveTextContent("Supported");
    expect(block).toHaveTextContent("87");
    expect(block).toHaveTextContent("First-party data");
  });

  it("an insufficient claim shows no confidence number (frontend never invents one)", () => {
    render(<ClaimBlock claim={claim({ trust_status: "insufficient_evidence", confidence: 0 })} />);
    expect(screen.getByTestId("brain-claim")).toHaveTextContent(/insufficient evidence/i);
    expect(screen.queryByTestId("brain-confidence")).not.toBeInTheDocument();
  });

  it("surfaces causal level and limitations for a downgraded causal claim", () => {
    render(
      <ClaimBlock
        claim={claim({
          statement: "The video caused the lift.",
          trust_status: "downgraded",
          causal_level: "observational",
          limitations: ["Evidence is observational; causal language requires a controlled design."],
        })}
      />,
    );
    const block = screen.getByTestId("brain-claim");
    expect(block).toHaveTextContent(/observational/i);
    expect(block).toHaveTextContent(/controlled design/i);
    expect(block).toHaveTextContent(/adjusted to fit evidence/i);
  });
});

describe("TrustMetricCard", () => {
  it("shows a verified value", () => {
    render(
      <TrustMetricCard
        metric={{ name: "ctr", value: 4.8, unit: "%", computable: true, status: "ok", reason: null, source: "First-party data" }}
      />,
    );
    const card = screen.getByTestId("brain-metric");
    expect(card).toHaveTextContent("4.8");
    expect(card).toHaveTextContent("CTR");
  });

  it("a NOT_COMPUTABLE metric shows 'Not available' + why, never a number", () => {
    render(
      <TrustMetricCard
        metric={{ name: "roas", value: null, unit: "x", computable: false, status: "not_computable", reason: "Required inputs could not be verified.", source: "Verified" }}
      />,
    );
    const card = screen.getByTestId("brain-metric");
    expect(card).toHaveTextContent(/not available/i);
    expect(card).toHaveTextContent(/could not be verified/i);
    expect(card).not.toHaveTextContent(/\b0\b/); // never a fake zero
  });
});

describe("TrustRecommendation", () => {
  it("a high-consequence recommendation shows consequence + requires human approval", () => {
    render(
      <TrustRecommendation
        rec={{ action: "Increase budget 40%", status: "high_risk_requires_review", consequence: "high", requires_approval: true, safe_language: "This recommendation has meaningful consequences..." }}
      />,
    );
    const block = screen.getByTestId("brain-trust-recommendation");
    expect(block).toHaveTextContent("Increase budget 40%");
    expect(block).toHaveTextContent("HIGH");
    expect(block).toHaveTextContent(/human approval required/i);
    expect(block).toHaveTextContent(/human review required/i);
  });

  it("a low-consequence recommendation does not demand approval", () => {
    render(
      <TrustRecommendation
        rec={{ action: "Test the new headline", status: "supported", consequence: "low", requires_approval: false, safe_language: "The available verified evidence supports this conclusion." }}
      />,
    );
    expect(screen.getByTestId("brain-trust-recommendation")).not.toHaveTextContent(/human approval required/i);
  });

  it("surfaces 'what would change this' and a suggested experiment (T5)", () => {
    render(
      <TrustRecommendation
        rec={{
          action: "Increase budget 40%",
          status: "high_risk_requires_review",
          consequence: "high",
          requires_approval: true,
          safe_language: "This recommendation has meaningful consequences...",
          what_would_change: [
            "A controlled experiment — current evidence is only observational and cannot establish causation.",
          ],
          suggested_experiment: {
            hypothesis: 'Whether "Increase budget 40%" holds up under a controlled comparison.',
            variants: ["the proposed change", "the current baseline"],
            hold_constant: ["audience", "objective"],
            success_metric: "a predefined primary metric",
            approval_required: true,
          },
        }}
      />,
    );
    expect(screen.getByTestId("brain-what-would-change")).toHaveTextContent(/controlled experiment/i);
    const exp = screen.getByTestId("brain-experiment-suggestion");
    expect(exp).toHaveTextContent(/suggested test instead/i);
    expect(exp).toHaveTextContent(/the proposed change vs the current baseline/i);
    expect(exp).toHaveTextContent(/approval required before running/i);
  });
});

describe("TrustSummaryBlock", () => {
  it("renders only non-zero counts, compactly", () => {
    render(
      <TrustSummaryBlock
        summary={{ supported: 4, qualified: 1, downgraded: 0, insufficient: 1, contradicted: 0, mixed: 0, not_computable_metrics: 1, high_risk_recommendations: 0 }}
      />,
    );
    const block = screen.getByTestId("brain-trust-summary");
    expect(block).toHaveTextContent("4");
    expect(block).toHaveTextContent("Supported");
    expect(block).toHaveTextContent("Insufficient");
    expect(block).toHaveTextContent(/metrics not available/i);
  });
});

describe("AgentAnswer trust integration", () => {
  it("renders structured claims, metrics, recommendations and summary from the envelope", () => {
    const env = envelope({
      status: "downgraded",
      claims: [
        claim({ statement: "CTR is 4.8%.", claim_type_label: "Observation", trust_status: "supported" }),
        claim({ statement: "The video caused it.", trust_status: "downgraded", causal_level: "observational" }),
      ],
      metrics: [{ name: "ctr", value: 4.8, unit: "%", computable: true, status: "ok", reason: null, source: "First-party data" }],
      recommendations: [{ action: "Run a controlled test", status: "supported", consequence: "low", requires_approval: false, safe_language: "ok" }],
      summary: { supported: 1, qualified: 0, downgraded: 1, insufficient: 0, contradicted: 0, mixed: 0, not_computable_metrics: 0, high_risk_recommendations: 0 },
    });
    render(<AgentAnswer response={response(env)} />);
    expect(within(screen.getByTestId("brain-claims")).getAllByTestId("brain-claim")).toHaveLength(2);
    expect(screen.getByTestId("brain-metrics")).toBeInTheDocument();
    expect(screen.getByTestId("brain-trust-recommendation")).toHaveTextContent("Run a controlled test");
    expect(screen.getByTestId("brain-trust-summary")).toBeInTheDocument();
  });

  it("the evidence disclosure never exposes chain-of-thought", () => {
    render(<AgentAnswer response={response(envelope())} />);
    const reasoning = screen.getByTestId("brain-reasoning");
    expect(reasoning).toHaveTextContent(/intent/i);
    const blob = reasoning.textContent?.toLowerCase() ?? "";
    expect(blob).not.toContain("chain_of_thought");
    expect(blob).not.toContain("reasoning tokens");
    expect(blob).not.toContain("system prompt");
  });

  it("renders the legacy footer when no trust envelope is present (backward compatible)", () => {
    render(<AgentAnswer response={response(null)} />);
    expect(screen.getByTestId("brain-answer")).toBeInTheDocument();
    expect(screen.queryByTestId("brain-claims")).not.toBeInTheDocument();
  });
});
