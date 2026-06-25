"use client";

import { ArrowRight, Loader2, RefreshCw, Sparkles, Target } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type AnalyticsSummary } from "@/lib/api";

/**
 * Phase 2.5 — AI Analytics Explanation Layer.
 *
 * Hero card at the top of the analytics dashboard: headline + what-to-do-next.
 * Same Gemini call ALSO populates per-section blurbs (passed down to existing
 * cards via the `summary` prop on each). This component renders only the hero.
 *
 * Client-cached for 30 minutes via localStorage — analytics data shifts
 * sub-hourly during active use, so half an hour is the sweet spot between
 * freshness and not burning a Gemini call on every dashboard refresh.
 */

const CACHE_KEY = "aicmo:analytics-summary:v1";
const CACHE_MAX_AGE_MS = 30 * 60 * 1000; // 30 min

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; summary: AnalyticsSummary };

export function useAnalyticsSummary() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({ kind: "ready", summary: cached });
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const summary = await api.coach.analyticsSummary();
        writeCache(summary);
        setState({ kind: "ready", summary });
      } catch (e) {
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyError(e.message)
              : "Couldn't read the dashboard right now.",
        });
      } finally {
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return {
    state,
    refreshing,
    refresh: () => void load({ force: true }),
  };
}

export function AnalyticsSummaryCard({
  state,
  refreshing,
  onRefresh,
}: {
  state: LoadState;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  if (state.kind === "loading") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            Reading your dashboard…
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The AI is summarising your numbers in plain English. One moment.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Couldn&apos;t summarise your dashboard
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{state.message}</p>
          <Button onClick={onRefresh} disabled={refreshing}>
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

  const { summary } = state;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            What the numbers say
          </div>
          <CardTitle className="text-base leading-snug">
            {summary.headline}
          </CardTitle>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing}
          title="Regenerate the summary"
          className="text-muted-foreground"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2.5">
          <Target className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div className="flex-1">
            <div className="text-[10px] font-medium uppercase tracking-wide text-primary">
              Do this next
            </div>
            <p className="mt-0.5 text-sm leading-relaxed">
              {summary.what_to_do_next}
            </p>
          </div>
        </div>
        {summary.signals_used.length > 0 && (
          <details className="rounded-md border bg-muted/20 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <Sparkles className="mr-1 inline h-3 w-3" />
              What I looked at
            </summary>
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
              {summary.signals_used.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <ArrowRight className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Lightweight inline blurb shown ABOVE each existing analytics card.
 * Renders nothing when the summary hasn't loaded yet — never blocks
 * the chart underneath.
 */
export function SectionBlurb({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <p className="px-1 text-xs italic text-muted-foreground">
      <Sparkles className="mr-1 inline h-3 w-3" />
      {text}
    </p>
  );
}

// ---------------- helpers ----------------

function friendlyError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("409") || lowered.includes("onboarding")) {
    return "Finish business onboarding first — the AI needs your profile to read the dashboard.";
  }
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI is under heavy load. Try again in a moment.";
  }
  return "The AI couldn't summarise this round. Try again — usually fixes on the second call.";
}

function readCache(): AnalyticsSummary | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      savedAt: number;
      summary: AnalyticsSummary;
    };
    if (Date.now() - parsed.savedAt > CACHE_MAX_AGE_MS) return null;
    return parsed.summary;
  } catch {
    return null;
  }
}

function writeCache(summary: AnalyticsSummary): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ savedAt: Date.now(), summary }),
    );
  } catch {
    /* quota — ignore */
  }
}
