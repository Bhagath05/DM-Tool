"use client";

/**
 * Phase 10.3c — Best Posting Windows.
 *
 *   Instagram   11:00 · 14:00 · 19:00   87%  ● Derived
 *   LinkedIn    08:30 · 12:00 · 17:30   74%  ● Derived
 *   Facebook    13:00 · 18:00            55%  ◌ Estimated
 *   Twitter/X   09:00 · 15:00            50%  ◌ Estimated
 *
 * Uses `api.social.patterns()` for personalised windows and falls
 * back to industry-norm placeholders for platforms with no patterns
 * yet. Placeholders are explicitly labelled "Estimated" so the founder
 * never mistakes them for personalised intelligence.
 *
 * No hardcoded "best times". See `lib/posting-time.ts` for the
 * structure + parser + placeholder source.
 */

import { Clock, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, type WinningPattern } from "@/lib/api";
import {
  formatWindow,
  planForDay,
  todayWeekday,
  type PlatformPostingPlan,
} from "@/lib/posting-time";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; plans: PlatformPostingPlan[]; anyDerived: boolean };

const PLATFORM_LABEL: Record<PlatformPostingPlan["platform"], string> = {
  instagram: "Instagram",
  linkedin: "LinkedIn",
  facebook: "Facebook",
  twitter: "Twitter / X",
  tiktok: "TikTok",
  youtube: "YouTube",
};

// Display order — founders read top-down, so highest-engagement
// platforms first. Order is stable regardless of source.
const DISPLAY_ORDER: PlatformPostingPlan["platform"][] = [
  "instagram",
  "linkedin",
  "facebook",
  "twitter",
  "tiktok",
  "youtube",
];

export function PostingTimeIntelligence({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      let patterns: WinningPattern[] = [];
      try {
        patterns = await api.social.patterns();
      } catch (err) {
        // Falling back to placeholders is the correct behaviour here —
        // the section still renders something useful + honest.
        if (!(err instanceof ApiError)) console.warn(err);
      }
      const plans = planForDay(patterns, todayWeekday());
      const anyDerived = plans.some((p) => p.source === "derived");
      // Sort by display order, putting derived plans first within ties.
      plans.sort((a, b) => {
        const ai = DISPLAY_ORDER.indexOf(a.platform);
        const bi = DISPLAY_ORDER.indexOf(b.platform);
        return ai - bi;
      });
      setState({ kind: "ready", plans, anyDerived });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load posting windows.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="posting-time-intelligence"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            Best posting windows
          </span>
        }
        heading={`When to post today, by platform`}
        description={
          state.kind === "ready" && state.anyDerived
            ? "Personalised from your winning patterns. Hit the highlighted slot first."
            : "Estimated from industry norms — connect a social handle to personalise."
        }
      />

      {state.kind === "loading" && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Posting windows unavailable"
          description={state.message}
          data-testid="posting-time-error"
        />
      )}

      {state.kind === "ready" && (
        <ul className="flex flex-col gap-2" data-testid="posting-time-list">
          {state.plans.map((plan) => (
            <PlatformRow key={plan.platform} plan={plan} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  One platform row
// ---------------------------------------------------------------------

function PlatformRow({ plan }: { plan: PlatformPostingPlan }) {
  // Top window confidence (used as the row-level score).
  const topConfidence = plan.windows.reduce(
    (acc, w) => Math.max(acc, w.confidence_score),
    0,
  );
  const isDerived = plan.source === "derived";

  return (
    <li>
      <div
        data-testid={`posting-time-row-${plan.platform}`}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3"
      >
        <span className="inline-flex w-32 shrink-0 items-center gap-2 text-sm font-medium text-foreground">
          {PLATFORM_LABEL[plan.platform]}
        </span>
        <ul className="flex flex-1 flex-wrap items-center gap-2" aria-label="Time windows">
          {plan.windows.map((w, i) => (
            <li key={i}>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium tabular-nums",
                  isDerived
                    ? "border-ai-border bg-ai-soft text-ai-soft-foreground"
                    : "border-border bg-muted text-foreground",
                )}
                data-testid={`posting-time-window-${plan.platform}-${i}`}
              >
                {formatWindow(w)}
              </span>
            </li>
          ))}
        </ul>
        <span className="ml-auto inline-flex items-center gap-2">
          <span className="text-xs font-semibold tabular-nums text-foreground">
            {topConfidence}%
          </span>
          <StatusPill
            tone={isDerived ? "ai" : "muted"}
            size="sm"
            data-testid={`posting-time-source-${plan.platform}`}
          >
            {isDerived ? "Derived" : "Estimated"}
          </StatusPill>
        </span>
      </div>
    </li>
  );
}
