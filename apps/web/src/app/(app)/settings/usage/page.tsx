"use client";

/**
 * Phase 10.1 — Settings · Usage & Limits.
 *
 * Three columns of metrics, all sourced from REAL endpoints we
 * already have. No fabricated numbers.
 *
 *   - CSV ingest         (rows + creatives)         from /performance/overview
 *   - AI recommendations (open diagnostics)         from /performance/overview
 *   - Coach actions      (this week's plan size)    from /coach/weekly
 *
 * On Early Access there are no hard caps — the page says so
 * explicitly. The progress bars use a "soft target" anchor (e.g.
 * 200 rows, 10 recommendations) so the founder gets a sense of
 * scale, not a fake plan limit.
 *
 * When the metered backend ships, the soft targets get replaced
 * with the plan's real caps; the UI stays the same shape.
 */

import {
  Bot,
  CloudUpload,
  Gauge,
  Loader2,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type PerformanceOverview,
  type WeeklyPlan,
} from "@/lib/api";

export const dynamic = "force-dynamic";

interface UsageState {
  perf: PerformanceOverview | null;
  weekly: WeeklyPlan | null;
  loading: boolean;
  error: string | null;
}

interface UsageMetric {
  key: string;
  icon: typeof Sparkles;
  label: string;
  blurb: string;
  value: number;
  unit: string;
  /** Soft target — used to render the progress bar's scale until
   *  metered plan limits ship. */
  softTarget: number;
}

export default function UsageSettingsPage() {
  const [state, setState] = useState<UsageState>({
    perf: null,
    weekly: null,
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [perf, weekly] = await Promise.all([
        api.performance.overview().catch(() => null),
        api.coach.weekly().catch(() => null),
      ]);
      setState({ perf, weekly, loading: false, error: null });
    } catch (err) {
      setState({
        perf: null,
        weekly: null,
        loading: false,
        error: err instanceof ApiError ? err.message : "Couldn't load usage",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const metrics: UsageMetric[] = [
    {
      key: "rows",
      icon: CloudUpload,
      label: "CSV rows ingested",
      blurb:
        "Performance rows the engine is reasoning over right now. More rows = sharper diagnostics.",
      value: state.perf?.rows_ingested ?? 0,
      unit: state.perf?.rows_ingested === 1 ? "row" : "rows",
      softTarget: 200,
    },
    {
      key: "creatives",
      icon: Sparkles,
      label: "Creatives tracked",
      blurb:
        "Distinct ad creatives we've rolled up across all your uploads. Each tagged creative feeds the Winning Formula.",
      value: state.perf?.creatives_tracked ?? 0,
      unit:
        state.perf?.creatives_tracked === 1 ? "creative" : "creatives",
      softTarget: 25,
    },
    {
      key: "diagnostics",
      icon: Bot,
      label: "Open AI recommendations",
      blurb:
        "Constitution-shaped recommendations live on your dashboard right now.",
      value: state.perf?.diagnostics?.length ?? 0,
      unit:
        state.perf?.diagnostics?.length === 1
          ? "recommendation"
          : "recommendations",
      softTarget: 7,
    },
    {
      key: "actions",
      icon: Wand2,
      label: "Coach actions this week",
      blurb:
        "Actions the AI Coach has lined up. Three is the focus number; more is fine if you've got the time.",
      value: state.weekly?.actions?.length ?? 0,
      unit: state.weekly?.actions?.length === 1 ? "action" : "actions",
      softTarget: 5,
    },
  ];

  return (
    <div className="flex flex-col gap-8" data-testid="settings-usage">
      <SectionHeading
        eyebrow="Settings · Usage & Limits"
        heading="How you're using DM Tool"
        description="Real-time counts from your workspace. Early Access has no hard caps — these targets just give you a sense of scale."
        size="lg"
        action={
          <StatusPill tone="ai" size="md" dot icon={Gauge}>
            Early Access · no hard limits
          </StatusPill>
        }
      />

      {state.error && (
        <div
          role="alert"
          data-testid="usage-error"
          className="rounded-xl border border-bad-border bg-bad-soft px-4 py-3 text-sm text-bad-soft-foreground"
        >
          {state.error}
        </div>
      )}

      <section
        data-testid="usage-grid"
        className="grid grid-cols-1 gap-4 md:grid-cols-2"
      >
        {state.loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <UsageSkeleton key={i} />
            ))
          : metrics.map((m) => <UsageTile key={m.key} metric={m} />)}
      </section>

      {/* Plan note — honest about what "no limits" actually means */}
      <article className="card-surface-ai relative overflow-hidden p-6 sm:p-7">
        <div className="flex flex-col gap-2">
          <span className="text-meta text-ai-soft-foreground">
            <Sparkles className="mr-1 inline h-3 w-3" />
            What "no limits" means today
          </span>
          <h3 className="text-card-title font-semibold">
            We won't gate you on rows, creatives, or recommendations.
          </h3>
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            We do throttle a few backend operations to keep costs sane:
            uploads are capped at 2 MB per file, the AI Coach plan refreshes
            once every 12 hours by default, and individual diagnostics run on
            a min-sample gate (500 impressions, ~1k spend, 1 conversion) before
            we'll surface them. None of these caps surface as paywalls — they
            exist to protect signal quality.
          </p>
        </div>
      </article>

      {/* Plan & history (placeholder — billing page is the home for this) */}
      <article className="card-surface flex flex-col items-start justify-between gap-3 p-6 sm:flex-row sm:items-center">
        <div className="flex flex-col gap-1">
          <h4 className="text-card-title font-semibold">
            See usage by month?
          </h4>
          <p className="text-sm text-muted-foreground">
            Historical usage graphs and per-month rollups land alongside
            metered billing in a future release.
          </p>
        </div>
        <StatusPill tone="muted" size="md" icon={Loader2}>
          Coming soon
        </StatusPill>
      </article>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Per-metric tile
// ---------------------------------------------------------------------

function UsageTile({ metric }: { metric: UsageMetric }) {
  const Icon = metric.icon;
  const pct = Math.min(100, Math.round((metric.value / metric.softTarget) * 100));
  return (
    <article
      data-testid={`usage-tile-${metric.key}`}
      className="card-surface card-surface-hover flex flex-col gap-4 p-6"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-muted text-foreground/80"
          >
            <Icon className="h-4 w-4" />
          </span>
          <div className="flex flex-col">
            <span className="text-meta">{metric.label}</span>
            <div className="flex items-baseline gap-2 tabular">
              <span
                data-testid={`usage-tile-${metric.key}-value`}
                className="text-section font-semibold tracking-tight"
              >
                {metric.value.toLocaleString()}
              </span>
              <span className="text-sm text-muted-foreground">
                {metric.unit}
              </span>
            </div>
          </div>
        </div>
        <StatusPill tone="muted" size="sm">
          {pct}% of soft target
        </StatusPill>
      </header>
      <ConfidenceBar value={pct} size="md" hideLabel />
      <p className="text-sm leading-relaxed text-muted-foreground">
        {metric.blurb}
      </p>
    </article>
  );
}

function UsageSkeleton() {
  return (
    <div className="card-surface flex flex-col gap-4 p-6">
      <div className="flex items-center gap-3">
        <Skeleton className="h-10 w-10 rounded-xl" />
        <div className="flex flex-1 flex-col gap-1.5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-20" />
        </div>
      </div>
      <Skeleton className="h-1.5 w-full rounded-full" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
