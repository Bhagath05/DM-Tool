"use client";

/**
 * Phase 6 — Opportunity Center.
 *
 * The top-level component for `/opportunities`. Three layers, top to
 * bottom:
 *
 *   1. Hero `<AiRecommendation>` — the SINGLE most leveraged action
 *      across content + ads.
 *   2. Content opportunities — what to create.
 *   3. Ad opportunities — what to spend on.
 *
 * Each opportunity carries the full Constitution contract and a
 * "Generate this" button that deep-links into the existing /content
 * or /ads studio with the form pre-filled (using URL query params
 * those studios already honour).
 *
 * Client-cached for 30 minutes via localStorage. Same pattern as
 * Lead Intelligence + Analytics Summary.
 */

import {
  ArrowRight,
  Compass,
  Loader2,
  Megaphone,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AiRecommendation } from "@/components/ui/business-metric";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type OpportunityCenterReport,
} from "@/lib/api";

import { OpportunityCard } from "./opportunity-card";

const CACHE_KEY = "aicmo:opportunity-center:v1";
const CACHE_MAX_AGE_MS = 30 * 60 * 1000; // 30 min

type State =
  | { kind: "loading" }
  | { kind: "no-profile" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: OpportunityCenterReport };

export function OpportunityCenter() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({ kind: "ready", report: cached });
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const report = await api.opportunities.center();
        writeCache(report);
        setState({ kind: "ready", report });
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          setState({ kind: "no-profile" });
          return;
        }
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyError(e.message)
              : "Couldn't read your opportunities right now.",
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

  if (state.kind === "loading") {
    return (
      <Card data-testid="opportunities-loading">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            Reading your business…
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The AI is picking the highest-leverage content and ad moves to
          make this week. One moment.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "no-profile") {
    return (
      <Card data-testid="opportunities-no-profile">
        <CardHeader>
          <CardTitle className="text-base">
            Finish business onboarding first
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The Opportunity Center reads your industry, audience, and
          channels — it can&apos;t recommend anything useful without
          your profile.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card data-testid="opportunities-error">
        <CardHeader>
          <CardTitle className="text-base">
            Couldn&apos;t pick your opportunities
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
    <div className="space-y-6" data-testid="opportunities">
      <HeadlineStrip
        headline={report.headline}
        refreshing={refreshing}
        onRefresh={() => void load({ force: true })}
      />

      <AiRecommendation
        data-testid="opportunities-hero"
        whatIsHappening={report.hero_recommendation.what_is_happening}
        impactCategory={report.hero_recommendation.impact_category}
        recommendation={report.hero_recommendation.recommendation}
        expectedResult={report.hero_recommendation.expected_result}
        confidence={report.hero_recommendation.confidence}
        reason={report.hero_recommendation.reason}
      />

      <OpportunitySection
        title="Content opportunities"
        icon={Sparkles}
        empty="Nothing to ship this week — keep doing what's working."
        items={report.content_opportunities}
        testId="content-opportunities"
      />

      <OpportunitySection
        title="Ad opportunities"
        icon={Megaphone}
        empty="No ad change recommended — your organic signal isn't clear enough yet to justify spend."
        items={report.ad_opportunities}
        testId="ad-opportunities"
      />

      {report.skip_for_now.length > 0 && (
        <SkipForNow items={report.skip_for_now} />
      )}

      {report.signals_used.length > 0 && (
        <details className="rounded-md border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            <Sparkles className="mr-1 inline h-3 w-3" />
            How this was built
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

function HeadlineStrip({
  headline,
  refreshing,
  onRefresh,
}: {
  headline: string;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <Compass className="h-3.5 w-3.5" />
            This week
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
          data-testid="opportunities-refresh"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </CardHeader>
    </Card>
  );
}

function OpportunitySection({
  title,
  icon: Icon,
  items,
  empty,
  testId,
}: {
  title: string;
  icon: typeof Sparkles;
  items: OpportunityCenterReport["content_opportunities"];
  empty: string;
  testId: string;
}) {
  return (
    <section className="space-y-3" data-testid={testId}>
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {title}
        <span className="text-muted-foreground/60">· {items.length}</span>
      </div>
      {items.length === 0 ? (
        <Card>
          <CardContent
            className="pt-6 text-sm text-muted-foreground"
            data-testid={`${testId}-empty`}
          >
            {empty}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((opp) => (
            <OpportunityCard key={opp.id} opportunity={opp} />
          ))}
        </div>
      )}
    </section>
  );
}

function SkipForNow({ items }: { items: string[] }) {
  return (
    <div
      className="rounded-md border border-dashed bg-muted/30 px-3 py-2.5"
      data-testid="opportunities-skip"
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
//  Local cache — same pattern as analytics-summary + lead-intelligence
// ---------------------------------------------------------------------

interface CacheEntry {
  ts: number;
  data: OpportunityCenterReport;
}

function readCache(): OpportunityCenterReport | null {
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

function writeCache(data: OpportunityCenterReport): void {
  if (typeof window === "undefined") return;
  try {
    const entry: CacheEntry = { ts: Date.now(), data };
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    /* persistence is best-effort */
  }
}

/** Test-only — let test suites wipe the cache between runs. */
export const __OPPORTUNITY_CACHE_KEY = CACHE_KEY;
