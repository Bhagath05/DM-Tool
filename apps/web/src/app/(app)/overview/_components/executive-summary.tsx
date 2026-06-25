"use client";

/**
 * Phase 10.0 — Executive Summary band.
 *
 * Four tiles, above the fold:
 *
 *   ┌── Status ──┐  ┌── Top Opportunity ──┐  ┌── Biggest Waste ──┐  ┌── Expected Impact ──┐
 *
 * Each tile is derived from the existing Performance overview payload —
 * no new endpoints. The Executive Summary is purely a presentation
 * layer; the data discipline is the same min-sample / confidence-band
 * discipline the engine already enforces.
 *
 * If there's not enough data for a tile, that tile renders an empty
 * variant ("Tracking — needs more data") rather than fabricating.
 */

import {
  Activity,
  type LucideIcon,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useMemo } from "react";

import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { derive } from "@/lib/performance-derived";
import type {
  PerformanceCards,
  PerformanceOpportunity,
} from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

export interface ExecutiveSummaryProps {
  cards: PerformanceCards;
  className?: string;
}

export function ExecutiveSummary({ cards, className }: ExecutiveSummaryProps) {
  const { status, topOpportunity, biggestWaste, expectedImpact } = useMemo(
    () => computeSummary(cards),
    [cards],
  );

  return (
    <section
      data-testid="executive-summary"
      className={cn("flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow="At a glance"
        heading="Today's status"
        description="Four lines that tell you everything you need to know."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryTile
          icon={Activity}
          eyebrow="Status"
          headline={status.label}
          subtext={status.subtext}
          accent={status.tone}
          testId="exec-status"
        />
        <SummaryTile
          icon={TrendingUp}
          eyebrow="Top opportunity"
          headline={topOpportunity.label}
          subtext={topOpportunity.subtext}
          accent={topOpportunity.label === "Waiting on data" ? "muted" : "good"}
          testId="exec-top-opportunity"
        />
        <SummaryTile
          icon={TrendingDown}
          eyebrow="Biggest waste"
          headline={biggestWaste.label}
          subtext={biggestWaste.subtext}
          accent={biggestWaste.label === "None detected" ? "good" : "bad"}
          testId="exec-biggest-waste"
        />
        <SummaryTile
          icon={Sparkles}
          eyebrow="Expected impact"
          headline={expectedImpact.label}
          subtext={expectedImpact.subtext}
          accent="ai"
          testId="exec-expected-impact"
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------
//  Tile primitive
// ---------------------------------------------------------------------

function SummaryTile({
  icon: Icon,
  eyebrow,
  headline,
  subtext,
  accent,
  testId,
}: {
  icon: LucideIcon;
  eyebrow: string;
  headline: string;
  subtext: string;
  accent: PillTone;
  testId: string;
}) {
  return (
    <div
      data-testid={testId}
      className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card p-5 shadow-sm transition-shadow duration-150 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          {eyebrow}
        </span>
        <span
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-lg",
            accent === "good" && "bg-good-soft text-good",
            accent === "watch" && "bg-watch-soft text-watch",
            accent === "bad" && "bg-bad-soft text-bad",
            accent === "ai" && "bg-ai-soft text-ai",
            (accent === "neutral" || accent === "muted") &&
              "bg-muted text-muted-foreground",
          )}
          aria-hidden
        >
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <div className="text-lg font-semibold leading-tight tracking-tight">
          {headline}
        </div>
        <p className="text-sm leading-snug text-muted-foreground">
          {subtext}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Derivation — pure, no fabrication
// ---------------------------------------------------------------------

interface SummaryRow {
  label: string;
  subtext: string;
  tone?: PillTone;
}

interface ExecutiveSummaryComputed {
  status: SummaryRow & { tone: PillTone };
  topOpportunity: SummaryRow;
  biggestWaste: SummaryRow;
  expectedImpact: SummaryRow;
}

function computeSummary(cards: PerformanceCards): ExecutiveSummaryComputed {
  const list = cards.cards;
  if (!cards.hasUsableCards) {
    return {
      status: {
        label: "Tracking",
        subtext: "We need a bit more data before we can call this.",
        tone: "muted",
      },
      topOpportunity: {
        label: "Waiting on data",
        subtext: "Upload an ad export to find your top opportunity.",
      },
      biggestWaste: {
        label: "Waiting on data",
        subtext: "Once we see your spend, we'll flag any waste.",
      },
      expectedImpact: {
        label: "—",
        subtext: "Will appear once recommendations are ready.",
      },
    };
  }

  // Status — bad waste card present → Needs attention.
  // Otherwise winner present at HIGH confidence → Growing.
  // Otherwise stable.
  const hasWaste = list.some(
    (c) => c.kind === "budget_waste" || c.kind === "audience_loser",
  );
  const hasHighWinner = list.some(
    (c) =>
      (c.kind === "winner" ||
        c.kind === "audience_winner" ||
        c.kind === "concept_winner" ||
        c.kind === "creative_dna") &&
      c.confidence >= 80,
  );

  let status: SummaryRow & { tone: PillTone };
  if (hasHighWinner && !hasWaste) {
    status = {
      label: "Growing",
      subtext: "Your top creatives are converting well. Lean in.",
      tone: "good",
    };
  } else if (hasWaste) {
    status = {
      label: "Needs attention",
      subtext: "There's spend going to underperforming creatives.",
      tone: "watch",
    };
  } else {
    status = {
      label: "Stable",
      subtext: "Nothing urgent — keep going and we'll surface signals.",
      tone: "neutral",
    };
  }

  // Top opportunity — highest-confidence winner-shaped card.
  const winner = list.find(
    (c) =>
      c.kind === "creative_dna" ||
      c.kind === "winner" ||
      c.kind === "audience_winner" ||
      c.kind === "concept_winner" ||
      c.kind === "offer_winner" ||
      c.kind === "scale_candidate",
  );
  const topOpportunity: SummaryRow = winner
    ? {
        label: titleForCard(winner),
        subtext: trimSentence(winner.recommendation, 120),
      }
    : {
        label: "Waiting on data",
        subtext: "Need more conversions to call a clear winner.",
      };

  // Biggest waste — first budget_waste / audience_loser, by confidence.
  const waste = list.find(
    (c) => c.kind === "budget_waste" || c.kind === "audience_loser",
  );
  const biggestWaste: SummaryRow = waste
    ? {
        label: titleForCard(waste),
        subtext: trimSentence(waste.recommendation, 120),
      }
    : {
        label: "None detected",
        subtext: "We didn't find a creative bleeding budget right now.",
      };

  // Expected impact — sum the derived expected-lead counts across the
  // top 3 cards. Plus money if value/lead is computable.
  let totalLeads = 0;
  let totalRevenue = 0;
  let currency: string | null = null;
  let revenueKnown = false;
  for (const c of list.slice(0, 3)) {
    const d = derive(c);
    if (d.expectedLeads && d.expectedLeads.startsWith("+")) {
      const n = parseInt(d.expectedLeads.replace(/[^\d]/g, ""), 10);
      if (Number.isFinite(n)) totalLeads += n;
    }
    if (d.revenueImpact && d.revenueImpact.includes("potential")) {
      const m = d.revenueImpact.match(/^([A-Z]{3})\s*([\d,]+)/);
      if (m) {
        currency ??= m[1];
        const v = parseInt(m[2].replace(/,/g, ""), 10);
        if (Number.isFinite(v)) {
          totalRevenue += v;
          revenueKnown = true;
        }
      }
    }
  }

  let expectedImpact: SummaryRow;
  if (totalLeads > 0 && revenueKnown && currency) {
    expectedImpact = {
      label: `+${totalLeads} leads`,
      subtext: `Up to ${currency} ${totalRevenue.toLocaleString()} in potential revenue if you act on the top recommendations.`,
    };
  } else if (totalLeads > 0) {
    expectedImpact = {
      label: `+${totalLeads} leads`,
      subtext: "Estimated lift if you act on the top recommendations.",
    };
  } else {
    expectedImpact = {
      label: "Open the cards below",
      subtext:
        "We have qualitative recommendations; volume estimates need more data.",
    };
  }

  return { status, topOpportunity, biggestWaste, expectedImpact };
}

function titleForCard(c: PerformanceOpportunity): string {
  // Reuse the recommendation's leading phrase as a tight label.
  const e = c.evidence ?? {};
  switch (c.kind) {
    case "creative_dna":
      return "Winning recipe identified";
    case "winner":
      return shortRef(typeof e["creative_ref"] === "string" ? e["creative_ref"] : "Top ad");
    case "audience_winner":
      return `“${humanise(e["audience"])}” audience`;
    case "audience_loser":
      return `“${humanise(e["audience"])}” audience`;
    case "concept_winner":
      return `${humanise(e["concept_family"]) ?? "Concept"} angle`;
    case "emotion_winner":
      return `${humanise(e["emotion"]) ?? "Emotion"} tone`;
    case "funnel_winner":
      return `${humanise(e["funnel_stage"]) ?? "Buyer stage"}`;
    case "offer_winner":
      return `${humanise(e["offer_type"]) ?? "Offer"} converts best`;
    case "scale_candidate":
      return shortRef(typeof e["creative_ref"] === "string" ? e["creative_ref"] : "Top ad");
    case "budget_waste":
      return shortRef(typeof e["creative_ref"] === "string" ? e["creative_ref"] : "Underperformer");
    default:
      return "Opportunity";
  }
}

function humanise(v: unknown): string | null {
  if (typeof v !== "string" || !v.trim()) return null;
  return v.replace(/_/g, " ");
}

function shortRef(s: string): string {
  if (s.length <= 32) return s;
  return s.slice(0, 31).trimEnd() + "…";
}

function trimSentence(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max).replace(/[\s,]+\S*$/, "") + "…";
}
