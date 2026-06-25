"use client";

/**
 * Phase 10.0 polish — AI Coach panel.
 *
 * Hero-band rendering of the founder's #1 action this week. Pulls
 * from `/coach/weekly` and surfaces the top action inside a premium
 * AI-tinted container with a soft outer glow.
 *
 * Polish (vs the 10.0 baseline):
 *   - AI gradient backdrop + glow shadow signals "this is the core
 *     feature" without resorting to rainbow chrome.
 *   - Priority + Impact + Effort + Confidence each render as a
 *     dedicated stat tile, not just chips on the recommendation card.
 *   - Confidence visualised via `<ConfidenceBar>` rather than text-
 *     only.
 *   - Empty + error states use `<EmptyState variant="ai">` for visual
 *     consistency with the rest of the AI surfaces.
 */

import { Compass, Sparkles, Wand2, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonCard } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type ActionPriority,
  type ImpactCategory,
  type WeeklyAction,
  type WeeklyPlan,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const PRIORITY_LABEL: Record<ActionPriority, "HIGH" | "MEDIUM" | "LOW"> = {
  focus: "HIGH",
  important: "MEDIUM",
  stretch: "LOW",
};

const IMPACT_LABEL: Record<ImpactCategory, string> = {
  revenue: "Revenue",
  lead: "Leads",
  customer: "Customers",
  time: "Time",
  cost: "Cost",
};

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; plan: WeeklyPlan; top: WeeklyAction };

export function AiCoachPanel() {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const plan = await api.coach.weekly();
      const top = plan.actions.find((a) => a.priority === "focus")
        ?? plan.actions[0];
      if (!top) {
        setState({ kind: "empty" });
        return;
      }
      setState({ kind: "ready", plan, top });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Coach is taking a break.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="ai-coach-panel"
      className="animate-fade-up flex flex-col gap-5"
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Wand2 className="h-3 w-3" />
            AI Coach
          </span>
        }
        heading={
          state.kind === "ready" ? state.plan.headline : "Your weekly focus"
        }
        description={
          state.kind === "ready"
            ? state.plan.week_focus
            : "One action, calibrated to your data, ranked above everything else this week."
        }
        size="lg"
      />

      {state.kind === "loading" && <SkeletonCard data-testid="ai-coach-skeleton" />}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="Coach is taking a moment"
          description={state.message}
          hint="The recommendation engine reruns on the next page refresh."
          data-testid="ai-coach-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Compass}
          variant="ai"
          title="No coaching for you yet"
          description="Once your data shows a clear next move, we'll surface it here as your weekly focus."
          hint="Upload an ad export above to seed the engine."
          data-testid="ai-coach-empty"
        />
      )}

      {state.kind === "ready" && <CoachCard action={state.top} />}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Coach hero card — premium AI container
// ---------------------------------------------------------------------

function CoachCard({ action }: { action: WeeklyAction }) {
  const priority = PRIORITY_LABEL[action.priority];
  const impactLabel = IMPACT_LABEL[action.impact_category];

  return (
    <article
      data-testid="ai-coach-card"
      className="relative overflow-hidden card-surface-ai p-7 sm:p-8"
    >
      {/* Soft animated glow — feels intelligent without being noisy. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -right-32 h-72 w-72 rounded-full bg-ai/15 blur-3xl animate-pulse-soft"
      />

      <div className="relative flex flex-col gap-6">
        {/* Top stripe — AI badge + impact + priority */}
        <header className="flex flex-wrap items-center gap-2">
          <StatusPill tone="ai" size="md" dot icon={Sparkles}>
            AI recommendation
          </StatusPill>
          <StatusPill tone="neutral" size="md">
            {impactLabel} impact
          </StatusPill>
          <StatusPill
            tone={
              priority === "HIGH"
                ? "good"
                : priority === "MEDIUM"
                  ? "ai"
                  : "muted"
            }
            size="md"
            dot
            data-testid="ai-coach-priority"
          >
            {priority} priority
          </StatusPill>
          <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Zap className="h-3 w-3" />
            <span className="font-medium">{action.estimated_time}</span>
          </span>
        </header>

        {/* Headline = the recommendation */}
        <div className="flex flex-col gap-2.5">
          <h3 className="text-section font-semibold tracking-tight">
            {action.action_title}
          </h3>
          <p className="text-base leading-relaxed text-muted-foreground">
            {action.business_impact}
          </p>
        </div>

        {/* Three-column outcome grid */}
        <div className="grid grid-cols-1 gap-4 rounded-2xl border border-ai-border/70 bg-card/70 p-5 backdrop-blur md:grid-cols-3">
          <StatBlock
            label="Why this"
            body={action.reason}
            data-testid="ai-coach-why"
          />
          <StatBlock
            label="Expected result"
            body={action.expected_result}
            highlight
            data-testid="ai-coach-expected"
          />
          <div data-testid="ai-coach-confidence" className="flex flex-col gap-2">
            <span className="text-meta">Confidence</span>
            <ConfidenceBar value={action.confidence} size="lg" hideLabel />
            <p className="text-xs text-muted-foreground">
              {action.confidence}% · calibrated to the data we've seen.
            </p>
          </div>
        </div>
      </div>
    </article>
  );
}

function StatBlock({
  label,
  body,
  highlight,
  "data-testid": testId,
}: {
  label: string;
  body: string;
  highlight?: boolean;
  "data-testid"?: string;
}) {
  return (
    <div data-testid={testId} className="flex flex-col gap-2">
      <span className="text-meta">{label}</span>
      <p
        className={cn(
          "text-sm leading-relaxed",
          highlight ? "font-semibold text-foreground" : "text-foreground/90",
        )}
      >
        {body}
      </p>
    </div>
  );
}
