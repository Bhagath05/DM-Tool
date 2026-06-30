"use client";

/**
 * Competitor Watch — live AI analysis of the competitors the founder
 * listed in their business profile.
 *
 * Backed by GET /api/v1/competitors/analysis (the `competitors` module),
 * which reasons about each named competitor from the founder's industry +
 * audience and returns plain-language, action-oriented insight with the
 * Constitution recommendation contract. No crawl pipeline, no fabricated
 * stats — and no placeholder: when the profile has no competitors the
 * backend returns a 409 that we surface as an actionable empty state.
 */

import {
  ArrowRight,
  Eye,
  Lightbulb,
  Lock,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonTable } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  ApiError,
  api,
  type CompetitorAnalysisResponse,
  type CompetitorInsight,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: CompetitorAnalysisResponse }
  | { kind: "needs-competitors"; message: string }
  | { kind: "error"; message: string };

export function CompetitorWatch({ className }: { className?: string }) {
  const { can } = useTenant();
  const allowed = can("analytics.view");
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await api.competitors.analysis();
      setState({ kind: "ready", data });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setState({ kind: "needs-competitors", message: e.message });
      } else {
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? e.message
              : "We couldn't analyse your competitors just now.",
        });
      }
    }
  }, []);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  return (
    <section
      data-testid="competitor-watch"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Eye className="h-3 w-3" />
            Competitor watch
          </span>
        }
        heading="How to win against your competitors"
        description="An AI read on the rivals you're tracking — what they do well, where they're open, and the one move that beats them."
      />

      {!allowed ? (
        <EmptyState
          icon={Lock}
          title="Analytics access needed"
          description="Ask a workspace admin for the Analyst or Admin role to see competitor intelligence."
          data-testid="competitor-watch-locked"
        />
      ) : state.kind === "loading" ? (
        <div data-testid="competitor-watch-loading">
          <SkeletonTable rows={3} />
        </div>
      ) : state.kind === "needs-competitors" ? (
        <div
          data-testid="competitor-watch-empty"
          className="rounded-2xl border border-dashed border-border bg-card/60 p-6"
        >
          <EmptyState
            icon={ShieldAlert}
            title="Tell us who your competitors are"
            description={state.message}
            action={
              <Link
                href="/onboarding/profile"
                className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
              >
                Add competitors
                <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
        </div>
      ) : state.kind === "error" ? (
        <div
          data-testid="competitor-watch-error"
          className="flex flex-col items-start gap-3 rounded-2xl border border-bad-border bg-bad-soft/30 p-5"
        >
          <p className="text-sm text-bad-soft-foreground">{state.message}</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : (
        <CompetitorResults data={state.data} />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Results
// ---------------------------------------------------------------------

function CompetitorResults({ data }: { data: CompetitorAnalysisResponse }) {
  return (
    <div data-testid="competitor-watch-results" className="flex flex-col gap-4">
      <p className="text-sm leading-relaxed text-muted-foreground">
        {data.market_summary}
      </p>

      <ul className="flex flex-col gap-3" data-testid="competitor-watch-list">
        {data.competitors.map((c, i) => (
          <CompetitorCard key={`${c.name}-${i}`} insight={c} index={i} />
        ))}
      </ul>

      {/* Constitution AI recommendation contract */}
      <article
        data-testid="competitor-watch-recommendation"
        className="flex flex-col gap-2 rounded-2xl border border-ai-border bg-ai-soft/30 p-5"
      >
        <header className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-ai" />
          <h3 className="text-sm font-semibold text-foreground">
            Your highest-leverage move
          </h3>
          <ConfidencePill value={data.confidence} className="ml-auto" />
        </header>
        <p className="text-sm font-medium text-foreground">
          {data.recommendation}
        </p>
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Why:</span>{" "}
          {data.reason}
        </p>
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">
            What to expect:
          </span>{" "}
          {data.expected_result}
        </p>
      </article>
    </div>
  );
}

function CompetitorCard({
  insight,
  index,
}: {
  insight: CompetitorInsight;
  index: number;
}) {
  return (
    <li>
      <article
        data-testid={`competitor-insight-${index}`}
        className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4"
      >
        <header className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">
            {insight.name}
          </h3>
          <ConfidencePill value={insight.confidence} className="ml-auto" />
        </header>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {insight.positioning}
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <BulletGroup
            tone="good"
            label="Where they're strong"
            items={insight.strengths}
          />
          <BulletGroup
            tone="watch"
            label="Openings for you"
            items={insight.gaps}
          />
        </div>

        {insight.content_angles.length > 0 && (
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground/80">
              They lean on:
            </span>{" "}
            {insight.content_angles.join(" · ")}
          </p>
        )}

        <div className="flex items-start gap-2 rounded-lg bg-muted/50 p-3">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-ai" />
          <p className="text-xs leading-relaxed text-foreground">
            <span className="font-semibold">Your move: </span>
            {insight.your_move}
          </p>
        </div>
      </article>
    </li>
  );
}

function BulletGroup({
  tone,
  label,
  items,
}: {
  tone: "good" | "watch";
  label: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <ul className="flex flex-col gap-1">
        {items.map((it, i) => (
          <li
            key={i}
            className="flex items-start gap-1.5 text-xs text-foreground/90"
          >
            <span
              className={cn(
                "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                tone === "good" ? "bg-good" : "bg-watch",
              )}
              aria-hidden
            />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConfidencePill({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const { tone, label } = confidenceBand(value);
  return (
    <StatusPill tone={tone} size="sm" dot className={className}>
      {label} · {value}%
    </StatusPill>
  );
}

function confidenceBand(v: number): {
  tone: "good" | "watch" | "neutral";
  label: string;
} {
  if (v >= 80) return { tone: "good", label: "High confidence" };
  if (v >= 60) return { tone: "watch", label: "Medium confidence" };
  if (v >= 40) return { tone: "watch", label: "Worth testing" };
  return { tone: "neutral", label: "Exploratory" };
}
