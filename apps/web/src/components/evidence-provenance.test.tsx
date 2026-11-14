/**
 * Phase 7.18 — Coach evidence provenance ("Why this recommendation?").
 *
 * The disclosure must trace a recommendation to the business's own evidence
 * honestly: show supporting beliefs with their SERVER-DERIVED confidence +
 * freshness, surface contradictions as "do not rely on", say plainly when
 * there is no validated evidence yet, and render nothing when the server
 * attached no provenance at all (never imply we checked when we didn't).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EvidenceGrounding } from "@/lib/api";

import { EvidenceProvenance } from "./evidence-provenance";

const grounded: EvidenceGrounding = {
  status: "grounded",
  belief_count: 2,
  beliefs: [
    {
      category: "channel",
      subject_key: "channel:ig",
      statement: "Reels beat static for leads",
      confidence: 82,
      evidence_count: 4,
      status: "active",
      freshness_reason: "Current — evidence is fresh (≤30d old); confidence held at 82%.",
    },
    {
      category: "channel",
      subject_key: "channel:email",
      statement: "Email drove signups last year",
      confidence: 51,
      evidence_count: 3,
      status: "active",
      freshness_reason: "Aged down from 80% to 51% — evidence is stale (≥180d old).",
    },
  ],
  contradictions: [
    {
      category: "offer",
      subject_key: "offer:discount",
      statement: "Discounts hurt margin",
      confidence: 28,
      evidence_count: 2,
      status: "contradicted",
      freshness_reason: null,
    },
  ],
  note: "Grounded in measured outcomes; confidence is server-derived.",
};

describe("EvidenceProvenance", () => {
  it("renders nothing when no provenance was attached", () => {
    const { container } = render(<EvidenceProvenance grounding={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows supporting beliefs with server-derived confidence and freshness", () => {
    render(<EvidenceProvenance grounding={grounded} />);
    expect(screen.getByText("Why this recommendation?")).toBeInTheDocument();
    expect(screen.getByText("Reels beat static for leads")).toBeInTheDocument();
    expect(screen.getByText("82% sure")).toBeInTheDocument();
    // Freshness is surfaced, including the stale aging reason.
    expect(screen.getByText(/stale \(≥180d old\)/)).toBeInTheDocument();
    expect(screen.getAllByTestId("supporting-belief")).toHaveLength(2);
  });

  it("surfaces contradictory findings as do-not-rely", () => {
    render(<EvidenceProvenance grounding={grounded} />);
    expect(screen.getByTestId("contradictions")).toBeInTheDocument();
    expect(screen.getByText("Discounts hurt margin")).toBeInTheDocument();
    expect(screen.getByText(/newer results question this/)).toBeInTheDocument();
  });

  it("is honest about insufficient evidence (hypothesis, not proven)", () => {
    const insufficient: EvidenceGrounding = {
      status: "insufficient_evidence",
      belief_count: 0,
      beliefs: [],
      contradictions: [],
      note: "No validated beliefs from past results yet — any recommendation here is a hypothesis.",
    };
    render(<EvidenceProvenance grounding={insufficient} />);
    expect(screen.getByTestId("insufficient-evidence")).toBeInTheDocument();
    expect(screen.queryByTestId("supporting-belief")).not.toBeInTheDocument();
  });
});
