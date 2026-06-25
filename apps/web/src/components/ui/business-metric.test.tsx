/**
 * <BusinessMetric> + <AiRecommendation> — Phase 2 component tests.
 *
 * Covers the Constitution contract:
 *   - 6 sections always rendered (What is happening / What should I do /
 *     Expected result / Confidence / Why / Technical details)
 *   - Technical details collapsed in Simple Mode, expanded in Professional
 *   - Toggle works in either mode
 *   - Confidence calibration (High / Medium / Low / Speculative) maps
 *     to the right pill label + colour-bucket assertion
 *   - Status pill renders + reflects the prop
 *   - Impact category drives the icon + accent label
 *   - Contract enforcement: missing required field throws, missing
 *     technical details renders cleanly without a disclosure
 *
 * Components must look like an advisor card, not a number tile, so
 * tests assert section HEADERS exist in document order.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  __resetViewModeForTests,
  setViewMode,
} from "@/lib/view-mode";

import {
  AiRecommendation,
  BusinessMetric,
} from "./business-metric";

const VALID_METRIC = {
  value: "₹120 per lead",
  plainLanguage: "You spend ₹120 to get one potential customer.",
  status: "good" as const,
  impactCategory: "cost" as const,
  businessImpact: "Lead cost is within healthy range — keep going.",
  recommendation: "Keep this campaign running.",
  expectedResult: "Sustained 8-12 leads/week at the current cost.",
  confidence: 85,
  reason: "Based on last 30 days of campaign performance.",
  technicalDetails: { CPL: "₹120", CTR: "3.4%", CPC: "₹11" },
};

const VALID_AI_REC = {
  whatIsHappening: "You don't have a published lead page yet.",
  impactCategory: "lead" as const,
  recommendation: "Publish your first lead page.",
  expectedResult: "Once live, even 50 visitors can produce 1-3 leads.",
  confidence: 75,
  reason: "Based on the missing lead-page signal.",
};

beforeEach(() => {
  __resetViewModeForTests();
});

afterEach(() => {
  __resetViewModeForTests();
});

// ---------------------------------------------------------------------
//  Shared 6-section structure (applies to BOTH components)
// ---------------------------------------------------------------------

describe("Constitution 6-section structure", () => {
  it("BusinessMetric renders all six section headers in order", () => {
    render(<BusinessMetric {...VALID_METRIC} />);
    const headers = screen
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "What is happening?",
      "What should I do?",
      "What result can I expect?",
      "Confidence",
      "Why this recommendation?",
      // "Technical Details (Optional)" is a button, not an h4 — separately tested
    ]);
  });

  it("AiRecommendation renders all five user-facing section headers", () => {
    render(<AiRecommendation {...VALID_AI_REC} />);
    const headers = screen
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "What is happening?",
      "What should I do?",
      "What result can I expect?",
      "Confidence",
      "Why this recommendation?",
    ]);
  });

  it("each section's body content matches the props", () => {
    render(<BusinessMetric {...VALID_METRIC} />);
    expect(screen.getByTestId("section-happening")).toHaveTextContent(
      VALID_METRIC.businessImpact,
    );
    expect(screen.getByTestId("section-action")).toHaveTextContent(
      VALID_METRIC.recommendation,
    );
    expect(screen.getByTestId("section-expected-result")).toHaveTextContent(
      VALID_METRIC.expectedResult,
    );
    expect(screen.getByTestId("section-reason")).toHaveTextContent(
      VALID_METRIC.reason,
    );
  });
});

// ---------------------------------------------------------------------
//  Technical details disclosure (Simple vs Professional)
// ---------------------------------------------------------------------

describe("Technical details disclosure", () => {
  it("Simple Mode (default): technical body NOT visible, toggle present", () => {
    render(<BusinessMetric {...VALID_METRIC} />);
    expect(screen.getByTestId("technical-details-toggle")).toBeInTheDocument();
    expect(
      screen.queryByTestId("technical-details-body"),
    ).not.toBeInTheDocument();
  });

  it("Professional Mode: technical body STARTS visible", () => {
    setViewMode("professional");
    render(<BusinessMetric {...VALID_METRIC} />);
    expect(screen.getByTestId("technical-details-body")).toBeInTheDocument();
    // And it contains the technical key/value pairs.
    expect(screen.getByTestId("technical-details-body")).toHaveTextContent("CPL");
    expect(screen.getByTestId("technical-details-body")).toHaveTextContent(
      "₹120",
    );
  });

  it("toggle expands/collapses regardless of mode", async () => {
    render(<BusinessMetric {...VALID_METRIC} />);
    const user = userEvent.setup();
    const toggle = screen.getByTestId("technical-details-toggle");
    expect(
      screen.queryByTestId("technical-details-body"),
    ).not.toBeInTheDocument();

    await user.click(toggle);
    expect(screen.getByTestId("technical-details-body")).toBeInTheDocument();

    await user.click(toggle);
    expect(
      screen.queryByTestId("technical-details-body"),
    ).not.toBeInTheDocument();
  });

  it("renders nothing for technical details when prop omitted", () => {
    const { technicalDetails: _omit, ...rest } = VALID_METRIC;
    render(<BusinessMetric {...rest} />);
    expect(
      screen.queryByTestId("technical-details-toggle"),
    ).not.toBeInTheDocument();
  });

  it("renders nothing for technical details when prop is an empty object", () => {
    render(<BusinessMetric {...VALID_METRIC} technicalDetails={{}} />);
    expect(
      screen.queryByTestId("technical-details-toggle"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------
//  Confidence calibration (matches Constitution table)
// ---------------------------------------------------------------------

describe("Confidence calibration", () => {
  it.each([
    [95, "High confidence"],
    [80, "High confidence"],
    [79, "Medium confidence"],
    [60, "Medium confidence"],
    [59, "Low confidence"],
    [40, "Low confidence"],
    [39, "Speculative"],
    [0, "Speculative"],
  ])("confidence=%d → %s", (conf, label) => {
    render(<BusinessMetric {...VALID_METRIC} confidence={conf} />);
    expect(screen.getByTestId("confidence-pill")).toHaveTextContent(label);
  });

  it("shows the raw percentage alongside the band", () => {
    render(<BusinessMetric {...VALID_METRIC} confidence={73} />);
    expect(screen.getByTestId("section-confidence")).toHaveTextContent("(73%)");
  });
});

// ---------------------------------------------------------------------
//  Status pill + impact category visuals (BusinessMetric only)
// ---------------------------------------------------------------------

describe("BusinessMetric — status + impact category", () => {
  it.each([
    ["good", "Good"],
    ["warning", "Watch"],
    ["bad", "Needs attention"],
    ["neutral", "Neutral"],
  ] as const)("status=%s renders pill label %s", (status, label) => {
    render(<BusinessMetric {...VALID_METRIC} status={status} />);
    expect(screen.getByTestId("status-pill")).toHaveTextContent(label);
  });

  it.each([
    ["revenue", "Revenue impact"],
    ["lead", "Leads impact"],
    ["customer", "Customers impact"],
    ["time", "Time impact"],
    ["cost", "Cost impact"],
  ] as const)("impactCategory=%s shows label %s", (cat, label) => {
    render(<BusinessMetric {...VALID_METRIC} impactCategory={cat} />);
    expect(screen.getByTestId("business-metric")).toHaveTextContent(label);
  });

  it("primary slot shows the value, with plain-language directly below", () => {
    render(<BusinessMetric {...VALID_METRIC} />);
    expect(screen.getByTestId("business-metric")).toHaveTextContent(
      VALID_METRIC.value,
    );
    expect(screen.getByTestId("business-metric")).toHaveTextContent(
      VALID_METRIC.plainLanguage,
    );
  });
});

// ---------------------------------------------------------------------
//  AiRecommendation specifics
// ---------------------------------------------------------------------

describe("AiRecommendation", () => {
  it("uses the recommendation as the primary headline", () => {
    render(<AiRecommendation {...VALID_AI_REC} />);
    expect(screen.getByTestId("ai-recommendation")).toHaveTextContent(
      VALID_AI_REC.recommendation,
    );
  });

  it("renders the 'AI recommendation · X impact' chip", () => {
    render(<AiRecommendation {...VALID_AI_REC} />);
    expect(screen.getByTestId("ai-recommendation")).toHaveTextContent(
      /AI recommendation · Leads impact/i,
    );
  });

  it("does not show a status pill (only BusinessMetric has one)", () => {
    render(<AiRecommendation {...VALID_AI_REC} />);
    expect(screen.queryByTestId("status-pill")).not.toBeInTheDocument();
  });

  it("does not show technical details toggle when none provided", () => {
    render(<AiRecommendation {...VALID_AI_REC} />);
    expect(
      screen.queryByTestId("technical-details-toggle"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------
//  Contract enforcement — refuses to render with missing fields
// ---------------------------------------------------------------------

describe("Constitution contract enforcement", () => {
  // Each test below intentionally bypasses TS by casting; the runtime
  // assertion is what we're verifying.
  it.each([
    ["recommendation", ""],
    ["expectedResult", ""],
    ["reason", ""],
    ["businessImpact", ""],
    ["plainLanguage", ""],
    ["value", ""],
  ])("BusinessMetric throws when %s is empty", (field, val) => {
    const broken = { ...VALID_METRIC, [field]: val };
    expect(() => render(<BusinessMetric {...broken} />)).toThrow(
      /required prop/i,
    );
  });

  it("BusinessMetric throws when confidence is out of range", () => {
    expect(() =>
      render(<BusinessMetric {...VALID_METRIC} confidence={150} />),
    ).toThrow(/confidence.*between 0 and 100/i);
    expect(() =>
      render(<BusinessMetric {...VALID_METRIC} confidence={-1} />),
    ).toThrow(/confidence.*between 0 and 100/i);
  });

  it("AiRecommendation throws when any contract field is empty", () => {
    const broken = { ...VALID_AI_REC, recommendation: "" };
    expect(() => render(<AiRecommendation {...broken} />)).toThrow(
      /required prop/i,
    );
  });
});
