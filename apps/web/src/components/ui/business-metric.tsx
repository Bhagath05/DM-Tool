"use client";

/**
 * `<BusinessMetric>` and `<AiRecommendation>` — the Constitution-shaped
 * cards. Phase 10.0 visual rewrite: same props, premium hierarchy.
 *
 * Visual contract (post-10.0):
 *
 *   ┌────────────────────────────────────────────────────────────┐
 *   │ [icon · category eyebrow]            [confidence pill]     │
 *   │                                                            │
 *   │ HEADLINE (display)                                         │
 *   │ sub-line (plain language / what is happening)              │
 *   │                                                            │
 *   │ [optional chip strip — AiRec only: priority/effort/...]    │
 *   │                                                            │
 *   │ ┌── What's happening ──┬── What to expect ──┐              │
 *   │ │ ...                  │ ...                │              │
 *   │ └──────────────────────┴────────────────────┘              │
 *   │                                                            │
 *   │ Why this · short reason line                               │
 *   │                                                            │
 *   │ [Technical details ▾]                                      │
 *   └────────────────────────────────────────────────────────────┘
 *
 * Props are byte-identical to Phase 2. Phase-2 tests pin every
 * `data-testid` and the text content of every section; those are
 * preserved verbatim even though the surrounding layout changed.
 *
 * Color discipline (Phase 10.0):
 *   - Impact-category accent has been NEUTRALISED. The icon is the
 *     differentiator; chip backgrounds are uniform `bg-muted` so the
 *     dashboard no longer reads as a rainbow.
 *   - The only colored surfaces are confidence-band / status / AI
 *     chips — all routed through `<StatusPill>` so they map to the
 *     5-color semantic palette.
 */

