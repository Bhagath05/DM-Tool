"use client";

/**
 * Phase 10.0 polish — Winning Creative Formula.
 *
 * Polish over the 10.0 baseline:
 *   - Animated entry via `aicmo-fade-up` staggered per tile.
 *   - Pulse-animated connectors so the flow feels alive without
 *     reading like a marketing animation.
 *   - Color-coded role tiles (audience / feeling / offer / angle /
 *     buyer-stage) — each gets a tiny AI accent badge so the eye
 *     can pick the dimension at a glance.
 *   - Confidence rendered as a `<ConfidenceBar>` in the outcome
 *     block, not just a pill.
 *   - Reads cleanly at 2-up on tablet and stacks gracefully on mobile.
 */

import {
  ArrowDown,
  ArrowRight,
  Award,
  CornerDownRight,
  Heart,
  Megaphone,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import type { PerformanceOpportunity } from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

interface FormulaStep {
  label: string;
  value: string | null;
  icon: LucideIcon;
}

const FUNNEL_PHRASE: Record<string, string> = {
  awareness: "People who are new to you",
  consideration: "People weighing their options",
  conversion: "People ready to buy or book",
  retention: "Your existing customers",
};

const OFFER_PHRASE: Record<string, string> = {
  discount: "A discount",
  free_trial: "A free trial",
  consultation: "A free consultation",
  bundle: "A bundle",
  promotion: "A promotion",
  seasonal: "A seasonal offer",
  none: "No special offer",
};

function humanise(value: string | null | undefined): string | null {
  if (!value) return null;
  return value.replace(/_/g, " ");
}

export interface WinningCreativeFormulaProps {
  card: PerformanceOpportunity | null;
  className?: string;
}

export function WinningCreativeFormula({
  card,
  className,
}: WinningCreativeFormulaProps) {
  if (!card) return null;
  const e = (card.evidence ?? {}) as Record<string, unknown>;

  const audienceRaw = typeof e["audience"] === "string" ? e["audience"] : null;
  const emotionRaw = typeof e["emotion"] === "string" ? e["emotion"] : null;
  const offerRaw = typeof e["offer_type"] === "string" ? e["offer_type"] : null;
  const angleRaw =
    typeof e["concept_family"] === "string" ? e["concept_family"] : null;
  const funnelRaw =
    typeof e["funnel_stage"] === "string" ? e["funnel_stage"] : null;

  const steps: FormulaStep[] = [
    { label: "Audience", value: humanise(audienceRaw), icon: Users },
    { label: "Feeling", value: humanise(emotionRaw), icon: Heart },
    {
      label: "Offer",
      value: offerRaw ? OFFER_PHRASE[offerRaw] ?? humanise(offerRaw) : null,
      icon: Megaphone,
    },
    { label: "Angle", value: humanise(angleRaw), icon: Target },
    {
      label: "Buyer stage",
      value: funnelRaw ? FUNNEL_PHRASE[funnelRaw] ?? humanise(funnelRaw) : null,
      icon: CornerDownRight,
    },
  ];

  const conversions =
    typeof e["conversions"] === "number" ? e["conversions"] : null;
  const cpl = typeof e["cpl"] === "number" ? e["cpl"] : null;
  const currency = typeof e["currency"] === "string" ? e["currency"] : null;
  const creativesCount =
    typeof e["creatives_count"] === "number" ? e["creatives_count"] : null;

  return (
    <section
      data-testid="winning-creative-formula"
      className={cn("animate-fade-up flex flex-col gap-5", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3 w-3" />
            Signature insight
          </span>
        }
        heading="Winning Creative Formula"
        description="The exact recipe behind your best-performing ads. Reuse it on your next batch."
        action={
          <StatusPill tone="ai" size="md" dot data-testid="formula-confidence">
            {card.confidence}% confidence
          </StatusPill>
        }
        size="lg"
      />

      <div
        className={cn(
          "relative overflow-hidden rounded-2xl border border-ai-border bg-gradient-to-br from-ai-soft via-card to-card p-6 shadow-md sm:p-8",
        )}
      >
        {/* Animated ambient glows */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 -right-32 h-72 w-72 rounded-full bg-ai/15 blur-3xl animate-pulse-soft"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-24 -left-24 h-48 w-48 rounded-full bg-ai/10 blur-3xl"
          style={{ animationDelay: "1.2s" }}
        />

        <div className="relative grid gap-8 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
          {/* LEFT — the formula flow */}
          <div className="flex flex-col gap-1.5" data-testid="formula-flow">
            {steps.map((s, i) => (
              <div
                key={s.label}
                className="flex flex-col animate-fade-up"
                data-stagger={i + 1}
              >
                <FormulaTile step={s} index={i} />
                {i < steps.length - 1 && <FlowConnector />}
              </div>
            ))}
          </div>

          {/* MIDDLE — connector on lg+ */}
          <div className="hidden text-ai/40 lg:block animate-flow-pulse" aria-hidden>
            <ArrowRight className="h-7 w-7" />
          </div>

          {/* RIGHT — outcome + action + confidence */}
          <div className="flex flex-col gap-4">
            <div
              className="rounded-2xl border border-ai-border bg-card/85 p-5 shadow-sm backdrop-blur animate-pop"
              data-testid="formula-outcome"
            >
              <div className="flex items-center gap-2 text-meta text-ai-soft-foreground">
                <Award className="h-3.5 w-3.5" />
                Outcome
              </div>
              <div className="mt-2 flex items-baseline gap-2 tabular">
                <span className="text-display tracking-tight">
                  {conversions ?? "—"}
                </span>
                <span className="text-base font-medium text-muted-foreground">
                  leads
                </span>
              </div>
              {cpl !== null && currency && (
                <p className="text-sm text-muted-foreground">
                  at {currency} {Math.round(cpl).toLocaleString()} each
                  {creativesCount
                    ? ` across ${creativesCount} ad${creativesCount === 1 ? "" : "s"}`
                    : ""}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <span className="text-meta">What to do next</span>
              <p className="text-sm leading-relaxed text-foreground/90">
                {card.recommendation}
              </p>
            </div>

            <div className="space-y-1.5">
              <span className="text-meta">Expected lift</span>
              <p className="text-sm leading-relaxed text-foreground/90">
                {card.expectedResult}
              </p>
            </div>

            <div className="space-y-1.5">
              <ConfidenceBar value={card.confidence} size="lg" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FormulaTile({ step, index }: { step: FormulaStep; index: number }) {
  const Icon = step.icon;
  const value = step.value ?? "Unknown";
  return (
    <div
      data-testid={`formula-tile-${step.label.toLowerCase().replace(/\s+/g, "-")}`}
      className="group flex items-center gap-3 rounded-xl border border-border/60 bg-card/85 px-4 py-3 shadow-xs backdrop-blur transition-all duration-200 hover:border-ai-border hover:shadow-sm"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-ai/15 to-ai-soft text-ai transition-transform duration-200 group-hover:scale-105">
        <Icon className="h-4 w-4" />
      </span>
      <div className="flex min-w-0 flex-col">
        <span className="flex items-center gap-1.5">
          <span className="text-meta">{step.label}</span>
          <span
            className="text-[9px] font-semibold uppercase tracking-wider text-ai-soft-foreground"
            aria-hidden
          >
            · {index + 1}/5
          </span>
        </span>
        <span className="truncate text-sm font-semibold capitalize text-foreground">
          {value}
        </span>
      </div>
    </div>
  );
}

function FlowConnector() {
  return (
    <div className="my-0.5 flex flex-col items-center gap-0.5 text-ai/40">
      <span
        aria-hidden
        className="block h-2 w-px bg-current animate-flow-pulse"
      />
      <ArrowDown className="h-3 w-3 animate-flow-pulse" aria-hidden />
      <span
        aria-hidden
        className="block h-2 w-px bg-current animate-flow-pulse"
      />
    </div>
  );
}
