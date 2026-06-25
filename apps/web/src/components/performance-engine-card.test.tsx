/**
 * Tests for the Performance Engine dashboard card — Phase 9.1.
 *
 * Pins the three render states (empty / coming-soon / ready) and the
 * upload happy path. The translator + Constitution contract are
 * tested separately in `performance-translator.test.ts`.
 */

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  CsvIngestSummary,
  PerformanceDiagnosticCard,
  PerformanceOverview,
} from "@/lib/api";

const overviewMock = vi.fn();
const uploadMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      performance: {
        overview: (...a: unknown[]) => overviewMock(...a),
        upload: (...a: unknown[]) => uploadMock(...a),
      },
    },
  };
});

import {
  __resetViewModeForTests,
  setViewMode,
} from "@/lib/view-mode";

import { PerformanceEngineCard } from "./performance-engine-card";

// ---------------------------------------------------------------------
//  Fixtures
// ---------------------------------------------------------------------

function diagnostic(
  over: Partial<PerformanceDiagnosticCard> = {},
): PerformanceDiagnosticCard {
  return {
    id: "d-1",
    kind: "winner",
    impact_category: "lead",
    what_happened: "Your best-performing creative is Family dinner reel.",
    why: "It converted at INR 50 per lead — cheaper than the runner-up.",
    recommendation: "Make 2-3 more variants in the same direction.",
    expected_result: "Expect 30-50% more leads next month.",
    reason: "Based on 12,400 impressions and 20 conversions.",
    confidence: 80,
    evidence: {
      creative_ref: "Family dinner reel",
      currency: "INR",
      cpl: 50,
      spend: 1000,
      conversions: 20,
      impressions: 12400,
    },
    status: "open",
    created_at: "2026-06-01T10:00:00Z",
    ...over,
  };
}

function overview(over: Partial<PerformanceOverview> = {}): PerformanceOverview {
  return {
    has_data: false,
    rows_ingested: 0,
    creatives_tracked: 0,
    last_upload_at: null,
    diagnostics: [],
    ...over,
  };
}

function summary(over: Partial<CsvIngestSummary> = {}): CsvIngestSummary {
  return {
    upload_id: "u-1",
    rows_accepted: 28,
    rows_rejected: 0,
    creatives_matched: 3,
    creatives_unmatched: 0,
    date_range: ["2026-05-01", "2026-05-30"],
    currency: "INR",
    errors: [],
    ...over,
  };
}

beforeEach(() => {
  overviewMock.mockReset();
  uploadMock.mockReset();
  __resetViewModeForTests();
});
afterEach(() => {
  vi.clearAllMocks();
  __resetViewModeForTests();
});

// ---------------------------------------------------------------------
//  State: empty
// ---------------------------------------------------------------------

describe("PerformanceEngineCard — empty state", () => {
  it("renders the upload CTA when the brand has uploaded nothing", async () => {
    overviewMock.mockResolvedValue(overview());
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-empty")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-empty")).toHaveTextContent(
      /No performance data yet/i,
    );
  });
});

// ---------------------------------------------------------------------
//  State: coming-soon (data ingested, no diagnostic survives gate)
// ---------------------------------------------------------------------

