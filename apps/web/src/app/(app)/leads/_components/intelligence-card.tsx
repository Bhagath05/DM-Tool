"use client";

/**
 * Phase 5 — Lead Intelligence card.
 *
 * Sits at the top of /leads. Three layers, top to bottom:
 *
 *   1. Counts strip          (total / new / hot / last 24h)
 *   2. Hero `<AiRecommendation>` — the SINGLE most important action
 *      across the whole inbox today.
 *   3. Per-lead priority list — up to 5 ranked rows, exactly one
 *      marked 'focus'. Each row carries the full Constitution contract
 *      (why now, action, expected result, confidence, reason).
 *
 * Client-cached for 30 minutes via localStorage — analytics data
 * shifts sub-hourly during active use, so half an hour is the sweet
 * spot between freshness and not burning a Gemini call on every
 * inbox visit. Mirrors `analytics/summary-card`'s pattern.
 */

import {
  ArrowRight,
  Compass,
  Flame,
  Inbox,
  Loader2,
  RefreshCw,
  Snowflake,
  Sparkles,
  Star,
  Thermometer,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AiRecommendation } from "@/components/ui/business-metric";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type LeadIntelligenceReport,
  type LeadPriorityBucket,
  type LeadPriorityItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const CACHE_KEY = "aicmo:lead-intelligence:v1";
const CACHE_MAX_AGE_MS = 30 * 60 * 1000; // 30 min

type State =
  | { kind: "loading" }
  | { kind: "no-profile" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: LeadIntelligenceReport };

/**
 * Inbox-level intelligence header. Receives an optional
 * `onPrioritiesResolved` callback so the parent `<Inbox>` can pass the
 * resolved priorities down to each row + the drawer — same data, no
 * second network call.
 */
