"use client";

import {
  ArrowRight,
  Compass,
  Flag,
  HeartHandshake,
  Info,
  Loader2,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RealityCheck, RiskSeverity } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Phase 2.2 — Reality Engine display surface.
 *
 * Style intent: advisory, calm, supportive. Never alarmist. The component
 * accepts three states (`loading`, `error`, `data`) so callers can render
 * it as a single inline element without an outer wrapper.
 *
 * Color rule: tones are chosen by feasibility band but skewed COOL, not
 * RED — even low scores feel like a thoughtful note from a mentor, not a
 * compliance warning.
 */
export function RealityCheckCard({
  state,
}: {
  state:
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "error"; message: string }
    | { kind: "data"; check: RealityCheck };
}) {
  if (state.kind === "idle") return null;

  if (state.kind === "loading") {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          The AI is sense-checking this goal…
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="py-4 text-sm text-muted-foreground">
          Reality check unavailable right now — your goal still works, the
          advisory just needs a retry.
        </CardContent>
      </Card>
    );
  }

  const { check } = state;
  const palette = paletteForScore(check.feasibility_score);

  return (
    <Card className={cn("overflow-hidden", palette.border)}>
      <CardHeader className={cn("flex flex-row items-start gap-4 py-4", palette.bg)}>
        <ScoreGauge score={check.feasibility_score} tone={palette.gauge} />
        <div className="flex-1 space-y-1">
          <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Reality check · {check.feasibility_label}
          </div>
          <CardTitle className="text-base leading-snug">
            {check.headline}
          </CardTitle>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 py-5">
        {check.realistic_milestones.length > 0 && (
          <Section
            icon={Flag}
            title="Realistic milestones"
            description="What you can credibly hit on the way to the goal."
          >
            <div className="grid gap-2">
              {check.realistic_milestones.map((m, i) => (
                <div
                  key={i}
                  className="rounded-md border bg-card/50 px-3 py-2"
                >
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      {m.timeframe}
                    </span>
                    <span className="text-sm font-medium">{m.target}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {m.why_realistic}
                  </p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {check.phased_growth_path.length > 0 && (
          <Section
            icon={Compass}
            title="Path that fits your stage"
            description="Order matters — what to do first."
          >
            <ol className="space-y-2">
              {check.phased_growth_path.map((p, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
                    {i + 1}
                  </span>
                  <div className="flex-1">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                        {p.phase}
                      </span>
                      <span className="font-medium">{p.focus}</span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {p.rationale}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Section>
        )}

        {check.risk_flags.length > 0 && (
          <Section
            icon={ShieldAlert}
            title="Things to know"
            description="Specific constraints — not blockers unless flagged."
          >
            <ul className="space-y-2">
              {check.risk_flags.map((f, i) => (
                <li
                  key={i}
                  className={cn(
                    "flex items-start gap-2 rounded-md border bg-card/50 px-3 py-2 text-xs",
                  )}
                >
                  <SeverityDot severity={f.severity} />
                  <div className="flex-1">
                    <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {f.kind} · {f.severity}
                    </div>
                    <p className="mt-0.5">{f.note}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {check.strategic_notes.length > 0 && (
          <Section
            icon={HeartHandshake}
            title="Strategist notes"
            description="Observations a friend in marketing would tell you."
          >
            <ul className="space-y-1.5">
              {check.strategic_notes.map((n, i) => (
                <li key={i} className="flex gap-2 text-xs leading-relaxed">
                  <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {check.score_signals.length > 0 && (
          <details className="rounded-md border bg-muted/30 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Why this score? <Info className="inline h-3 w-3" />
            </summary>
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
              {check.score_signals.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <ArrowRight className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------- subcomponents ----------------

function Section({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <div className="text-sm font-medium">{title}</div>
      </div>
      <p className="text-[11px] text-muted-foreground">{description}</p>
      {children}
    </section>
  );
}

function ScoreGauge({ score, tone }: { score: number; tone: string }) {
  // Compact circular gauge — readable, no charting library needed.
  return (
    <div
      className={cn(
        "relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        tone,
      )}
      aria-label={`Feasibility score ${score} out of 100`}
    >
      <span className="text-base font-bold">{score}</span>
      <span className="absolute -bottom-1 right-0 rounded-full border bg-background px-1.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
        /100
      </span>
    </div>
  );
}

function SeverityDot({ severity }: { severity: RiskSeverity }) {
  const cls = {
    info: "bg-sky-400",
    watch: "bg-amber-400",
    blocker: "bg-rose-500",
  }[severity];
  return <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", cls)} />;
}

// ---------------- palette ----------------

function paletteForScore(score: number): {
  border: string;
  bg: string;
  gauge: string;
} {
  if (score >= 80) {
    return {
      border: "border-emerald-200/50",
      bg: "bg-emerald-50/40 dark:bg-emerald-950/20",
      gauge: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-100",
    };
  }
  if (score >= 65) {
    return {
      border: "border-teal-200/50",
      bg: "bg-teal-50/40 dark:bg-teal-950/20",
      gauge: "bg-teal-100 text-teal-900 dark:bg-teal-900/30 dark:text-teal-100",
    };
  }
  if (score >= 45) {
    return {
      border: "border-amber-200/50",
      bg: "bg-amber-50/40 dark:bg-amber-950/20",
      gauge: "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100",
    };
  }
  if (score >= 25) {
    return {
      border: "border-orange-200/50",
      bg: "bg-orange-50/40 dark:bg-orange-950/20",
      gauge: "bg-orange-100 text-orange-900 dark:bg-orange-900/30 dark:text-orange-100",
    };
  }
  return {
    // Even at the bottom, we go cool/muted — not red.
    border: "border-slate-300/60",
    bg: "bg-slate-50/40 dark:bg-slate-900/40",
    gauge: "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  };
}
