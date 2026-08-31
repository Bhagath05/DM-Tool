"use client";

/**
 * Phase 4 — the marketing-analytics signal inside the AI Coach.
 *
 * Renders the computed platform signal the advisor reasoned over: what
 * happened (📊), why it matters (⚠️), and the recommended next move (🎯).
 * Numbers come straight from the server-computed evidence — this component
 * never derives or alters a metric. Additive and self-contained; renders
 * nothing when there is no signal.
 */

import { AlertTriangle, ArrowRight, BarChart3, Target } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import type {
  MarketingAnalyticsSignal,
  MarketingSignalInsight,
} from "@/lib/intelligence-adapter";

export function MarketingSignalStrip({
  signal,
}: {
  signal: MarketingAnalyticsSignal | null | undefined;
}) {
  if (!signal) return null;

  // Empty / not-enough-data states: stay useful, never invent a trend.
  if (!signal.has_data || signal.insights.length === 0) {
    const message =
      signal.empty_message ??
      (signal.connected
        ? "Your account is connected — insights appear once we have enough data."
        : "Connect a marketing account to start receiving performance insights.");
    return (
      <Card data-testid="today-marketing-signal">
        <CardContent className="flex items-start gap-2 pt-5 text-sm">
          <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="flex-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Marketing signal
            </div>
            <p className="mt-1 text-muted-foreground">{message}</p>
            <SignalFooter />
          </div>
        </CardContent>
      </Card>
    );
  }

  const working = signal.insights.find((i) => i.severity === "good");
  const attention = signal.insights.find((i) => i.severity === "attention");
  const action = signal.insights[0];

  return (
    <Card data-testid="today-marketing-signal">
      <CardContent className="space-y-3 pt-5">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <BarChart3 className="h-3.5 w-3.5" />
          Marketing signal
        </div>
        <p className="text-sm font-medium leading-snug">{signal.headline}</p>

        {working && (
          <Row icon={<BarChart3 className="h-4 w-4 text-emerald-500" />} label="What's working">
            {working.observation}
          </Row>
        )}
        {attention && (
          <Row
            icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
            label="What this means"
          >
            {attention.interpretation}
          </Row>
        )}
        {action && <ActionRow insight={action} />}

        <SignalFooter />
      </CardContent>
    </Card>
  );
}

function Row({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-2">
      {icon}
      <div className="flex-1">
        <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <p className="mt-0.5 text-sm leading-snug">{children}</p>
      </div>
    </div>
  );
}

function ActionRow({ insight }: { insight: MarketingSignalInsight }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
      <Target className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div className="flex-1">
        <div className="text-[10px] font-medium uppercase tracking-wide text-primary">
          Recommended next move
        </div>
        <p className="mt-0.5 text-sm leading-snug">{insight.recommendation}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Expected: {insight.expected_result} · {insight.confidence_band} confidence
        </p>
      </div>
    </div>
  );
}

function SignalFooter() {
  return (
    <Link
      href="/analytics"
      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
    >
      View analytics <ArrowRight className="h-3 w-3" />
    </Link>
  );
}
