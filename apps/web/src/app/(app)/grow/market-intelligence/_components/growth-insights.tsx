"use client";

/**
 * Phase 10.3c — AI Growth Insights row.
 *
 * 3 mini-cards composed from data the page already loads. Each card
 * carries a one-line insight + a quick CTA. The page passes
 * pre-computed insights so this component stays stateless + cheap.
 *
 * Composition rules (Founder Rule: "What should I do next?"):
 *   - Each insight title is a short concrete claim (not "data dropped")
 *   - Each card has a CTA target — never just informational
 *   - Tones: `good` for upside, `watch` for risk, `neutral` for context
 */

import { ArrowUpRight, TrendingUp, AlertCircle, Sparkles } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type InsightTone = "good" | "watch" | "neutral";

export interface GrowthInsight {
  id: string;
  tone: InsightTone;
  title: string;
  detail: string | null;
  ctaLabel: string;
  ctaHref: string;
}

export interface GrowthInsightsProps {
  insights: GrowthInsight[] | null; // null = loading; [] = honest empty
  className?: string;
}

export function GrowthInsights({ insights, className }: GrowthInsightsProps) {
  return (
    <section
      data-testid="growth-insights"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            AI Growth Insights
          </span>
        }
        heading="What just shifted"
        description="The three signals worth your attention right now."
      />

      {insights === null && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-2xl" />
          ))}
        </div>
      )}

      {insights !== null && insights.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title="No fresh insights yet"
          description="Once your data + connected accounts produce a signal, you'll see it here."
          data-testid="growth-insights-empty"
        />
      )}

      {insights !== null && insights.length > 0 && (
        <div
          className="grid grid-cols-1 gap-3 sm:grid-cols-3"
          data-testid="growth-insights-list"
        >
          {insights.slice(0, 3).map((insight) => (
            <InsightCard key={insight.id} insight={insight} />
          ))}
        </div>
      )}
    </section>
  );
}

function InsightCard({ insight }: { insight: GrowthInsight }) {
  const Icon =
    insight.tone === "good"
      ? TrendingUp
      : insight.tone === "watch"
        ? AlertCircle
        : Sparkles;
  return (
    <Link
      href={insight.ctaHref as never}
      data-testid={`growth-insight-${insight.id}`}
      className={cn(
        "group flex flex-col gap-2 rounded-2xl border border-border bg-card p-4 transition-all duration-200",
        "hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm",
      )}
    >
      <span
        className={cn(
          "inline-flex h-7 w-7 items-center justify-center rounded-full",
          insight.tone === "good" && "bg-good/15 text-good-foreground",
          insight.tone === "watch" && "bg-watch/15 text-watch-foreground",
          insight.tone === "neutral" && "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <p className="text-sm font-medium text-foreground">{insight.title}</p>
      {insight.detail && (
        <p className="text-xs text-muted-foreground">{insight.detail}</p>
      )}
      <span className="mt-auto inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors group-hover:text-foreground">
        {insight.ctaLabel}
        <ArrowUpRight className="h-3 w-3" />
      </span>
    </Link>
  );
}
