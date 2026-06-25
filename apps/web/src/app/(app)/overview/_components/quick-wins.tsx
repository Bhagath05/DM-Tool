"use client";

/**
 * Phase 10.0 — Quick Wins panel.
 *
 * Sits at the very top of /overview. Pulls the top-3 highest-confidence
 * cards from the Performance overview, rendered as a punchy
 * action-only list with derived expected-leads + revenue chips.
 *
 * Constitution discipline:
 *   - Only HIGH-priority (≥80% confidence) make this list. The whole
 *     point of "Quick Wins" is that you can act without further
 *     thought; medium-confidence rows belong in the AI Coach panel
 *     where they get full context.
 *   - When fewer than 3 quick wins exist, we show what we have. We
 *     never pad with weaker recommendations.
 *   - Section hides entirely when no quick wins are available.
 */

import { ArrowRight, CheckCircle2, Sparkles } from "lucide-react";

import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { derive } from "@/lib/performance-derived";
import type { PerformanceOpportunity } from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

export interface QuickWinsProps {
  cards: PerformanceOpportunity[];
  className?: string;
}

export function QuickWins({ cards, className }: QuickWinsProps) {
  const wins = cards
    .filter((c) => c.confidence >= 80)
    .slice(0, 3);
  if (wins.length === 0) return null;

  return (
    <section
      data-testid="quick-wins"
      className={cn("flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            Top of mind
          </span>
        }
        heading="Quick Wins"
        description="The highest-confidence moves you can make today."
      />

      <div className="flex flex-col gap-2.5" data-testid="quick-wins-list">
        {wins.map((w) => (
          <QuickWinRow key={w.id} card={w} />
        ))}
      </div>
    </section>
  );
}

function QuickWinRow({ card }: { card: PerformanceOpportunity }) {
  const { expectedLeads, revenueImpact } = derive(card);
  // Trim the recommendation to a one-sentence headline so the row
  // reads at-a-glance. The full text is available in the dedicated
  // Performance section below.
  const headline = trimToSentence(card.recommendation, 110);
  return (
    <div
      data-testid={`quick-win-${card.kind}`}
      className="group flex items-center gap-4 rounded-xl border border-border/70 bg-card px-4 py-3.5 shadow-xs transition-all duration-150 hover:border-ai-border hover:shadow-sm"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-good-soft text-good">
        <CheckCircle2 className="h-4 w-4" />
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
          {headline}
        </p>
        {expectedLeads && (
          <StatusPill tone="neutral" size="sm" data-testid="quick-win-leads">
            Expected: {expectedLeads}
          </StatusPill>
        )}
        {revenueImpact && (
          <StatusPill tone="good" size="sm" data-testid="quick-win-revenue">
            {revenueImpact}
          </StatusPill>
        )}
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-ai" />
    </div>
  );
}

function trimToSentence(s: string, max: number): string {
  if (s.length <= max) return s;
  // Cut on the first sentence boundary within the limit.
  const cut = s.slice(0, max);
  const period = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "));
  if (period > 40) return s.slice(0, period + 1);
  return cut.replace(/[\s,]+\S*$/, "") + "…";
}