export function LeadIntelligenceCard({
  onReport,
}: {
  onReport?: (report: LeadIntelligenceReport | null) => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({ kind: "ready", report: cached });
          onReport?.(cached);
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const report = await api.leads.intelligence();
        writeCache(report);
        setState({ kind: "ready", report });
        onReport?.(report);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          setState({ kind: "no-profile" });
          onReport?.(null);
          return;
        }
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyError(e.message)
              : "Couldn't read your inbox right now.",
        });
        onReport?.(null);
      } finally {
        setRefreshing(false);
      }
    },
    [onReport],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <Card data-testid="lead-intelligence-loading">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            Reading your inbox…
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The AI is picking which lead is worth your time today. One moment.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "no-profile") {
    return (
      <Card data-testid="lead-intelligence-no-profile">
        <CardHeader>
          <CardTitle className="text-base">
            Finish business onboarding first
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Lead intelligence picks who to contact first based on your
          industry, audience, and stage — we can&apos;t suggest anything
          useful without your profile.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card data-testid="lead-intelligence-error">
        <CardHeader>
          <CardTitle className="text-base">
            Couldn&apos;t pick your top lead
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{state.message}</p>
          <Button
            onClick={() => void load({ force: true })}
            disabled={refreshing}
          >
            {refreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { report } = state;
  return (
    <div className="space-y-4" data-testid="lead-intelligence">
      <CountsStrip
        report={report}
        refreshing={refreshing}
        onRefresh={() => void load({ force: true })}
      />

      <AiRecommendation
        data-testid="lead-intelligence-hero"
        whatIsHappening={report.hero_recommendation.what_is_happening}
        impactCategory={report.hero_recommendation.impact_category}
        recommendation={report.hero_recommendation.recommendation}
        expectedResult={report.hero_recommendation.expected_result}
        confidence={report.hero_recommendation.confidence}
        reason={report.hero_recommendation.reason}
      />

      {report.priorities.length > 0 && (
        <PriorityList priorities={report.priorities} />
      )}

      {report.skip_for_now.length > 0 && (
        <SkipForNow items={report.skip_for_now} />
      )}

      {report.signals_used.length > 0 && (
        <details className="rounded-md border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            <Sparkles className="mr-1 inline h-3 w-3" />
            What I looked at
          </summary>
          <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
            {report.signals_used.map((s, i) => (
              <li key={i} className="flex gap-2">
                <ArrowRight className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                <span>{s}</span>
              </li>
            ))}
          </ul>
          <div className="mt-2 text-[10px] text-muted-foreground">
            Updated {formatRelative(report.generated_at)}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Subcomponents
// ---------------------------------------------------------------------

function CountsStrip({
  report,
  refreshing,
  onRefresh,
}: {
  report: LeadIntelligenceReport;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const { counts, headline } = report;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <Inbox className="h-3.5 w-3.5" />
            Inbox today
          </div>
          <CardTitle className="text-base leading-snug">{headline}</CardTitle>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing}
          title="Re-rank with fresh data"
          className="text-muted-foreground"
          data-testid="lead-intelligence-refresh"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </CardHeader>
      <CardContent className="pt-0">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CountTile label="Total" value={counts.total} />
          <CountTile label="New" value={counts.new_count} />
          <CountTile label="Hot" value={counts.hot_count} accent="hot" />
          <CountTile label="Last 24h" value={counts.last_24h} accent="fresh" />
        </dl>
      </CardContent>
    </Card>
  );
}

function CountTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: "hot" | "fresh";
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 text-2xl font-semibold tabular-nums",
          accent === "hot" && value > 0 && "text-rose-600 dark:text-rose-400",
          accent === "fresh" && value > 0 && "text-sky-600 dark:text-sky-400",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function PriorityList({ priorities }: { priorities: LeadPriorityItem[] }) {
  const focus = priorities.find((p) => p.priority === "focus");
  const rest = priorities.filter((p) => p !== focus);
  return (
    <div className="space-y-3" data-testid="lead-intelligence-priorities">
      {focus && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-primary">
            <Compass className="h-3.5 w-3.5" />
            Start here
          </div>
          <PriorityRow item={focus} emphasized />
        </div>
      )}
      {rest.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Then work through
          </div>
          <div className="space-y-2">
            {rest.map((p) => (
              <PriorityRow key={p.lead_id} item={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const BUCKET_META: Record<
  LeadPriorityBucket,
  { label: string; icon: typeof Flame; cls: string }
> = {
  focus: {
    label: "Focus",
    icon: Star,
    cls: "bg-primary/15 text-primary",
  },
  hot: {
    label: "Hot",
    icon: Flame,
    cls: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  },
  warm: {
    label: "Warm",
    icon: Thermometer,
    cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  },
  cold: {
    label: "Cold",
    icon: Snowflake,
    cls: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  },
};

const VALUE_BAND_LABEL: Record<LeadPriorityItem["estimated_value_band"], string> = {
  high: "High value",
  medium: "Medium value",
  low: "Small but worth it",
  unknown: "Value unclear",
};

/**
 * Single-lead advisory row — exported so the founder-first
 * `/today` command center renders identical-looking lead cards without
 * copy-pasting the layout. Always re-renders the full Constitution
 * contract (why now → do this → expected → confidence + reason).
 */
export function PriorityRow({
  item,
  emphasized,
}: {
  item: LeadPriorityItem;
  emphasized?: boolean;
}) {
  const meta = BUCKET_META[item.priority];
  const Icon = meta.icon;
  const band = confidenceBand(item.confidence);
  return (
    <article
      data-testid={`lead-priority-${item.priority}`}
      className={cn(
        "rounded-md border bg-card p-3 sm:p-4",
        emphasized && "border-primary/30 bg-primary/5",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            meta.cls,
          )}
        >
          <Icon className="h-3 w-3" />
          {meta.label}
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          #{item.rank}
        </span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          · {VALUE_BAND_LABEL[item.estimated_value_band]}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">
          {item.cta_label}
        </span>
      </header>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-sm font-semibold">{item.name ?? item.email}</span>
        {item.name && (
          <span className="text-xs text-muted-foreground">{item.email}</span>
        )}
        {item.company && (
          <span className="text-xs text-muted-foreground">
            · {item.company}
          </span>
        )}
      </div>

      <p className="mt-2 text-sm leading-snug">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Why now ·{" "}
        </span>
        {item.why_now}
      </p>

      <p className="mt-1.5 text-sm leading-snug">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-primary">
          Do this ·{" "}
        </span>
        <span className="font-medium">{item.recommended_action}</span>
      </p>

      <p className="mt-1.5 text-xs leading-snug text-muted-foreground">
        <span className="text-[10px] font-semibold uppercase tracking-wide">
          Expected ·{" "}
        </span>
        {item.expected_result}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <span
          className={cn(
            "inline-flex items-center rounded-md border px-1.5 py-0.5 font-medium",
            band.cls,
          )}
        >
          {band.label} ({item.confidence}%)
        </span>
        <span className="italic">{item.reason}</span>
      </div>
    </article>
  );
}

function SkipForNow({ items }: { items: string[] }) {
  return (
    <div
      className="rounded-md border border-dashed bg-muted/30 px-3 py-2.5"
      data-testid="lead-intelligence-skip"
    >
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Skip for now
      </div>
      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-muted-foreground">
        {items.map((s, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
            <span>{s}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function confidenceBand(confidence: number): { label: string; cls: string } {
  if (confidence >= 80)
    return {
      label: "High",
      cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
    };
  if (confidence >= 60)
    return {
      label: "Medium",
      cls: "bg-sky-500/10 text-sky-600 border-sky-500/30",
    };
  if (confidence >= 40)
    return {
      label: "Low",
      cls: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    };
  return {
    label: "Speculative",
    cls: "bg-muted text-muted-foreground border-border",
  };
}

function friendlyError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI provider was under heavy load. Wait a moment and try again — that's a temporary blip.";
  }
  if (lowered.includes("429") || lowered.includes("rate")) {
    return "We hit the AI provider's rate limit. Wait 30 seconds and try again.";
  }
  if (lowered.includes("truncated") || lowered.includes("max_tokens")) {
    return "The AI ran past its limit. Try again — most errors here are transient.";
  }
  return "Most errors here are transient — try again in a moment.";
}

function formatRelative(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "just now";
    const diff = Date.now() - then;
    const mins = Math.floor(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(iso).toLocaleString();
  } catch {
    return "just now";
  }
}

// ---------------------------------------------------------------------
//  Tiny localStorage cache — same pattern as AnalyticsSummaryCard
// ---------------------------------------------------------------------

interface CacheEntry {
  ts: number;
  data: LeadIntelligenceReport;
}

function readCache(): LeadIntelligenceReport | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry;
    if (!parsed || typeof parsed.ts !== "number" || !parsed.data) return null;
    if (Date.now() - parsed.ts > CACHE_MAX_AGE_MS) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

function writeCache(data: LeadIntelligenceReport): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry = { ts: Date.now(), data };
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    /* persistence is best-effort */
  }
}

/** Test-only — let test suites wipe the cache between runs. */
export const __LEAD_INTELLIGENCE_CACHE_KEY = CACHE_KEY;
