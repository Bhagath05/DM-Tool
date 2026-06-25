"use client";

/**
 * Phase 10.4 — Next Best Action (Command Center top card).
 *
 * The single highest-leverage action right now. Pulls from
 * `api.coach.weekly()` — same source as AiCoachPanel on /today — but
 * renders the full Action Scoring footer (Confidence · Reach · Leads ·
 * Revenue · Difficulty · Time) the directive specifies.
 *
 *   ⭐ YOUR NEXT BEST ACTION
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ Publish reel: "Top 5 Payroll Mistakes Startups Make"         │
 *   │                                                              │
 *   │ Why:                                                         │
 *   │   Trend momentum +42% · Competitors not covering it          │
 *   │                                                              │
 *   │ Expected impact:                                             │
 *   │   Reach 12k+ · Leads +15 · ₹15k–₹25k revenue                 │
 *   │                                                              │
 *   │ Confidence 89% · Some effort · 45 mins                       │
 *   │                                                              │
 *   │ [ Generate Now → ]    [ See all actions ]                    │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Constitution discipline: every field is required to render; the
 * <CoachCardContract> guard returns an honest empty when the LLM
 * shipped an incomplete action.
 */

import { ArrowRight, Compass, Sparkles, Wand2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonCard } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type WeeklyAction,
  type WeeklyPlan,
} from "@/lib/api";
import { humaniseDifficulty, scoreWeeklyAction } from "@/lib/action-scoring";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; plan: WeeklyPlan; top: WeeklyAction };

export function NextBestAction({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const plan = await api.coach.weekly();
      const top =
        plan.actions.find((a) => a.priority === "focus") ?? plan.actions[0];
      if (!top) {
        setState({ kind: "empty" });
        return;
      }
      setState({ kind: "ready", plan, top });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Couldn't load the action.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="next-best-action"
      className={cn("animate-fade-up flex flex-col gap-5", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Wand2 className="h-3 w-3" />
            Your next best action
          </span>
        }
        heading={
          state.kind === "ready" ? state.plan.headline : "What to do next"
        }
        description={
          state.kind === "ready"
            ? state.plan.week_focus
            : "The single move our engine ranks above everything else right now."
        }
        size="lg"
      />

      {state.kind === "loading" && (
        <SkeletonCard data-testid="next-best-action-skeleton" />
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="Action unavailable"
          description={state.message}
          data-testid="next-best-action-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Compass}
          variant="ai"
          title="No high-leverage action yet"
          description="Once your data produces clear signal, we'll surface the single highest-impact move here."
          data-testid="next-best-action-empty"
        />
      )}

      {state.kind === "ready" && <ActionCard action={state.top} />}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Card
// ---------------------------------------------------------------------

function ActionCard({ action }: { action: WeeklyAction }) {
  const score = scoreWeeklyAction(action);
  const ctaHref = ctaTargetHref(action.cta_target);

  return (
    <article
      data-testid="next-best-action-card"
      className="relative overflow-hidden card-surface-ai p-7 sm:p-8"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -right-32 h-72 w-72 rounded-full bg-ai/15 blur-3xl animate-pulse-soft"
      />

      <div className="relative flex flex-col gap-6">
        {/* Top stripe */}
        <header className="flex flex-wrap items-center gap-2">
          <StatusPill tone="ai" size="md" dot icon={Sparkles}>
            Highest impact today
          </StatusPill>
          <StatusPill tone="muted" size="md">
            {humaniseDifficulty(score.difficulty)}
          </StatusPill>
          <StatusPill tone="muted" size="md">
            {score.timeRequired}
          </StatusPill>
        </header>

        {/* Action title */}
        <h3 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          {action.action_title}
        </h3>

        {/* Why */}
        <div className="flex flex-col gap-1">
          <span className="text-meta">Why</span>
          <p className="text-sm text-muted-foreground sm:text-base">
            {action.why}
          </p>
        </div>

        {/* Expected impact — Constitution business-impact line */}
        <div className="flex flex-col gap-1">
          <span className="text-meta">Expected impact</span>
          <p className="text-sm font-medium text-foreground sm:text-base">
            {action.business_impact}
          </p>
          {(score.expectedLeads || score.expectedRevenue) && (
            <ul
              className="mt-1 flex flex-wrap gap-1.5"
              aria-label="Expected impact details"
            >
              {score.expectedReach.band !== "unknown" && (
                <li>
                  <StatusPill tone="good" size="sm">
                    Reach {score.expectedReach.display}
                  </StatusPill>
                </li>
              )}
              {score.expectedLeads && (
                <li>
                  <StatusPill tone="good" size="sm">
                    {score.expectedLeads}
                  </StatusPill>
                </li>
              )}
              {score.expectedRevenue && (
                <li>
                  <StatusPill tone="good" size="sm">
                    {score.expectedRevenue}
                  </StatusPill>
                </li>
              )}
            </ul>
          )}
        </div>

        {/* Confidence */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="text-meta">Confidence</span>
            <span className="text-sm font-semibold tabular-nums">
              {score.confidence}%
            </span>
          </div>
          <ConfidenceBar value={score.confidence} />
          <p className="text-xs text-muted-foreground">{action.reason}</p>
        </div>

        {/* CTAs */}
        <div className="flex flex-wrap gap-3">
          <Link
            href={ctaHref as never}
            data-testid="next-best-action-cta"
            className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-4 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-foreground/90"
          >
            {action.cta_label || "Generate now"}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
          <Link
            href={"/ai-coach" as never}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:border-ai-border hover:text-foreground"
          >
            See all actions
          </Link>
        </div>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------
//  CTA target → frontend URL
// ---------------------------------------------------------------------

function ctaTargetHref(target: WeeklyAction["cta_target"]): string {
  switch (target) {
    case "content":
      return "/create/social-posts?from=command-center";
    case "ads":
      return "/create/ads?from=command-center";
    case "visuals":
      return "/create/creatives?from=command-center";
    case "campaigns":
      return "/campaigns";
    case "lead_pages":
      return "/grow/leads";
    case "trends":
      return "/grow/market-intelligence";
    case "analytics":
      return "/results";
    case "profile":
      return "/settings/organization";
    default: {
      const _exhaustive: never = target;
      void _exhaustive;
      return "/today";
    }
  }
}
