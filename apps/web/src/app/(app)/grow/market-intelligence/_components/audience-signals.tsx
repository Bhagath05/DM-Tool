"use client";

/**
 * Phase 10.3c — Audience Signals.
 *
 *   ✓ Lead quality increasing       ✓ CPC decreasing
 *   ✓ CTR increasing                ⚠ Reels engagement dipping
 *
 * Compose signals from two existing sources:
 *   - `api.social.audiencePatterns()` — backend's audience pattern engine
 *     (pattern_type + description + confidence_score)
 *   - `api.performance.overview()` — perf diagnostics (winners + losers)
 *     re-shaped as "the metric is moving" signals
 *
 * Founder Rule: every signal carries a hint at WHAT TO DO. Steady-state
 * info ("you have 12 leads") is excluded — that's not a signal, it's a
 * tile (lives on Today's Plan).
 */

import {
  ArrowDownRight,
  ArrowUpRight,
  Radar,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, type AudiencePattern } from "@/lib/api";
import { translateOverview } from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

export type SignalTone = "good" | "watch" | "neutral";

export interface AudienceSignal {
  id: string;
  tone: SignalTone;
  label: string;
  detail: string | null;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; signals: AudienceSignal[] };

const MAX_SIGNALS = 8;

export function AudienceSignals({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    const signals: AudienceSignal[] = [];

    const [patternsResult, overviewResult] = await Promise.allSettled([
      api.social.audiencePatterns(),
      api.performance.overview(),
    ]);

    if (patternsResult.status === "fulfilled") {
      for (const p of patternsResult.value) {
        if (signals.length >= MAX_SIGNALS) break;
        signals.push(audiencePatternToSignal(p));
      }
    } else if (!(patternsResult.reason instanceof ApiError)) {
      console.warn(patternsResult.reason);
    }

    if (overviewResult.status === "fulfilled") {
      const cards = translateOverview(overviewResult.value);
      for (const c of cards.cards) {
        if (signals.length >= MAX_SIGNALS) break;
        const sig = perfCardToSignal(c);
        if (sig) signals.push(sig);
      }
    } else if (!(overviewResult.reason instanceof ApiError)) {
      console.warn(overviewResult.reason);
    }

    setState({ kind: "ready", signals });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="audience-signals"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Radar className="h-3 w-3" />
            Audience signals
          </span>
        }
        heading="What your audience is doing"
        description="The shifts our engine has spotted across your audience + performance data."
      />

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "ready" && state.signals.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title="No signals yet"
          description="Once you have connected social + performance data, signals will appear here."
          data-testid="audience-signals-empty"
        />
      )}

      {state.kind === "ready" && state.signals.length > 0 && (
        <ul
          className="grid grid-cols-1 gap-2 sm:grid-cols-2"
          data-testid="audience-signals-list"
        >
          {state.signals.map((s) => (
            <SignalRow key={s.id} signal={s} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row
// ---------------------------------------------------------------------

function SignalRow({ signal }: { signal: AudienceSignal }) {
  const Icon =
    signal.tone === "good"
      ? TrendingUp
      : signal.tone === "watch"
        ? TrendingDown
        : Radar;
  const ArrowIcon =
    signal.tone === "good"
      ? ArrowUpRight
      : signal.tone === "watch"
        ? ArrowDownRight
        : ArrowUpRight;
  return (
    <li
      data-testid={`audience-signal-${signal.id}`}
      className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3"
    >
      <span
        className={cn(
          "mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          signal.tone === "good" && "bg-good/15 text-good-foreground",
          signal.tone === "watch" && "bg-watch/15 text-watch-foreground",
          signal.tone === "neutral" && "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-start gap-1 text-sm font-medium text-foreground">
          <span className="min-w-0 flex-1">{signal.label}</span>
          <ArrowIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
        </span>
        {signal.detail && (
          <span className="text-xs text-muted-foreground">{signal.detail}</span>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------
//  Composition helpers
// ---------------------------------------------------------------------

function audiencePatternToSignal(p: AudiencePattern): AudienceSignal {
  // AudiencePattern.description is already a human sentence per backend
  // contract. The pattern_type is a slug we humanise for the detail line.
  return {
    id: `audience-${p.id}`,
    tone: "neutral",
    label: p.description,
    detail: `${humanizePatternType(p.pattern_type)} · ${p.confidence_score}% confidence`,
  };
}

function perfCardToSignal(
  card: ReturnType<typeof translateOverview>["cards"][number],
): AudienceSignal | null {
  // Only kinds that read as movement, not steady state.
  const POSITIVE = new Set([
    "winner",
    "audience_winner",
    "concept_winner",
    "creative_dna",
  ]);
  const NEGATIVE = new Set(["budget_waste", "audience_loser"]);

  let tone: SignalTone;
  if (POSITIVE.has(card.kind)) tone = "good";
  else if (NEGATIVE.has(card.kind)) tone = "watch";
  else return null;

  return {
    id: `perf-${card.id}`,
    tone,
    label: card.whatIsHappening,
    detail: card.recommendation,
  };
}

function humanizePatternType(t: string): string {
  return t
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}
