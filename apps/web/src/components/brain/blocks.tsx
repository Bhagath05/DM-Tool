"use client";

/**
 * Marketing Brain — generative UI primitives.
 *
 * Reusable, presentational building blocks the agent's structured responses
 * render through, so every answer reads as one consistent "marketing operating
 * system" experience instead of a wall of text. They render ONLY the data passed
 * in — they never fabricate metrics or results. Built on the existing design
 * system (tokens, ConfidenceBar, StatusPill); no separate visual language.
 *
 * Accessibility: status is always conveyed by text/icon + shape, never color
 * alone; severity/trend carry an explicit label and an aria-hidden glyph.
 */

import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  FlaskConical,
  Lightbulb,
  Minus,
  ScrollText,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export type Severity = "high" | "medium" | "low";
export type Trend = "up" | "down" | "flat";

const SEVERITY_TONE: Record<Severity, PillTone> = {
  high: "bad",
  medium: "watch",
  low: "muted",
};

// ---------------------------------------------------------------------
//  GenBlock — the shared titled container every structured block uses.
// ---------------------------------------------------------------------
export function GenBlock({
  eyebrow,
  icon: Icon,
  accent = false,
  children,
  "data-testid": testId,
}: {
  eyebrow: string;
  icon?: React.ComponentType<{ className?: string }>;
  accent?: boolean;
  children: ReactNode;
  "data-testid"?: string;
}) {
  return (
    <section
      data-testid={testId}
      className={cn(
        "rounded-xl border bg-card p-4",
        accent ? "border-ai-border bg-ai-soft/40" : "border-border",
      )}
    >
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {Icon && <Icon className={cn("h-3.5 w-3.5", accent && "text-ai")} aria-hidden />}
        {eyebrow}
      </div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------
//  MetricCard + MetricDeltaRow — numbers with trend, tabular figures.
// ---------------------------------------------------------------------
function TrendGlyph({ trend }: { trend: Trend }) {
  const Icon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;
  return <Icon className="h-3.5 w-3.5" aria-hidden />;
}

function trendTone(trend: Trend, goodWhen: Trend): string {
  if (trend === "flat") return "text-muted-foreground";
  return trend === goodWhen ? "text-good" : "text-bad";
}

export function MetricCard({
  label,
  value,
  delta,
  trend = "flat",
  goodWhen = "up",
  hint,
}: {
  label: string;
  value: string;
  delta?: string;
  trend?: Trend;
  goodWhen?: Trend;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/40 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="tabular mt-1 text-2xl font-semibold leading-none">{value}</p>
      {delta && (
        <p className={cn("mt-1.5 inline-flex items-center gap-1 text-xs font-medium", trendTone(trend, goodWhen))}>
          <TrendGlyph trend={trend} />
          <span className="tabular">{delta}</span>
          <span className="sr-only">
            {trend === "up" ? "up" : trend === "down" ? "down" : "unchanged"}
          </span>
        </p>
      )}
      {hint && <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function MetricDeltaRow({
  label,
  delta,
  trend,
  goodWhen = "up",
}: {
  label: string;
  delta: string;
  trend: Trend;
  goodWhen?: Trend;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("inline-flex items-center gap-1 font-medium", trendTone(trend, goodWhen))}>
        <TrendGlyph trend={trend} />
        <span className="tabular">{delta}</span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------
//  FactorList — weighted factors with accessible severity labels.
// ---------------------------------------------------------------------
export function FactorList({
  factors,
}: {
  factors: { label: string; severity: Severity; note?: string }[];
}) {
  return (
    <ul className="flex flex-col gap-1.5">
      {factors.map((f) => (
        <li key={f.label} className="flex items-center justify-between gap-3 text-sm">
          <span className="min-w-0">
            <span className="text-foreground">{f.label}</span>
            {f.note && <span className="ml-2 text-xs text-muted-foreground">{f.note}</span>}
          </span>
          <StatusPill tone={SEVERITY_TONE[f.severity]}>{f.severity.toUpperCase()}</StatusPill>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------
//  DiagnosisBlock — "why did X happen" with factors.
// ---------------------------------------------------------------------
export function DiagnosisBlock({
  summary,
  factors,
}: {
  summary: string;
  factors?: { label: string; severity: Severity; note?: string }[];
}) {
  return (
    <GenBlock eyebrow="Diagnosis" icon={Stethoscope} data-testid="brain-diagnosis">
      <p className="text-sm leading-relaxed">{summary}</p>
      {factors && factors.length > 0 && (
        <div className="mt-3 border-t border-border pt-3">
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Likely factors</p>
          <FactorList factors={factors} />
        </div>
      )}
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  InsightBlock — key observations the Brain actually saw.
// ---------------------------------------------------------------------
export function InsightBlock({ observations }: { observations: string[] }) {
  if (observations.length === 0) return null;
  return (
    <GenBlock eyebrow="What the Brain saw" icon={Lightbulb} data-testid="brain-insights">
      <ul className="flex flex-col gap-1.5">
        {observations.map((o, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <span aria-hidden className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ai" />
            <span>{o}</span>
          </li>
        ))}
      </ul>
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  EvidenceBlock — the sources behind the answer.
// ---------------------------------------------------------------------
export function EvidenceBlock({
  sources,
  toolsConsulted,
}: {
  sources: { label: string; source?: string | null; confidence?: number | null; status?: string | null }[];
  toolsConsulted?: string[];
}) {
  const hasSources = sources.length > 0;
  const hasTools = (toolsConsulted?.length ?? 0) > 0;
  if (!hasSources && !hasTools) return null;
  return (
    <GenBlock eyebrow="Evidence" icon={ScrollText} data-testid="brain-evidence">
      {hasTools && (
        <p className="mb-2 text-xs text-muted-foreground">
          Consulted:{" "}
          <span className="text-foreground">{toolsConsulted!.join(", ")}</span>
        </p>
      )}
      <ul className="flex flex-col divide-y divide-border">
        {sources.map((s, i) => (
          <li key={`${s.label}-${i}`} className="flex items-start justify-between gap-3 py-1.5">
            <span className="min-w-0">
              <span className="block truncate text-sm text-foreground">{s.label}</span>
              {s.source && <span className="block truncate text-xs text-muted-foreground">{s.source}</span>}
            </span>
            {typeof s.confidence === "number" && (
              <span className="tabular shrink-0 text-xs text-muted-foreground">{s.confidence}%</span>
            )}
          </li>
        ))}
      </ul>
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  RecommendationBlock — a next step. Distinct from a consequential action.
// ---------------------------------------------------------------------
export function RecommendationBlock({
  recommendation,
  reason,
  expectedResult,
  confidence,
  action,
}: {
  recommendation: string;
  reason?: string;
  expectedResult?: string;
  confidence?: number;
  action?: { label: string; href: string };
}) {
  return (
    <GenBlock eyebrow="Recommended next step" icon={ArrowRight} accent data-testid="brain-recommendation">
      <p className="text-sm font-medium">{recommendation}</p>
      {reason && <p className="mt-1 text-sm text-muted-foreground">{reason}</p>}
      {expectedResult && (
        <p className="mt-1 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Expected:</span> {expectedResult}
        </p>
      )}
      {typeof confidence === "number" && (
        <div className="mt-2 max-w-xs">
          <ConfidenceBar value={confidence} size="sm" />
        </div>
      )}
      {action && (
        <Link
          href={action.href as never}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-ai px-3 py-1.5 text-xs font-medium text-ai-foreground transition-opacity hover:opacity-90"
        >
          {action.label}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  ExperimentBlock — presentational; renders only passed-in experiment data.
// ---------------------------------------------------------------------
export function ExperimentBlock({
  hypothesis,
  variants,
  metric,
  action,
}: {
  hypothesis: string;
  variants?: string[];
  metric?: string;
  action?: { label: string; href: string };
}) {
  return (
    <GenBlock eyebrow="Experiment" icon={FlaskConical} data-testid="brain-experiment">
      <p className="text-sm">{hypothesis}</p>
      {variants && variants.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {variants.map((v) => (
            <span key={v} className="rounded-md border border-border bg-background/40 px-2 py-0.5 text-xs">
              {v}
            </span>
          ))}
        </div>
      )}
      {metric && (
        <p className="mt-2 text-xs text-muted-foreground">
          Success metric: <span className="text-foreground">{metric}</span>
        </p>
      )}
      {action && (
        <Link
          href={action.href as never}
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-ai underline-offset-4 hover:underline"
        >
          {action.label}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  ApprovalRequestBlock — a PROPOSED consequential action. Never executes.
// ---------------------------------------------------------------------
export function ApprovalRequestBlock({
  tool,
  explanation,
  reason,
  expectedEffect,
  status = "pending",
  href = "/ai/approvals",
}: {
  tool: string;
  explanation?: string;
  reason?: string | null;
  expectedEffect?: string | null;
  status?: string;
  href?: string;
}) {
  return (
    <GenBlock eyebrow="Approval required" icon={ShieldCheck} accent data-testid="brain-approval">
      <div className="flex items-center gap-2 text-[11px]">
        <span className="rounded-md bg-ai-soft px-1.5 py-0.5 font-medium text-ai-soft-foreground">
          AI proposed this
        </span>
        <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden />
        <span className="rounded-md border border-border px-1.5 py-0.5 font-medium text-foreground">
          A human must approve it
        </span>
      </div>
      <p className="mt-2 text-sm font-medium">{explanation ?? `Prepared "${tool}".`}</p>
      {reason && <p className="mt-1 text-sm text-muted-foreground">{reason}</p>}
      {expectedEffect && (
        <p className="mt-1 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Expected effect:</span> {expectedEffect}
        </p>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Nothing has run. Status: <span className="font-medium text-foreground">{status}</span>.
      </p>
      <Link
        href={href as never}
        className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-ai-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-ai-soft"
      >
        Review &amp; decide
        <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  InsufficientEvidenceBlock — the honest "not enough to conclude" state.
// ---------------------------------------------------------------------
export function InsufficientEvidenceBlock({ detail }: { detail?: string }) {
  return (
    <GenBlock eyebrow="Insufficient evidence" icon={AlertTriangle} data-testid="brain-insufficient">
      <p className="text-sm">
        I don&apos;t have enough reliable data to answer this confidently yet — so I won&apos;t guess.
      </p>
      {detail && <p className="mt-1 text-sm text-muted-foreground">{detail}</p>}
    </GenBlock>
  );
}

// ---------------------------------------------------------------------
//  DataTable — compact semantic table, tabular figures.
// ---------------------------------------------------------------------
export function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border" data-testid="brain-table">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 text-xs font-semibold text-muted-foreground">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="border-b border-border last:border-0">
              {r.map((cell, ci) => (
                <td key={ci} className={cn("px-3 py-2", typeof cell === "number" && "tabular text-right")}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Timeline — ordered activity, presentational.
// ---------------------------------------------------------------------
export function Timeline({
  items,
}: {
  items: { label: string; when?: string; tone?: PillTone }[];
}) {
  return (
    <ol className="flex flex-col" data-testid="brain-timeline">
      {items.map((it, i) => (
        <li key={i} className="flex gap-3 pb-3 last:pb-0">
          <div className="flex flex-col items-center">
            <span className="mt-1 h-2 w-2 rounded-full bg-ai" aria-hidden />
            {i < items.length - 1 && <span className="w-px flex-1 bg-border" aria-hidden />}
          </div>
          <div className="min-w-0 pb-1">
            <p className="text-sm">{it.label}</p>
            {it.when && <p className="text-xs text-muted-foreground">{it.when}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
