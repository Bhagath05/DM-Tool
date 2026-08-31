"use client";

/**
 * Phase 5 — Top Performing Content.
 *
 * Reads /marketing-analytics/content and shows which specific posts performed
 * best, how formats compare, and an evidence-backed "repeat this" note. All
 * numbers are server-computed; this component never derives a metric. Additive
 * to the analytics page; honest empty state when there isn't enough content.
 */

import { ArrowRight, Sparkles, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type MaContentItem,
  type MaContentReport,
  type MaInsight,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: MaContentReport };

export function TopContent() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const report = await api.marketingAnalytics.content();
      setState({ kind: "ready", report });
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof Error ? e.message : "Couldn't read content performance.",
      });
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
            <Trophy className="h-4 w-4" /> Top performing content
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Reading your content performance…
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top performing content</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{state.message}</p>
          <Button onClick={() => void load()}>Try again</Button>
        </CardContent>
      </Card>
    );
  }

  const { report } = state;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Trophy className="h-4 w-4 text-amber-500" /> Top performing content
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {!report.has_data || report.top.length === 0 ? (
          <EmptyState message={report.sufficiency.message} />
        ) : (
          <>
            {report.insights.length > 0 && (
              <RepeatThis insight={report.insights[0]} />
            )}
            <ol className="space-y-2">
              {report.top.map((item, i) => (
                <ContentRow key={item.asset_id} rank={i + 1} item={item} />
              ))}
            </ol>
            {report.format_comparison.length > 1 && (
              <FormatCompare rows={report.format_comparison} />
            )}
            {report.recommendation_effectiveness?.has_data && (
              <RecommendationImpact
                text={report.recommendation_effectiveness.summary}
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center">
      <p className="text-sm font-medium">Not enough content data yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {message} Publish and connect your accounts — once a few posts have
        performance data, your best content shows up here.
      </p>
    </div>
  );
}

function RepeatThis({ insight }: { insight: MaInsight }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div className="flex-1">
        <p className="text-sm font-medium leading-snug">{insight.observation}</p>
        <p className="mt-0.5 flex items-center gap-1 text-sm">
          <ArrowRight className="h-3.5 w-3.5 text-primary" />
          {insight.recommendation}
        </p>
      </div>
    </div>
  );
}

function ContentRow({ rank, item }: { rank: number; item: MaContentItem }) {
  const title = item.caption?.trim() || `${item.asset_type} post`;
  return (
    <li className="flex items-center gap-3 rounded-md border px-3 py-2">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{title}</p>
        <p className="text-[11px] text-muted-foreground">
          {item.platform_label} · {item.asset_type}
          {item.above_median && (
            <span className="ml-1 text-emerald-600">· above your median</span>
          )}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-sm font-semibold tabular-nums">
          {(item.engagement_rate * 100).toFixed(1)}%
        </div>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          engagement
        </div>
      </div>
    </li>
  );
}

function RecommendationImpact({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-emerald-600">
        Recommendation impact
      </div>
      <p className="mt-0.5 text-sm">{text}</p>
    </div>
  );
}

function FormatCompare({
  rows,
}: {
  rows: MaContentReport["format_comparison"];
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Format comparison
      </div>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div
            key={r.asset_type}
            className="flex items-center justify-between text-sm"
          >
            <span>
              {r.asset_type}{" "}
              <span className="text-[11px] text-muted-foreground">
                ({r.count})
              </span>
            </span>
            <span className="tabular-nums">
              {(r.median_engagement_rate * 100).toFixed(1)}% median
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
