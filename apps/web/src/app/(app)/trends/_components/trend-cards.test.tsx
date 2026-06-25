/**
 * Founder Experience Audit (Batch 3 / C5 + C6) tests.
 *
 * The Trends page previously rendered each topic as a research card
 * with a raw integer "relevance score" and a bullet list of suggested
 * angles. A non-marketer reading it had no idea what to do next.
 *
 * After Batch 3, every trending topic must answer the same four
 * advisory questions every other AI surface answers — and confidence
 * is shown as a plain-language tier, not a naked integer. These
 * tests lock that contract in and also confirm the page degrades
 * gracefully when the legacy LLM shape comes back from old reports.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TrendAnalysis, TrendingTopic } from "@/lib/api";

import { TrendCards } from "./trend-cards";

function makeAnalysis(topics: TrendingTopic[]): TrendAnalysis {
  return {
    summary: "Specialty coffee interest is climbing across your platforms.",
    trending_topics: topics,
    content_ideas: [
      {
        platform: "Instagram",
        format: "reel",
        hook: "The 30-second bean test we use every morning.",
        description: "Show how you taste-test a new bean shipment.",
      },
    ],
    hashtag_clusters: [
      {
        theme: "Specialty coffee",
        hashtags: ["coffee", "#specialtycoffee", "barista"],
      },
    ],
    marketing_angles: ["Lead with the bean origin story."],
  };
}

const NEW_TOPIC: TrendingTopic = {
  topic: "Specialty coffee guides",
  why_it_matters: "Your audience is asking espresso questions on Reddit.",
  suggested_angles: ["Bean-by-bean walkthrough", "Pour-over basics"],
  relevance_score: 78,
  recommended_action:
    "Post a 60-second Instagram reel walking through your espresso bean selection.",
  expected_result:
    "Likely 80-150 extra people see it; 1-3 walk in this week.",
  confidence: 78,
  reason:
    "'Espresso bean comparison' is rising +45% on Google Trends and your audience is on Instagram.",
};

const LEGACY_TOPIC: TrendingTopic = {
  topic: "Cold brew season",
  why_it_matters: "Local search for 'cold brew' jumped 18% last week.",
  suggested_angles: ["Cold brew tasting note", "Behind-the-bar reel"],
  relevance_score: 65,
  recommended_action: null,
  expected_result: null,
  confidence: null,
  reason: null,
};

describe("TrendCards — founder advisory contract (Batch 3)", () => {
  it("uses founder-language section headers (no 'Trend landscape', 'Trending topics', 'Hashtag clusters')", () => {
    render(<TrendCards analysis={makeAnalysis([NEW_TOPIC])} />);

    expect(screen.getByText(/what's heating up right now/i)).toBeInTheDocument();
    expect(screen.getByText(/trends to act on this week/i)).toBeInTheDocument();
    expect(screen.getByText(/things you could post/i)).toBeInTheDocument();
    expect(screen.getByText(/angles to lean into this week/i)).toBeInTheDocument();
    expect(screen.getByText(/hashtags worth using/i)).toBeInTheDocument();

    // The strategist vocabulary must be gone.
    expect(screen.queryByText(/^trend landscape$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^trending topics$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^hashtag clusters$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^marketing angles$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^content ideas$/i)).not.toBeInTheDocument();
  });

  it("renders the 4-question advisor contract for each new topic", () => {
    render(<TrendCards analysis={makeAnalysis([NEW_TOPIC])} />);

    // What is happening
    expect(
      screen.getByText(/your audience is asking espresso questions/i),
    ).toBeInTheDocument();
    // What you should do
    expect(
      screen.getByText(/post a 60-second instagram reel/i),
    ).toBeInTheDocument();
    // What you can expect
    expect(
      screen.getByText(/80-150 extra people see it/i),
    ).toBeInTheDocument();
    // Why
    expect(
      screen.getByText(/'espresso bean comparison' is rising \+45%/i),
    ).toBeInTheDocument();

    // The four Constitution labels exist.
    expect(screen.getByText(/^what is happening$/i)).toBeInTheDocument();
    expect(screen.getByText(/^what you should do$/i)).toBeInTheDocument();
    expect(screen.getByText(/^what you can expect$/i)).toBeInTheDocument();
    expect(screen.getByText(/^why we believe it$/i)).toBeInTheDocument();
  });

  it("replaces the numeric relevance_score with a plain-language tier pill", () => {
    render(<TrendCards analysis={makeAnalysis([NEW_TOPIC])} />);
    // 78 → "Strong fit"
    expect(screen.getByText(/strong fit/i)).toBeInTheDocument();
    // The naked integer must not appear as a standalone badge anywhere.
    expect(screen.queryByText(/^78$/)).not.toBeInTheDocument();
  });

  it("maps confidence ranges to the right tier", () => {
    render(
      <TrendCards
        analysis={makeAnalysis([
          { ...NEW_TOPIC, topic: "A", confidence: 90 },
          { ...NEW_TOPIC, topic: "B", confidence: 60 },
          { ...NEW_TOPIC, topic: "C", confidence: 35 },
        ])}
      />,
    );

    expect(screen.getByText(/strong fit/i)).toBeInTheDocument();
    expect(screen.getByText(/worth a shot/i)).toBeInTheDocument();
    expect(screen.getByText(/^speculative$/i)).toBeInTheDocument();
  });

  it("falls back to the legacy 'angles you could use' view when advisory fields are missing", () => {
    // Old reports already in Postgres won't have the new fields. The
    // page must still render something concrete instead of going blank.
    render(<TrendCards analysis={makeAnalysis([LEGACY_TOPIC])} />);

    expect(screen.getByText(/cold brew season/i)).toBeInTheDocument();
    expect(screen.getByText(/^angles you could use$/i)).toBeInTheDocument();
    expect(screen.getByText(/cold brew tasting note/i)).toBeInTheDocument();
    expect(screen.getByText(/behind-the-bar reel/i)).toBeInTheDocument();

    // No advisory labels — the legacy fallback hides them.
    expect(screen.queryByText(/^what you should do$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^what you can expect$/i)).not.toBeInTheDocument();
  });

  it("hides the confidence tier pill when confidence is missing (legacy report)", () => {
    render(<TrendCards analysis={makeAnalysis([LEGACY_TOPIC])} />);
    expect(screen.queryByText(/strong fit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/worth a shot/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^speculative$/i)).not.toBeInTheDocument();
  });

  it("renders both shapes side-by-side in a mixed report", () => {
    render(<TrendCards analysis={makeAnalysis([NEW_TOPIC, LEGACY_TOPIC])} />);

    // New topic uses the contract.
    expect(screen.getByText(/post a 60-second instagram reel/i)).toBeInTheDocument();
    // Legacy topic uses the angles fallback.
    expect(screen.getByText(/^angles you could use$/i)).toBeInTheDocument();
    // Both topics show.
    expect(screen.getByText(/specialty coffee guides/i)).toBeInTheDocument();
    expect(screen.getByText(/cold brew season/i)).toBeInTheDocument();
  });
});

// Phase 8 — One-Click Execution. Advisory trends ship a Quick
// Generate button so a founder reading /trends can go from "I should
// ride this" to "here's the post" without a single form. Legacy
// trends (no advisory contract) stay button-less — generating without
// a "why" surface would violate the Constitution.
describe("TrendCards — Phase 8 Quick Generate", () => {
  it("renders a Quick Generate button for advisory trends", () => {
    render(<TrendCards analysis={makeAnalysis([NEW_TOPIC])} />);
    expect(screen.getByTestId("trend-quick-generate")).toBeInTheDocument();
  });

  it("HIDES Quick Generate on legacy trends without the advisory contract", () => {
    render(<TrendCards analysis={makeAnalysis([LEGACY_TOPIC])} />);
    expect(screen.queryByTestId("trend-quick-generate")).toBeNull();
  });

  it("renders one Quick Generate per advisory trend in a mixed list", () => {
    render(
      <TrendCards
        analysis={makeAnalysis([
          NEW_TOPIC,
          { ...NEW_TOPIC, topic: "Another advisory" },
          LEGACY_TOPIC,
        ])}
      />,
    );
    expect(screen.getAllByTestId("trend-quick-generate")).toHaveLength(2);
  });
});
