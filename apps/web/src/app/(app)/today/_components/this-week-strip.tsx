"use client";

/**
 * Phase 10.3b — Section 4: This Week.
 *
 * Day-by-day action list:
 *
 *   Mon  Contact 3 warm leads               [ Do it ]
 *   Tue  Publish reel "5 mistakes..."       [ Open  ]
 *   Wed  Launch campaign                    [ Go    ]
 *   Thu  Review opportunity                 [ See   ]
 *   Fri  Approve ad creative                [ Open  ]
 *
 * Reuses `api.coach.weekly()` — same data the AiCoachPanel reads, no
 * extra LLM call. The Coach plan is a flat list of actions ranked by
 * priority; we map them onto Mon→Fri in order so the founder sees a
 * concrete five-day plan.
 *
 * Discipline (Founder Simplification Pass):
 *   - Max 5 actions visible. The full plan stays accessible via
 *     "See full weekly plan" → /ai-coach.
 *   - Every row has a CTA. No row is just informational.
 *   - "Tasks done" counter on Day-At-A-Glance reflects user clicks
 *     here — handled by ActionCenter's storage in a later slice; this
 *     component is read-only for now.
 */

import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, type ActionTarget, type WeeklyAction } from "@/lib/api";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; actions: WeeklyAction[] };

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

export function ThisWeekStrip({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const plan = await api.coach.weekly();
      const actions = (plan.actions ?? []).slice(0, 5);
      if (actions.length === 0) {
        setState({ kind: "empty" });
        return;
      }
      setState({ kind: "ready", actions });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load this week's plan. Refresh to try again.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="this-week-strip"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <div className="flex items-end justify-between">
        <SectionHeading
          eyebrow="This week"
          heading="Your five-day plan"
          description="The next moves, ranked. Tackle one, watch the rest line up."
        />
        <Link
          href={"/ai-coach" as never}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          data-testid="this-week-see-all"
        >
          See full plan →
        </Link>
      </div>

      {state.kind === "loading" && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="Plan unavailable"
          description={state.message}
          data-testid="this-week-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="No plan yet"
          description="Your weekly plan will appear here once the Coach has enough signal."
          hint="Upload an ad export or capture a few leads to seed the engine."
          data-testid="this-week-empty"
        />
      )}

      {state.kind === "ready" && (
        <ol className="flex flex-col gap-2" data-testid="this-week-list">
          {state.actions.map((action, i) => (
            <ActionRow
              key={`${i}-${action.action_title}`}
              day={DAY_LABELS[i] ?? ""}
              action={action}
            />
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Single action row — day pill · title · CTA
// ---------------------------------------------------------------------

function ActionRow({ day, action }: { day: string; action: WeeklyAction }) {
  const href = ctaHref(action.cta_target);
  return (
    <li>
      <Link
        href={href as never}
        data-testid={`this-week-row-${day.toLowerCase()}`}
        className={cn(
          "group flex items-center gap-4 rounded-xl border border-border bg-card px-4 py-3 transition-all duration-200",
          "hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm",
        )}
      >
        <span
          className="inline-flex h-9 w-12 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold uppercase tracking-wide text-muted-foreground"
          aria-hidden
        >
          {day}
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium text-foreground">
            {action.action_title}
          </span>
          <span className="truncate text-xs text-muted-foreground">
            {action.expected_result}
          </span>
        </span>
        {action.estimated_time && (
          <StatusPill tone="muted" size="sm">
            {action.estimated_time}
          </StatusPill>
        )}
        <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors group-hover:text-foreground">
          {action.cta_label}
          <ArrowRight className="h-3 w-3" />
        </span>
      </Link>
    </li>
  );
}

// ---------------------------------------------------------------------
//  CTA target → frontend route
// ---------------------------------------------------------------------

/**
 * Map the backend's ActionTarget enum to a frontend URL.
 *
 * Targets that have no obvious frontend home land on /today (the
 * action stays inline). This is intentional: a CTA that disappears
 * into "nowhere" is worse than one that keeps the founder on the
 * page they understand.
 */
function ctaHref(target: ActionTarget): string {
  switch (target) {
    case "content":
      return "/create/social-posts";
    case "ads":
      return "/create/ads";
    case "visuals":
      return "/create/creatives";
    case "campaigns":
      return "/campaigns";
    case "lead_pages":
      return "/grow/leads";
    case "trends":
      return "/grow/market-intelligence";
    case "analytics":
      return "/results";
    case "profile":
      return "/settings/organization";
    default: {
      // Exhaustiveness check — adding a new ActionTarget without
      // mapping it here is a TypeScript compile error.
      const _exhaustive: never = target;
      void _exhaustive;
      return "/today";
    }
  }
}
