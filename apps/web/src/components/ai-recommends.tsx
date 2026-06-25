"use client";

/**
 * Phase 10.5 — AI Recommends preset row.
 *
 * Closes the recommendation → execution loop:
 *
 *   Opportunity (api.opportunities.center)
 *      ↓
 *   AiRecommends card with "Use this brief" CTA
 *      ↓
 *   Studio form prefilled, founder reviews + hits Generate
 *
 * Mounts at the top of Content Studio and Ads Studio. Filters the
 * opportunity feed to `generator.target === target` (content vs ad),
 * shows top 3 by confidence, gives each a one-click prefill button.
 *
 * Honest empty states: when no opportunities targeting this studio
 * exist, the row hides itself entirely rather than showing fake
 * recommendations.
 */

import { ArrowRight, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type Opportunity,
  type OpportunityCenterReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Brief the founder receives when they click "Use this brief". */
export interface RecommendedBrief {
  opportunityId: string;
  headline: string;
  format: string | null;
  platform: string | null;
  goal: string | null;
  objective: string | null;
  recommendedAction: string;
  whyItMatters: string;
  expectedResult: string;
  confidence: number;
}

export interface AiRecommendsProps {
  /** Which studio is mounting this — picks the opportunity filter. */
  target: "content" | "ad";
  /** Called when the founder clicks "Use this brief". Studio uses
   *  this to prefill its form. */
  onUseBrief: (brief: RecommendedBrief) => void;
  className?: string;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: Opportunity[] }
  | { kind: "hidden" };

const MAX = 3;

export function AiRecommends({ target, onUseBrief, className }: AiRecommendsProps) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report: OpportunityCenterReport = await api.opportunities.center();
      const pool =
        target === "content"
          ? (report.content_opportunities ?? [])
          : (report.ad_opportunities ?? []);
      if (pool.length === 0) {
        // Honest: no recommendations targeting this studio. Hide the
        // row entirely — don't show a confusing empty state.
        setState({ kind: "hidden" });
        return;
      }
      const ranked = [...pool]
        .sort((a, b) => b.confidence - a.confidence)
        .slice(0, MAX);
      setState({ kind: "ready", items: ranked });
    } catch (err) {
      // Backend incomplete (e.g. 409 — onboarding) is silent: hide
      // the row, don't bother the founder with an error.
      if (!(err instanceof ApiError)) console.warn(err);
      setState({ kind: "hidden" });
    }
  }, [target]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "hidden") return null;

  return (
    <section
      data-testid={`ai-recommends-${target}`}
      className={cn("flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            AI Recommends
          </span>
        }
        heading={
          target === "content"
            ? "Top content briefs for you this week"
            : "Top ad briefs for you this week"
        }
        description="One click prefills the form below. Edit anything, then generate."
      />

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "ready" && (
        <div
          className="grid grid-cols-1 gap-3 sm:grid-cols-3"
          data-testid={`ai-recommends-${target}-list`}
        >
          {state.items.map((opp) => (
            <BriefCard
              key={opp.id}
              opp={opp}
              onUse={() => onUseBrief(toBrief(opp))}
            />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Card
// ---------------------------------------------------------------------

function BriefCard({ opp, onUse }: { opp: Opportunity; onUse: () => void }) {
  return (
    <article
      data-testid={`ai-recommends-card-${opp.id}`}
      className={cn(
        "flex h-full flex-col gap-2.5 rounded-2xl border border-border bg-card p-4 transition-all duration-200",
        "hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm",
      )}
    >
      <header className="flex flex-wrap items-center gap-1.5">
        <StatusPill tone="ai" size="sm" dot>
          {opp.confidence}%
        </StatusPill>
        {opp.generator?.format && (
          <StatusPill tone="muted" size="sm">
            {humanise(opp.generator.format)}
          </StatusPill>
        )}
        {opp.generator?.platform && (
          <StatusPill tone="muted" size="sm">
            {humanise(opp.generator.platform)}
          </StatusPill>
        )}
      </header>

      <h3 className="text-sm font-semibold text-foreground line-clamp-2">
        {opp.headline}
      </h3>

      {opp.recommended_action && (
        <p className="text-xs text-muted-foreground line-clamp-3">
          {opp.recommended_action}
        </p>
      )}

      <button
        type="button"
        onClick={onUse}
        data-testid={`ai-recommends-use-${opp.id}`}
        className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
      >
        Use this brief
        <ArrowRight className="h-3 w-3" />
      </button>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Pure helpers (exported for tests)
// ---------------------------------------------------------------------

export function toBrief(opp: Opportunity): RecommendedBrief {
  return {
    opportunityId: opp.id,
    headline: opp.headline,
    format: opp.generator?.format ?? null,
    platform: opp.generator?.platform ?? null,
    goal: opp.generator?.goal ?? null,
    objective: opp.generator?.objective ?? null,
    recommendedAction: opp.recommended_action,
    whyItMatters: opp.why_it_matters,
    expectedResult: opp.expected_result,
    confidence: opp.confidence,
  };
}

function humanise(s: string): string {
  if (s === "google_search") return "Google Search";
  return s
    .split(/[_\s]+/)
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}