import {
  ChevronDown,
  ChevronUp,
  Clock,
  DollarSign,
  type LucideIcon,
  PiggyBank,
  Sparkles,
  TrendingUp,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { useViewMode } from "@/lib/use-view-mode";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------
//  Types — mirror the backend recommendation contract.
// ---------------------------------------------------------------------

export type ImpactCategory =
  | "revenue"
  | "lead"
  | "customer"
  | "time"
  | "cost";

export type MetricStatus = "good" | "warning" | "bad" | "neutral";

/**
 * Optional Phase 10.0 chip strip — Priority / Effort / Expected
 * Leads / Revenue Impact / etc. Strings only; the caller (usually
 * `<PerformanceEngineCard>` via `lib/performance-derived.ts`)
 * decides which chips are honest enough to render.
 */
export interface RecommendationChips {
  priority?: "HIGH" | "MEDIUM" | "LOW";
  effort?: string;
  expectedLeads?: string;
  revenueImpact?: string;
}

export interface BusinessMetricProps {
  /** Numeric or short-text value, formatted for the user. e.g. "₹120 per lead". */
  value: string;
  plainLanguage: string;
  status: MetricStatus;
  impactCategory: ImpactCategory;
  businessImpact: string;
  recommendation: string;
  expectedResult: string;
  confidence: number;
  reason: string;
  technicalDetails?: Record<string, string | number>;
  chips?: RecommendationChips;
  className?: string;
  "data-testid"?: string;
}

export interface AiRecommendationProps {
  whatIsHappening: string;
  impactCategory: ImpactCategory;
  recommendation: string;
  expectedResult: string;
  confidence: number;
  reason: string;
  technicalDetails?: Record<string, string | number>;
  chips?: RecommendationChips;
  className?: string;
  "data-testid"?: string;
}

// ---------------------------------------------------------------------
//  Internal helpers
// ---------------------------------------------------------------------

const IMPACT_META: Record<ImpactCategory, { icon: LucideIcon; label: string }> = {
  revenue: { icon: DollarSign, label: "Revenue" },
  lead: { icon: Users, label: "Leads" },
  customer: { icon: UserCheck, label: "Customers" },
  time: { icon: Clock, label: "Time" },
  cost: { icon: PiggyBank, label: "Cost" },
};

const STATUS_META: Record<
  MetricStatus,
  { label: string; tone: PillTone }
> = {
  good: { label: "Good", tone: "good" },
  warning: { label: "Watch", tone: "watch" },
  bad: { label: "Needs attention", tone: "bad" },
  neutral: { label: "Neutral", tone: "neutral" },
};

/**
 * Confidence calibration matches the Constitution bands:
 *   80-100 High · 60-79 Medium · 40-59 Low · <40 Speculative.
 */
function confidenceBand(confidence: number): {
  label: string;
  tone: PillTone;
} {
  if (confidence >= 80) return { label: "High confidence", tone: "good" };
  if (confidence >= 60) return { label: "Medium confidence", tone: "ai" };
  if (confidence >= 40) return { label: "Low confidence", tone: "watch" };
  return { label: "Speculative", tone: "muted" };
}

function assertNonEmpty(name: string, value: string | undefined): void {
  if (!value || value.trim().length === 0) {
    throw new Error(
      `[BusinessMetric/AiRecommendation] required prop '${name}' is empty. ` +
        `The Constitution requires every recommendation to carry all four ` +
        `of recommendation, expectedResult, confidence, reason.`,
    );
  }
}

function assertConfidence(confidence: number): void {
  if (
    typeof confidence !== "number" ||
    !Number.isFinite(confidence) ||
    confidence < 0 ||
    confidence > 100
  ) {
    throw new Error(
      `[BusinessMetric/AiRecommendation] 'confidence' must be a number ` +
        `between 0 and 100. Got: ${String(confidence)}`,
    );
  }
}

// ---------------------------------------------------------------------
//  Section header (kept for testid contract) + technical-details disclosure
// ---------------------------------------------------------------------

function Section({
  title,
  children,
  testId,
  className,
}: {
  title: string;
  children: React.ReactNode;
  testId: string;
  className?: string;
}) {
  return (
    <div data-testid={testId} className={cn("flex flex-col gap-1.5", className)}>
      <h4 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {title}
      </h4>
      <div className="text-sm leading-relaxed text-foreground/90">
        {children}
      </div>
    </div>
  );
}

function TechnicalDetails({
  details,
  startOpen,
}: {
  details: Record<string, string | number>;
  startOpen: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  useEffect(() => {
    setOpen(startOpen);
  }, [startOpen]);
  const entries = Object.entries(details);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 border-t border-border/60 pt-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        data-testid="technical-details-toggle"
        className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-foreground"
      >
        <span>Technical Details (Optional)</span>
        {open ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </button>
      {open && (
        <dl
          data-testid="technical-details-body"
          className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs tabular sm:grid-cols-2"
        >
          {entries.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2">
              <dt className="font-medium text-muted-foreground">{k}</dt>
              <dd className="font-mono text-foreground/90">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Chip strip — Phase 10.0
// ---------------------------------------------------------------------

const PRIORITY_TONE: Record<
  NonNullable<RecommendationChips["priority"]>,
  PillTone
> = {
  HIGH: "good",
  MEDIUM: "ai",
  LOW: "muted",
};

function ChipStrip({ chips }: { chips: RecommendationChips }) {
  const items: React.ReactNode[] = [];
  if (chips.priority) {
    items.push(
      <StatusPill
        key="priority"
        tone={PRIORITY_TONE[chips.priority]}
        size="sm"
        data-testid="chip-priority"
      >
        {chips.priority} priority
      </StatusPill>,
    );
  }
  if (chips.effort) {
    items.push(
      <StatusPill
        key="effort"
        tone="neutral"
        icon={Zap}
        size="sm"
        data-testid="chip-effort"
      >
        {chips.effort}
      </StatusPill>,
    );
  }
  if (chips.expectedLeads) {
    items.push(
      <StatusPill
        key="leads"
        tone="neutral"
        icon={Users}
        size="sm"
        data-testid="chip-leads"
      >
        {chips.expectedLeads}
      </StatusPill>,
    );
  }
  if (chips.revenueImpact) {
    items.push(
      <StatusPill
        key="revenue"
        tone="neutral"
        icon={DollarSign}
        size="sm"
        data-testid="chip-revenue"
      >
        {chips.revenueImpact}
      </StatusPill>,
    );
  }
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="chip-strip">
      {items}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Internal layout — the premium card both public components share.
// ---------------------------------------------------------------------

interface CardLayoutProps {
  eyebrow: React.ReactNode;
  topRight?: React.ReactNode;
  headline: React.ReactNode;
  subline?: React.ReactNode;
  chips?: RecommendationChips;

  whatIsHappening: string;
  whatShouldIDo: string;
  expectedResult: string;
  confidence: number;
  reason: string;

  technicalDetails?: Record<string, string | number>;

  className?: string;
  "data-testid"?: string;
}

function CardLayout({
  eyebrow,
  topRight,
  headline,
  subline,
  chips,
  whatIsHappening,
  whatShouldIDo,
  expectedResult,
  confidence,
  reason,
  technicalDetails,
  className,
  "data-testid": testId,
}: CardLayoutProps) {
  const { isProfessional } = useViewMode();
  const band = confidenceBand(confidence);

  return (
    <article
      data-testid={testId}
      className={cn(
        "card-surface card-surface-hover group flex flex-col gap-5 p-6 sm:p-7",
        className,
      )}
    >
      {/* Top stripe — impact eyebrow + status / confidence */}
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">{eyebrow}</div>
        {topRight}
      </header>

      {/* Headline + subline — the primary slot.
          For BusinessMetric this is the value; for AiRecommendation this
          is the recommendation, so the action is the headline. */}
      <div className="flex flex-col gap-1.5">
        <div className="text-[22px] font-semibold leading-tight tracking-tight">
          {headline}
        </div>
        {subline && (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {subline}
          </p>
        )}
      </div>

      {/* Optional chip strip — Priority / Effort / Expected Leads / Revenue */}
      {chips && <ChipStrip chips={chips} />}

      {/* Body — three required sections (happening, action, expected).
          Action lives BETWEEN context and expected so the eye lands on
          it. Confidence has its own marker section preserved for the
          Phase 2 test contract. */}
      <div className="flex flex-col gap-4">
        <Section title="What is happening?" testId="section-happening">
          {whatIsHappening}
        </Section>

        <Section title="What should I do?" testId="section-action">
          <span className="font-medium text-foreground">{whatShouldIDo}</span>
        </Section>

        <Section
          title="What result can I expect?"
          testId="section-expected-result"
        >
          {expectedResult}
        </Section>

        <Section title="Confidence" testId="section-confidence">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <StatusPill
                tone={band.tone}
                size="sm"
                dot={band.tone === "good" || band.tone === "ai"}
                data-testid="confidence-pill"
              >
                {band.label}
              </StatusPill>
              <span className="text-xs tabular text-muted-foreground">
                ({confidence}%)
              </span>
            </div>
            <ConfidenceBar value={confidence} size="sm" hideLabel />
          </div>
        </Section>

        <Section title="Why this recommendation?" testId="section-reason">
          <span className="text-muted-foreground">{reason}</span>
        </Section>

        {technicalDetails && Object.keys(technicalDetails).length > 0 && (
          <TechnicalDetails
            details={technicalDetails}
            startOpen={isProfessional}
          />
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Eyebrow — the impact-category badge atop every card. Neutral, icon-led.
// ---------------------------------------------------------------------

function ImpactEyebrow({
  category,
  prefix,
}: {
  category: ImpactCategory;
  prefix?: string;
}) {
  const impact = IMPACT_META[category];
  const Icon = impact.icon;
  return (
    <>
      <span
        className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-muted text-foreground/80"
        aria-hidden
      >
        <Icon className="h-3.5 w-3.5" />
      </span>
      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {prefix ? `${prefix} · ` : ""}
        {impact.label} impact
      </span>
    </>
  );
}

// ---------------------------------------------------------------------
//  Public — <BusinessMetric>
// ---------------------------------------------------------------------

export function BusinessMetric(props: BusinessMetricProps) {
  assertNonEmpty("value", props.value);
  assertNonEmpty("plainLanguage", props.plainLanguage);
  assertNonEmpty("businessImpact", props.businessImpact);
  assertNonEmpty("recommendation", props.recommendation);
  assertNonEmpty("expectedResult", props.expectedResult);
  assertNonEmpty("reason", props.reason);
  assertConfidence(props.confidence);

  const status = STATUS_META[props.status];

  return (
    <CardLayout
      data-testid={props["data-testid"] ?? "business-metric"}
      className={props.className}
      eyebrow={<ImpactEyebrow category={props.impactCategory} />}
      topRight={
        <StatusPill
          tone={status.tone}
          data-testid="status-pill"
          dot={status.tone === "good"}
        >
          {status.label}
        </StatusPill>
      }
      headline={
        <span className="tabular">{props.value}</span>
      }
      subline={props.plainLanguage}
      chips={props.chips}
      whatIsHappening={props.businessImpact}
      whatShouldIDo={props.recommendation}
      expectedResult={props.expectedResult}
      confidence={props.confidence}
      reason={props.reason}
      technicalDetails={props.technicalDetails}
    />
  );
}

// ---------------------------------------------------------------------
//  Public — <AiRecommendation>
// ---------------------------------------------------------------------

export function AiRecommendation(props: AiRecommendationProps) {
  assertNonEmpty("whatIsHappening", props.whatIsHappening);
  assertNonEmpty("recommendation", props.recommendation);
  assertNonEmpty("expectedResult", props.expectedResult);
  assertNonEmpty("reason", props.reason);
  assertConfidence(props.confidence);

  return (
    <CardLayout
      data-testid={props["data-testid"] ?? "ai-recommendation"}
      className={props.className}
      eyebrow={
        <ImpactEyebrow
          category={props.impactCategory}
          prefix="AI recommendation"
        />
      }
      headline={
        <span className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-ai" aria-hidden />
          <span>{props.recommendation}</span>
        </span>
      }
      // Surface the contextual line under the recommendation, since the
      // recommendation IS the headline now and `whatIsHappening` already
      // carries the situational context. We render it again below as the
      // explicit Section (test-pinned), but the subline gives the eye an
      // immediate "why now."
      subline={props.whatIsHappening}
      chips={props.chips}
      whatIsHappening={props.whatIsHappening}
      whatShouldIDo={props.recommendation}
      expectedResult={props.expectedResult}
      confidence={props.confidence}
      reason={props.reason}
      technicalDetails={props.technicalDetails}
    />
  );
}

/** Re-export for tests + downstream callers. */
export { TrendingUp as DefaultMetricIcon };
