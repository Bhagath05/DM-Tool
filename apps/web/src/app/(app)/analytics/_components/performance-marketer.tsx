"use client";

/**
 * Phase 3 — Performance Marketer panel.
 *
 * Reads the normalized platform analytics + evidence-grounded insights from
 * `/marketing-analytics/*` and presents them the way a senior performance
 * marketer would talk to a business owner:
 *
 *   🔥 What's working    ⚠️ What needs attention    🎯 Recommended next move
 *
 * Additive: this mounts alongside the existing lead-analytics dashboard, it
 * does not replace it. Advisory only — no buttons here publish, spend, or touch
 * a connected account. Every claim is backed by computed evidence chips; when
 * there isn't enough data it says so honestly rather than inventing numbers.
 */

import {
  AlertTriangle,
  ArrowRight,
  Flame,
  Loader2,
  Minus,
  RefreshCw,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type MaCrossPlatformRow,
  type MaInsight,
  type MaPerformanceReport,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: MaPerformanceReport };

export function PerformanceMarketer() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async ({ force = false } = {}) => {
    setRefreshing(force);
    if (!force) setState({ kind: "loading" });
    try {
      const report = await api.marketingAnalytics.performance();
      setState({ kind: "ready", report });
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof Error
            ? e.message
            : "Couldn't read your platform performance right now.",
      });
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            Your performance marketer is reading the numbers…
          </CardTitle>
        </CardHeader>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Performance Marketer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{state.message}</p>
          <Button onClick={() => void load({ force: true })} disabled={refreshing}>
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
  const nothingToSay =
    !report.has_data ||
    (report.whats_working.length === 0 &&
      report.whats_not_working.length === 0 &&
      report.recommendations.length === 0);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <Flame className="h-3.5 w-3.5" />
            Performance Marketer
          </div>
          <CardTitle className="text-base leading-snug">
            {report.headline}
          </CardTitle>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void load({ force: true })}
          disabled={refreshing}
          title="Refresh"
          className="text-muted-foreground"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </CardHeader>

      <CardContent className="space-y-5 pt-0">
        {nothingToSay ? (
          <EmptyState message={report.sufficiency.message} />
        ) : (
          <>
            {report.whats_working.length > 0 && (
              <Group
                icon={<Flame className="h-4 w-4 text-emerald-500" />}
                title="What's working"
                insights={report.whats_working}
                tone="good"
              />
            )}
            {report.whats_not_working.length > 0 && (
              <Group
                icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
                title="What needs attention"
                insights={report.whats_not_working}
                tone="attention"
              />
            )}
            {report.recommendations.length > 0 && (
              <Group
                icon={<Target className="h-4 w-4 text-primary" />}
                title="Recommended next move"
                insights={report.recommendations}
                tone="neutral"
              />
            )}
          </>
        )}

        {report.platform_comparison.length > 0 && (
          <PlatformComparison rows={report.platform_comparison} />
        )}
      </CardContent>
    </Card>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center">
      <p className="text-sm font-medium">Not enough data yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {message} Connect a platform and keep publishing — your performance
        marketer needs about a week of activity before calling trends.
      </p>
    </div>
  );
}

const TONE: Record<
  "good" | "attention" | "neutral",
  { border: string; chip: string }
> = {
  good: { border: "border-emerald-500/30 bg-emerald-500/5", chip: "text-emerald-600" },
  attention: { border: "border-amber-500/30 bg-amber-500/5", chip: "text-amber-600" },
  neutral: { border: "border-primary/30 bg-primary/5", chip: "text-primary" },
};

function Group({
  icon,
  title,
  insights,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  insights: MaInsight[];
  tone: "good" | "attention" | "neutral";
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>
      <div className="space-y-2">
        {insights.map((i) => (
          <InsightCard key={i.id} insight={i} tone={tone} />
        ))}
      </div>
    </section>
  );
}

function InsightCard({
  insight,
  tone,
}: {
  insight: MaInsight;
  tone: "good" | "attention" | "neutral";
}) {
  const t = TONE[tone];
  return (
    <div className={`rounded-md border px-3 py-2.5 ${t.border}`}>
      <p className="text-sm font-medium leading-snug">{insight.observation}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-medium">Why:</span> {insight.interpretation}
      </p>

      <div className="mt-2 flex items-start gap-2 rounded border bg-background/60 px-2.5 py-1.5">
        <ArrowRight className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${t.chip}`} />
        <div className="flex-1">
          <p className="text-sm leading-snug">{insight.recommendation}</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Expected: {insight.expected_result}
          </p>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {insight.evidence
          .filter((e) => e.change_percent !== null && e.change_percent !== undefined)
          .map((e, idx) => (
            <span
              key={idx}
              className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground"
              title={`${e.platform ?? ""} ${e.label}`}
            >
              {e.label}{" "}
              <b className={pctColor(e.change_percent!)}>{fmtPct(e.change_percent!)}</b>
            </span>
          ))}
        <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">
          {insight.confidence_band} confidence · {insight.confidence}%
        </span>
      </div>
    </div>
  );
}

function PlatformComparison({ rows }: { rows: MaCrossPlatformRow[] }) {
  return (
    <section className="space-y-2">
      <div className="text-sm font-semibold">Platform comparison</div>
      <p className="text-[11px] text-muted-foreground">
        Only metrics that mean the same thing across platforms are compared.
      </p>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.metric} className="rounded-md border p-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {row.label}
            </div>
            <div className="space-y-1.5">
              {row.entries.map((e) => {
                const isLeader = e.provider_slug === row.leader_provider;
                return (
                  <div
                    key={e.provider_slug}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="flex items-center gap-1.5">
                      {isLeader && <Flame className="h-3 w-3 text-emerald-500" />}
                      <span className={isLeader ? "font-medium" : ""}>
                        {e.platform}
                      </span>
                    </span>
                    <span className="flex items-center gap-2 tabular-nums">
                      {fmtValue(row.unit, e.value)}
                      <TrendIcon trend={e.trend} />
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "up")
    return <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />;
  if (trend === "down")
    return <TrendingDown className="h-3.5 w-3.5 text-red-500" />;
  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
}

// ---------------- formatting ----------------

function fmtPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${Math.round(v)}%`;
}

function pctColor(v: number): string {
  if (v > 0) return "text-emerald-600";
  if (v < 0) return "text-red-600";
  return "text-muted-foreground";
}

function fmtValue(unit: string, value: number): string {
  if (unit === "ratio") return `${(value * 100).toFixed(1)}%`;
  if (unit === "rating") return value.toFixed(1);
  return Math.round(value).toLocaleString();
}
