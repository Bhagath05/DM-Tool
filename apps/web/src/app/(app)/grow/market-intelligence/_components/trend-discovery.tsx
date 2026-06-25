"use client";

/**
 * Phase 10.3c — Trend Discovery.
 *
 *   "Payroll Automation"
 *   Momentum: +42% · Competition: Medium
 *   Recommended: Carousel · LinkedIn
 *   [ Generate Content → ]
 *
 * Uses the existing `api.trends.get()` — Phase 1B trend engine. We
 * surface the top trending topics with action shaping; deep-link into
 * the content studio with prefill params.
 *
 * NOTE: the backend's TrendingTopic carries `recommended_action`,
 * `expected_result`, `confidence`, and `reason` — the same Constitution
 * contract every action card honours. The legacy `relevance_score`
 * is intentionally NOT shown (it leaks raw scoring; founders see
 * the confidence band instead).
 */

import { ArrowRight, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, type TrendingTopic } from "@/lib/api";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty"; message: string }
  | { kind: "ready"; topics: TrendingTopic[] };

const MAX_TOPICS = 4;

export function TrendDiscovery({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report = await api.trends.get();
      if (!report) {
        setState({
          kind: "empty",
          message: "Your trend report will appear here on next refresh.",
        });
        return;
      }
      const topics = report.analysis?.trending_topics ?? [];
      if (topics.length === 0) {
        setState({
          kind: "empty",
          message:
            report.status === "pending"
              ? "Trends are still being analysed. Refresh in a minute."
              : "No trending topics surfaced for your industry yet.",
        });
        return;
      }
      // Sort by confidence DESC (nulls last). Stable secondary sort by
      // legacy relevance_score so output is deterministic when both
      // are absent.
      const ranked = [...topics].sort((a, b) => {
        const ac = a.confidence ?? -1;
        const bc = b.confidence ?? -1;
        if (bc !== ac) return bc - ac;
        return (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
      });
      setState({ kind: "ready", topics: ranked.slice(0, MAX_TOPICS) });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load trend report. Refresh to retry.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="trend-discovery"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <div className="flex items-end justify-between">
        <SectionHeading
          eyebrow={
            <span className="inline-flex items-center gap-1.5">
              <TrendingUp className="h-3 w-3" />
              Trend discovery
            </span>
          }
          heading="What your audience is asking about"
          description="Topics gaining momentum in your industry — and the format that wins on each."
        />
        <Link
          href={"/trends" as never}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          data-testid="trend-discovery-see-all"
        >
          See full report →
        </Link>
      </div>

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Trend report unavailable"
          description={state.message}
          data-testid="trend-discovery-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={TrendingUp}
          title="No trends yet"
          description={state.message}
          data-testid="trend-discovery-empty"
        />
      )}

      {state.kind === "ready" && (
        <ul
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          data-testid="trend-discovery-list"
        >
          {state.topics.map((t, i) => (
            <TrendCard key={`${i}-${t.topic}`} topic={t} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Trend card
// ---------------------------------------------------------------------

function TrendCard({ topic }: { topic: TrendingTopic }) {
  const ctaHref = trendCtaHref(topic);
  const ctaLabel = topic.recommended_action ?? "Generate content";
  const hasConfidence = typeof topic.confidence === "number";

  return (
    <li>
      <article className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-4">
        <header className="flex flex-wrap items-center gap-2">
          {hasConfidence && (
            <StatusPill tone="ai" size="sm" dot>
              {topic.confidence}% confidence
            </StatusPill>
          )}
          <StatusPill tone="muted" size="sm">
            Trending
          </StatusPill>
        </header>

        <div className="flex flex-col gap-1.5">
          <h3 className="text-sm font-semibold text-foreground">
            {topic.topic}
          </h3>
          <p className="text-xs text-muted-foreground">
            {topic.why_it_matters}
          </p>
        </div>

        {topic.expected_result && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Expected: </span>
            {topic.expected_result}
          </p>
        )}

        {topic.suggested_angles?.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Suggested angles">
            {topic.suggested_angles.slice(0, 3).map((a, i) => (
              <li
                key={i}
                className="rounded-md bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
              >
                {a}
              </li>
            ))}
          </ul>
        )}

        <Link
          href={ctaHref as never}
          data-testid={`trend-cta-${slugify(topic.topic)}`}
          className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
        >
          {ctaLabel}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </article>
    </li>
  );
}

// ---------------------------------------------------------------------
//  CTA target
// ---------------------------------------------------------------------

function trendCtaHref(topic: TrendingTopic): string {
  // Send the founder into the social-posts studio with the topic
  // pre-filled. Studios honour the `topic` + `from` params per the
  // Phase 3.3 prefill convention.
  const qs = new URLSearchParams();
  qs.set("topic", topic.topic);
  qs.set("from", "market-intel-trends");
  return `/create/social-posts?${qs}`;
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 40);
}