describe("PerformanceEngineCard — coming-soon state", () => {
  it("explains the sample threshold honestly instead of fabricating", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 12,
        creatives_tracked: 3,
        diagnostics: [],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(
        screen.getByTestId("performance-coming-soon"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-coming-soon")).toHaveTextContent(
      /minimum sample size/i,
    );
    // Crucially: we never claim a winner here.
    expect(screen.queryByTestId(/performance-card-/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------
//  State: ready
// ---------------------------------------------------------------------

describe("PerformanceEngineCard — ready state", () => {
  it("renders one AiRecommendation per diagnostic", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 4,
        diagnostics: [diagnostic({ id: "a" }), diagnostic({ id: "b", kind: "budget_reallocation" })],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-cards")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-card-winner")).toBeInTheDocument();
    expect(
      screen.getByTestId("performance-card-budget_reallocation"),
    ).toBeInTheDocument();
  });

  it("orders cards by confidence desc", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 4,
        diagnostics: [
          diagnostic({ id: "low", confidence: 50, kind: "budget_reallocation" }),
          diagnostic({ id: "high", confidence: 88 }),
        ],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-cards")).toBeInTheDocument(),
    );
    const cards = screen.getByTestId("performance-cards").children;
    // Winner (88) before budget_reallocation (50).
    expect(cards[0]).toHaveAttribute(
      "data-testid",
      "performance-card-winner",
    );
  });
});

// ---------------------------------------------------------------------
//  Upload path
// ---------------------------------------------------------------------

describe("PerformanceEngineCard — upload", () => {
  it("uploads the selected file and refreshes the overview", async () => {
    overviewMock
      .mockResolvedValueOnce(overview()) // initial render
      .mockResolvedValueOnce(
        overview({
          has_data: true,
          rows_ingested: 28,
          creatives_tracked: 3,
          diagnostics: [diagnostic()],
        }),
      );
    uploadMock.mockResolvedValue(summary());

    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-empty")).toBeInTheDocument(),
    );

    const file = new File(["date,creative\n2026-05-29,A"], "ads.csv", {
      type: "text/csv",
    });
    const input = screen.getByTestId(
      "performance-csv-input",
    ) as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });

    await waitFor(() => expect(uploadMock).toHaveBeenCalledTimes(1));
    expect(uploadMock.mock.calls[0][0]).toBe(file);

    await waitFor(() =>
      expect(
        screen.getByTestId("performance-upload-summary"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-upload-summary")).toHaveTextContent(
      /28 rows/i,
    );

    // Refresh kicked in → ready state shown.
    await waitFor(() =>
      expect(screen.getByTestId("performance-cards")).toBeInTheDocument(),
    );
  });

  it("surfaces parse errors from the upload summary", async () => {
    overviewMock.mockResolvedValue(overview());
    uploadMock.mockResolvedValue(
      summary({
        rows_accepted: 25,
        rows_rejected: 3,
        errors: [
          { row_number: 3, raw: {}, error: "date is empty" },
          { row_number: 7, raw: {}, error: "clicks (50) > impressions (10)" },
          { row_number: 9, raw: {}, error: "currency missing" },
        ],
      }),
    );

    render(<PerformanceEngineCard />);
    await waitFor(() => expect(overviewMock).toHaveBeenCalled());

    const file = new File(["x"], "ads.csv", { type: "text/csv" });
    await act(async () => {
      fireEvent.change(screen.getByTestId("performance-csv-input"), {
        target: { files: [file] },
      });
    });
    await waitFor(() =>
      expect(
        screen.getByTestId("performance-upload-summary"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-upload-summary")).toHaveTextContent(
      /3 rows were skipped/i,
    );
    expect(screen.getByTestId("performance-upload-summary")).toHaveTextContent(
      /date is empty/i,
    );
  });

  it("shows an error banner if the upload fails", async () => {
    overviewMock.mockResolvedValue(overview());
    uploadMock.mockRejectedValue(new Error("Network down"));

    render(<PerformanceEngineCard />);
    await waitFor(() => expect(overviewMock).toHaveBeenCalled());

    const file = new File(["x"], "ads.csv", { type: "text/csv" });
    await act(async () => {
      fireEvent.change(screen.getByTestId("performance-csv-input"), {
        target: { files: [file] },
      });
    });
    await waitFor(() =>
      expect(screen.getByTestId("performance-error")).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------
//  Phase 9.1.5 — Simple/Pro split, sectioning, top-3 truncation
// ---------------------------------------------------------------------

// Mimics the real backend `recommender._creative_dna()` output shape
// so this test pins the actual founder-visible card, not a stub.
function dnaDiag(over: Partial<PerformanceDiagnosticCard> = {}): PerformanceDiagnosticCard {
  return diagnostic({
    id: "dna-1",
    kind: "creative_dna",
    impact_category: "revenue",
    what_happened:
      "This combination produced the strongest business result in this upload.\n\n" +
      "Winning pattern:\n" +
      "  • Audience: parents\n" +
      "  • Feeling: warmth\n" +
      "  • Angle: family experience\n" +
      "  • Offer: a free consultation\n" +
      "  • Buyer stage: people who are ready to buy or book\n\n" +
      "It produced 38 leads at INR 50 each across 2 ads.",
    why: "No other audience × feeling × angle × offer × buyer-stage matched it.",
    recommendation: "Make 2-3 more ads using this exact recipe.",
    expected_result: "Variants in this style usually add 30-50% more leads.",
    reason: "Based on every 5-tag combination in the upload.",
    confidence: 80,
    evidence: {
      audience: "parents",
      concept_family: "family_experience",
      emotion: "warmth",
      offer_type: "consultation",
      funnel_stage: "conversion",
      creatives_count: 2,
      currency: "INR",
      cpl: 50,
      conversions: 38,
    },
    ...over,
  });
}

describe("PerformanceEngineCard — 9.1.5 Simple Mode (default)", () => {
  it("truncates to top-3 cards by confidence", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 5,
        diagnostics: [
          diagnostic({ id: "1", confidence: 90 }),
          diagnostic({ id: "2", confidence: 85, kind: "budget_reallocation" }),
          diagnostic({ id: "3", confidence: 80, kind: "audience_winner" }),
          diagnostic({ id: "4", confidence: 75, kind: "concept_winner" }),
          diagnostic({ id: "5", confidence: 70, kind: "offer_winner" }),
        ],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-cards")).toBeInTheDocument(),
    );
    // Only 3 cards rendered.
    const cards = screen.getByTestId("performance-cards").querySelectorAll(
      "[data-testid^=performance-card-]",
    );
    expect(cards).toHaveLength(3);
    // "more available" hint visible.
    expect(screen.getByTestId("performance-more-hint")).toHaveTextContent(
      /2 more insights/i,
    );
  });

  it("does not render section headers in Simple Mode", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 3,
        diagnostics: [
          diagnostic({ id: "1" }),
          dnaDiag(),
        ],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-cards")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("performance-section-dna")).not.toBeInTheDocument();
    expect(screen.queryByTestId("performance-section-baseline")).not.toBeInTheDocument();
  });
});

describe("PerformanceEngineCard — 9.1.5 Pro Mode", () => {
  it("renders all cards grouped by section, DNA first", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 5,
        diagnostics: [
          diagnostic({ id: "w", kind: "winner", confidence: 90 }),
          diagnostic({ id: "a", kind: "audience_winner", confidence: 85 }),
          diagnostic({ id: "c", kind: "concept_winner", confidence: 80 }),
          diagnostic({ id: "o", kind: "offer_winner", confidence: 75 }),
          diagnostic({ id: "s", kind: "scale_candidate", confidence: 70 }),
          dnaDiag({ id: "d", confidence: 80 }),
        ],
      }),
    );
    setViewMode("professional");
    render(<PerformanceEngineCard />);
    // useViewMode reads the stored mode in a post-mount effect, so we
    // wait for the section header (Pro-only) to appear rather than
    // asserting synchronously.
    await waitFor(() =>
      expect(screen.getByTestId("performance-section-dna")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("performance-section-baseline")).toBeInTheDocument();
    expect(screen.getByTestId("performance-section-audience")).toBeInTheDocument();
    expect(screen.getByTestId("performance-section-creative")).toBeInTheDocument();
    expect(screen.getByTestId("performance-section-offer")).toBeInTheDocument();
    expect(screen.getByTestId("performance-section-scaling")).toBeInTheDocument();

    // DNA section comes first in the DOM (apex card always first).
    const root = screen.getByTestId("performance-cards");
    const firstSection = root.querySelector("section");
    expect(firstSection?.getAttribute("data-testid")).toBe(
      "performance-section-dna",
    );
  });

  it("does not show the 'more available' hint in Pro Mode", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 5,
        diagnostics: [
          diagnostic({ id: "1" }),
          diagnostic({ id: "2", kind: "audience_winner" }),
          diagnostic({ id: "3", kind: "concept_winner" }),
          diagnostic({ id: "4", kind: "offer_winner" }),
        ],
      }),
    );
    setViewMode("professional");
    render(<PerformanceEngineCard />);
    // Wait for Pro-only section header so we know useViewMode has hydrated.
    await waitFor(() =>
      expect(screen.getByTestId("performance-section-baseline")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("performance-more-hint")).not.toBeInTheDocument();
  });
});

describe("PerformanceEngineCard — 9.1.5 creative_dna apex card", () => {
  it("renders the DNA card with the 5-tag pattern visible", async () => {
    overviewMock.mockResolvedValue(
      overview({
        has_data: true,
        rows_ingested: 30,
        creatives_tracked: 2,
        diagnostics: [dnaDiag()],
      }),
    );
    render(<PerformanceEngineCard />);
    await waitFor(() =>
      expect(screen.getByTestId("performance-card-creative_dna")).toBeInTheDocument(),
    );
    const card = screen.getByTestId("performance-card-creative_dna");
    // The pattern lines are inside the "what is happening" block.
    expect(card).toHaveTextContent(/Winning pattern/i);
    expect(card).toHaveTextContent(/Audience/i);
    expect(card).toHaveTextContent(/Feeling/i);
    expect(card).toHaveTextContent(/Angle/i);
    expect(card).toHaveTextContent(/Offer/i);
    expect(card).toHaveTextContent(/Buyer stage/i);
  });
});
