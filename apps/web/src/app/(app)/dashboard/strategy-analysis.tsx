"use client";

import {
  AlertCircle,
  ArrowRight,
  Circle,
  Compass,
  Eye,
  Flag,
  Radio,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BusinessAnalysis } from "@/lib/api";

/**
 * Phase 2.1 — Intelligence Engine v2 surface.
 *
 * A consultant-style deliverable layout. Hidden when the analysis predates
 * v2 (profile-loader falls back to the v1 layout for legacy rows).
 *
 * Layout philosophy: every block answers a different question the founder
 * cares about. No "audience demographics 22-30 yo female" walls — concrete
 * gaps, ranked channels, phased path.
 */
export function StrategyAnalysis({ analysis }: { analysis: BusinessAnalysis }) {
  const {
    current_state,
    desired_future_state,
    gap_analysis,
    growth_bottlenecks,
    competitor_signals,
    realistic_growth_path,
    recommended_acquisition_channels,
  } = analysis;

  return (
    <div className="space-y-4">
      {/* Hero: current → desired */}
      {(current_state || desired_future_state) && (
        <Card>
          <CardContent className="grid gap-4 pt-6 sm:grid-cols-[1fr_auto_1fr]">
            <StateBlock
              icon={Compass}
              label="Where you are today"
              body={current_state}
              tone="muted"
            />
            <div className="hidden items-center justify-center sm:flex">
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </div>
            <StateBlock
              icon={Target}
              label="Where you're going"
              body={desired_future_state}
              tone="primary"
            />
          </CardContent>
        </Card>
      )}

      {/* Gap analysis */}
      {gap_analysis && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              The biggest gaps
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed">
            {gap_analysis}
          </CardContent>
        </Card>
      )}

      {/* Two-col: bottlenecks + competitor signals */}
      {(growth_bottlenecks?.length || competitor_signals?.length) && (
        <div className="grid gap-4 md:grid-cols-2">
          {growth_bottlenecks?.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Eye className="h-4 w-4 text-rose-500" />
                  What&apos;s holding you back
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DotList items={growth_bottlenecks} tone="rose" />
              </CardContent>
            </Card>
          ) : null}
          {competitor_signals?.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Radio className="h-4 w-4 text-sky-500" />
                  What competitors are doing
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DotList items={competitor_signals} tone="sky" />
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}

      {/* Growth path */}
      {realistic_growth_path?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Flag className="h-4 w-4 text-primary" />
              Your growth path
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Calibrated to your current traction and budget. Honest, not
              optimistic.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            {realistic_growth_path.map((m, i) => (
              <MilestoneRow
                key={i}
                index={i + 1}
                phase={m.phase}
                goal={m.goal}
                actions={m.actions}
                metric={m.success_metric}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {/* Recommended channels */}
      {recommended_acquisition_channels?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-emerald-600" />
              Where to put your effort first
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {recommended_acquisition_channels.map((c, i) => (
              <ChannelRow
                key={i}
                rank={i + 1}
                channel={c.channel}
                whyNow={c.why_now}
                outcome={c.expected_outcome}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {/* Strategy summary (v1 prose — still useful as the closing paragraph) */}
      {analysis.strategy_recommendation && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              In summary
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-relaxed text-muted-foreground">
            {analysis.strategy_recommendation}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------- subcomponents ----------------

function StateBlock({
  icon: Icon,
  label,
  body,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  body: string | null | undefined;
  tone: "muted" | "primary";
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon
          className={
            tone === "primary"
              ? "h-4 w-4 text-primary"
              : "h-4 w-4 text-muted-foreground"
          }
        />
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
      </div>
      <p
        className={
          tone === "primary"
            ? "text-sm leading-relaxed text-foreground"
            : "text-sm leading-relaxed text-muted-foreground"
        }
      >
        {body || "—"}
      </p>
    </div>
  );
}

function DotList({
  items,
  tone,
}: {
  items: string[];
  tone: "rose" | "sky";
}) {
  const dotClass =
    tone === "rose"
      ? "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500"
      : "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-500";
  return (
    <ul className="space-y-2 text-sm">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 leading-relaxed">
          <span className={dotClass} />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function MilestoneRow({
  index,
  phase,
  goal,
  actions,
  metric,
}: {
  index: number;
  phase: string;
  goal: string;
  actions: string[];
  metric: string;
}) {
  return (
    <div className="grid gap-3 rounded-md border bg-card p-3 sm:grid-cols-[40px_1fr]">
      <div className="flex flex-col items-center">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {index}
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {phase}
          </span>
          <span className="text-sm font-semibold leading-snug">{goal}</span>
        </div>
        <ul className="space-y-1 text-xs text-muted-foreground">
          {actions.map((a, i) => (
            <li key={i} className="flex gap-2">
              <Circle className="mt-1 h-2 w-2 shrink-0 fill-muted-foreground/30 text-muted-foreground/30" />
              <span>{a}</span>
            </li>
          ))}
        </ul>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Watch · {metric}
        </div>
      </div>
    </div>
  );
}

function ChannelRow({
  rank,
  channel,
  whyNow,
  outcome,
}: {
  rank: number;
  channel: string;
  whyNow: string;
  outcome: string;
}) {
  return (
    <div className="grid gap-3 rounded-md border bg-card p-3 sm:grid-cols-[40px_1fr]">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        #{rank}
      </div>
      <div className="space-y-1.5">
        <div className="text-sm font-semibold">{channel}</div>
        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Why now: </span>
          {whyNow}
        </div>
        <div className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">Expect: </span>
          {outcome}
        </div>
      </div>
    </div>
  );
}
