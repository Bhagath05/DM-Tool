"use client";

/**
 * Phase 10.0 — /ai-coach deep-dive.
 *
 * The Overview page surfaces this week's #1 focus action. This page
 * shows the full weekly plan — every action, grouped by priority,
 * with the same Constitution-shaped card per recommendation.
 *
 * No new endpoints; reuses `api.coach.weekly`.
 */

import { Compass, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AiRecommendation } from "@/components/ui/business-metric";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  ApiError,
  type ActionPriority,
  type ImpactCategory,
  type WeeklyAction,
  type WeeklyPlan,
} from "@/lib/api";

const PRIORITY_LABEL: Record<ActionPriority, "HIGH" | "MEDIUM" | "LOW"> = {
  focus: "HIGH",
  important: "MEDIUM",
  stretch: "LOW",
};

const PRIORITY_GROUP_LABEL: Record<ActionPriority, string> = {
  focus: "This week's focus",
  important: "Important",
  stretch: "Stretch goals",
};

export default function AiCoachPage() {
  const [plan, setPlan] = useState<WeeklyPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPlan(await api.coach.weekly());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Coach is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8">
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Wand2 className="h-3 w-3" />
            AI Coach
          </span>
        }
        heading={plan?.headline ?? "Your weekly plan"}
        description={
          plan?.week_focus ?? "Every recommendation, ranked by what moves the needle this week."
        }
        size="lg"
      />

      {loading && (
        <div className="flex flex-col gap-4">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card p-6"
            >
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-6 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ))}
        </div>
      )}

      {error && !loading && (
        <EmptyState
          icon={Compass}
          variant="ai"
          title="Coach is taking a moment"
          description={error}
        />
      )}

      {plan && !loading && plan.actions.length === 0 && (
        <EmptyState
          icon={Compass}
          variant="ai"
          title="No coaching yet"
          description="Once your data shows enough signal, we'll surface this week's plan here."
        />
      )}

      {plan && !loading && plan.actions.length > 0 && (
        <Plan plan={plan} />
      )}
    </div>
  );
}

function Plan({ plan }: { plan: WeeklyPlan }) {
  const grouped: Record<ActionPriority, WeeklyAction[]> = {
    focus: [],
    important: [],
    stretch: [],
  };
  for (const a of plan.actions) grouped[a.priority].push(a);

  return (
    <div className="flex flex-col gap-8">
      {(["focus", "important", "stretch"] as const).map((p) => {
        const items = grouped[p];
        if (items.length === 0) return null;
        return (
          <section key={p} className="flex flex-col gap-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {PRIORITY_GROUP_LABEL[p]}
            </h3>
            {items.map((a, i) => (
              <AiRecommendation
                key={i}
                data-testid={`coach-action-${p}-${i}`}
                whatIsHappening={a.business_impact}
                impactCategory={a.impact_category as ImpactCategory}
                recommendation={a.action_title}
                expectedResult={a.expected_result}
                confidence={a.confidence}
                reason={a.reason}
                chips={{
                  priority: PRIORITY_LABEL[a.priority],
                  effort: a.estimated_time,
                }}
              />
            ))}
          </section>
        );
      })}
    </div>
  );
}
