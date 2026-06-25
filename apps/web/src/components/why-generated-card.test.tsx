/**
 * Founder Experience Audit (Batch 2 / C10 + C11) tests.
 *
 * The "Why we generated this" disclosure used to dump raw `key=value`
 * chips and an `imp · eng · leads` line straight from the database.
 * These tests lock in the founder-friendly rewrite — the card must
 * now read like a sentence a non-marketer would say out loud, and
 * must NEVER surface the old engineering shorthand.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExperimentProvenance } from "@/lib/api";

const provenanceMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      learning: {
        provenance: (id: string) => provenanceMock(id),
      },
    },
  };
});

import { WhyGeneratedCard } from "./why-generated-card";

const SAMPLE: ExperimentProvenance = {
  experiment: {
    id: "exp-1",
    user_id: "u-1",
    source_asset_type: "content",
    source_asset_id: "asset-1",
    platform: "instagram",
    goal: "Get more leads",
    hypothesis: "Coffee shops respond best to warm, story-led posts.",
    inherited_patterns: ["Warmer tone beat formal tone 3:1 in past posts."],
    variable_choices: {
      content_type: "social_post",
      platform: "instagram",
      tone: "warm and confident",
      trend_grounded: true,
      has_landing_page: true,
    },
    context_snapshot: {},
    status: "live",
    sample_size: 0,
    confidence_score: 0,
    evidence: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  matched_events: [
    {
      id: "ev-1",
      user_id: "u-1",
      variable: "tone",
      finding: "Warm tones outperformed neutral by 18% on Instagram.",
      direction: "positive",
      effect_size: 0.18,
      experiment_ids: ["exp-0"],
      evidence: [],
      sample_size: 12,
      confidence_score: 0.82,
      source: "auto",
      status: "active",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  latest_result: {
    id: "r-1",
    experiment_id: "exp-1",
    impressions: 1240,
    reach: 1100,
    likes: 50,
    comments_count: 5,
    saves: 8,
    shares: 4,
    engagement_rate: 0.054,
    leads: 2,
    ctr: 0,
    views: 0,
    watch_time_seconds: 0,
    captured_at: new Date().toISOString(),
    sample_size: 1240,
    confidence_score: 0.6,
    evidence: [],
  },
};

beforeEach(() => {
  provenanceMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

async function openCard() {
  render(<WhyGeneratedCard sourceAssetId="asset-1" />);
  await waitFor(() => {
    expect(screen.getByText(/why we generated this/i)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByText(/why we generated this/i));
}

describe("WhyGeneratedCard — founder vocabulary (Batch 2)", () => {
  it("uses 'What the AI was going for' instead of 'Hypothesis'", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();
    expect(screen.getByText(/what the ai was going for/i)).toBeInTheDocument();
    expect(screen.queryByText(/^hypothesis$/i)).not.toBeInTheDocument();
  });

  it("renders 'How the AI built this' as sentences (no key=value chips)", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();

    expect(screen.getByText(/how the ai built this/i)).toBeInTheDocument();
    // Sentences a founder would read.
    expect(
      screen.getByText(/wrote a social post for instagram/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/voice: warm and confident/i)).toBeInTheDocument();
    expect(
      screen.getByText(/built on a trend that's heating up right now/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/wired to a lead page so clicks turn into contacts/i),
    ).toBeInTheDocument();

    // The old chip vocabulary must be gone.
    expect(screen.queryByText(/^creative choices$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tone=warm/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/trend_grounded=true/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/content_type=/i)).not.toBeInTheDocument();
  });

  it("renames the patterns section so founders know it's their own past data", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();
    expect(
      screen.getByText(/what we learned from your past posts/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/patterns the ai inherited/i)).not.toBeInTheDocument();
  });

  it("renames the matched-events section to plain English", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();
    expect(
      screen.getByText(/what worked before for similar posts/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/findings about these dimensions/i),
    ).not.toBeInTheDocument();
  });

  it("translates confidence + sample-size to plain words ('High confidence · based on 12 past posts')", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();
    // 0.82 → High tier
    expect(screen.getByText(/high confidence/i)).toBeInTheDocument();
    expect(screen.getByText(/based on 12 past posts/i)).toBeInTheDocument();
    // Old shorthand must be gone.
    expect(screen.queryByText(/n=12/)).not.toBeInTheDocument();
    expect(screen.queryByText(/82%/)).not.toBeInTheDocument();
  });

  it("rewrites the performance footer as a sentence (no imp · eng · leads)", async () => {
    provenanceMock.mockResolvedValueOnce(SAMPLE);
    await openCard();
    expect(screen.getByText(/how this is doing so far/i)).toBeInTheDocument();
    // 1,240 impressions, 5.4% engagement, 2 leads
    expect(
      screen.getByText(/1,240 people saw it · 5\.4% engaged · 2 leads\./i),
    ).toBeInTheDocument();
    // Engineering shorthand must be gone.
    expect(screen.queryByText(/\bimp \d/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/latest performance snapshot/i)).not.toBeInTheDocument();
  });

  it("uses 'no leads yet' rather than '0 leads' when the asset hasn't converted", async () => {
    provenanceMock.mockResolvedValueOnce({
      ...SAMPLE,
      latest_result: {
        ...SAMPLE.latest_result!,
        impressions: 1,
        engagement_rate: 0,
        leads: 0,
      },
    });
    await openCard();
    expect(
      screen.getByText(/1 person saw it · 0\.0% engaged · no leads yet\./i),
    ).toBeInTheDocument();
  });

  it("renders nothing when the provenance request fails (silent degrade)", async () => {
    // The card never blocks the surrounding result-card — error AND absent
    // both collapse to null so a legacy generation or a transient failure
    // never confuses a founder with a broken collapsible.
    provenanceMock.mockRejectedValueOnce(new Error("boom"));
    const { container } = render(<WhyGeneratedCard sourceAssetId="legacy" />);
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });
});
