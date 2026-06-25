"use client";

/**
 * Phase 10.0 — Industry Benchmark card.
 *
 * Per the modifications brief: when benchmark data is unavailable
 * we render "Benchmark data coming soon" and DO NOT fabricate values.
 * No backend currently produces benchmark numbers, so this is a
 * coming-soon empty state by design — honest by construction.
 *
 * When the benchmark service ships in a future phase, the same
 * component takes `{ yourCpl, industryAvg, currency }` props and
 * renders the comparative view.
 */

import { LineChart, ScaleIcon, Sparkles } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export interface IndustryBenchmarkProps {
  /**
   * Optional pre-computed comparison. When omitted, the card renders
   * an honest "coming soon" empty state. Never call this with
   * fabricated values.
   */
  data?: {
    yourCpl: number;
    industryAvg: number;
    currency: string;
  };
  className?: string;
}

export function IndustryBenchmark({ data, className }: IndustryBenchmarkProps) {
  return (
    <section
      data-testid="industry-benchmark"
      className={cn("flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <ScaleIcon className="h-3 w-3" />
            How you compare
          </span>
        }
        heading="Industry Benchmark"
        description="See how your cost per lead stacks up against businesses like yours."
      />

      {data ? <Comparison {...data} /> : <ComingSoon />}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Coming-soon variant (default — no backend data yet)
// ---------------------------------------------------------------------

function ComingSoon() {
  return (
    <EmptyState
      icon={LineChart}
      variant="ai"
      title="Benchmark data coming soon"
      description="We're building anonymised industry benchmarks so you can see how your cost per lead compares to similar businesses. Available in a future release."
      hint="No benchmark values are ever fabricated."
      data-testid="industry-benchmark-coming-soon"
    />
  );
}

// ---------------------------------------------------------------------
//  Live-data variant (renders when caller passes `data`)
// ---------------------------------------------------------------------

function Comparison({
  yourCpl,
  industryAvg,
  currency,
}: NonNullable<IndustryBenchmarkProps["data"]>) {
  const ratio = industryAvg > 0 ? yourCpl / industryAvg : 1;
  const isBetter = ratio < 1;
  const diffPct = Math.round(Math.abs(ratio - 1) * 100);

  return (
    <div
      data-testid="industry-benchmark-data"
      className="grid grid-cols-1 gap-4 rounded-2xl border border-border/70 bg-card p-6 shadow-sm md:grid-cols-3"
    >
      <BenchmarkTile
        label="Your CPL"
        value={`${currency} ${Math.round(yourCpl).toLocaleString()}`}
        accent="default"
      />
      <BenchmarkTile
        label="Industry average"
        value={`${currency} ${Math.round(industryAvg).toLocaleString()}`}
        accent="muted"
      />
      <BenchmarkTile
        label="Performance"
        value={`${diffPct}% ${isBetter ? "better" : "worse"}`}
        accent={isBetter ? "good" : "watch"}
        pill={
          <StatusPill tone={isBetter ? "good" : "watch"} size="sm" dot>
            {isBetter ? "Above average" : "Below average"}
          </StatusPill>
        }
      />
    </div>
  );
}

function BenchmarkTile({
  label,
  value,
  accent,
  pill,
}: {
  label: string;
  value: string;
  accent: "default" | "muted" | "good" | "watch";
  pill?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <div
        className={cn(
          "text-2xl font-semibold tracking-tight tabular",
          accent === "muted" && "text-muted-foreground",
          accent === "good" && "text-good-soft-foreground",
          accent === "watch" && "text-watch-soft-foreground",
        )}
      >
        {value}
      </div>
      {pill}
    </div>
  );
}
