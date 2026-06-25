"use client";

/**
 * Phase 10.4 — Lead Opportunities (ranked).
 *
 *   🎯 LEAD OPPORTUNITIES
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ #1  Aisha Khanna · X Corp        Hot · 91%                  │
 *   │     Why now: Visited pricing 3 times in 2 days              │
 *   │     Action:  Send a 15-min booking link                     │
 *   │     Value:   High-value lead · 5 mins to handle             │
 *   │     [ Open lead → ]                                          │
 *   └──────────────────────────────────────────────────────────────┘
 *   …
 *
 * Pulls `api.leads.intelligence()` — the existing Phase-5 ranked
 * priority feed. Backend already does the scoring (rank, priority,
 * confidence, estimated_value_band); frontend just presents the top 5
 * with action-shaped CTAs.
 *
 * Constitution discipline: every row shows recommendation + reason +
 * confidence + expected_result (the four required fields).
 */

import { ArrowRight, Sparkles, Target, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { scoreLeadPriority } from "@/lib/action-scoring";
import {
  api,
  ApiError,
  type LeadPriorityItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty"; message: string }
  | { kind: "ready"; priorities: LeadPriorityItem[] };

const MAX_ITEMS = 5;

export function LeadOpportunities({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report = await api.leads.intelligence();
      const priorities = (report.priorities ?? []).slice(0, MAX_ITEMS);
      if (priorities.length === 0) {
        setState({
          kind: "empty",
          message: "No high-value leads waiting right now. We'll surface them here as they arrive.",
        });
        return;
      }
      setState({ kind: "ready", priorities });
    } catch (err) {
      // 409 from backend means onboarding incomplete — friendly empty.
      if (err instanceof ApiError && err.status === 409) {
        setState({
          kind: "empty",
          message: "Complete your business profile so the engine can score your leads.",
        });
        return;
      }
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load lead opportunities.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="lead-opportunities"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <div className="flex items-end justify-between">
        <SectionHeading
          eyebrow={
            <span className="inline-flex items-center gap-1.5">
              <Target className="h-3 w-3" />
              Lead opportunities
            </span>
          }
          heading="Highest-value leads waiting"
          description="Ranked by potential value × conversion probability × urgency."
        />
        <Link
          href={"/grow/leads" as never}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          data-testid="lead-opportunities-see-all"
        >
          Open inbox →
        </Link>
      </div>

      {state.kind === "loading" && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Leads unavailable"
          description={state.message}
          data-testid="lead-opportunities-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Users}
          title="No ranked leads yet"
          description={state.message}
          data-testid="lead-opportunities-empty"
        />
      )}

      {state.kind === "ready" && (
        <ol
          className="flex flex-col gap-2"
          data-testid="lead-opportunities-list"
        >
          {state.priorities.map((p) => (
            <LeadRow key={p.lead_id} priority={p} />
          ))}
        </ol>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row
// ---------------------------------------------------------------------

const PRIORITY_TONE: Record<
  LeadPriorityItem["priority"],
  "good" | "watch" | "bad" | "muted"
> = {
  focus: "bad", // urgent = stronger tone
  hot: "bad",
  warm: "watch",
  cold: "muted",
};

const PRIORITY_LABEL: Record<LeadPriorityItem["priority"], string> = {
  focus: "Focus",
  hot: "Hot",
  warm: "Warm",
  cold: "Cooling",
};

function LeadRow({ priority }: { priority: LeadPriorityItem }) {
  const score = scoreLeadPriority(priority);
  const href = `/grow/leads?lead_id=${encodeURIComponent(priority.lead_id)}&from=command-center`;
  const displayName =
    priority.name || priority.company || priority.email;

  return (
    <li>
      <article
        data-testid={`lead-opportunity-${priority.lead_id}`}
        className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-start"
      >
        {/* Rank pill */}
        <span
          aria-hidden
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold tabular-nums text-foreground"
        >
          #{priority.rank}
        </span>

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <header className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {displayName}
            </span>
            {priority.company && priority.name && (
              <span className="text-xs text-muted-foreground">
                · {priority.company}
              </span>
            )}
            <StatusPill
              tone={PRIORITY_TONE[priority.priority]}
              size="sm"
              dot
              className="ml-auto"
            >
              {PRIORITY_LABEL[priority.priority]} · {score.confidence}%
            </StatusPill>
          </header>

          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Why now: </span>
            {priority.why_now}
          </p>

          <p className="text-sm font-medium text-foreground">
            <span className="text-muted-foreground">Action: </span>
            {priority.recommended_action}
          </p>

          <ul className="flex flex-wrap gap-1.5 text-[11px]">
            {score.expectedRevenue && (
              <li>
                <StatusPill tone="good" size="sm">
                  {score.expectedRevenue}
                </StatusPill>
              </li>
            )}
            <li>
              <StatusPill tone="muted" size="sm">
                {score.timeRequired} to handle
              </StatusPill>
            </li>
          </ul>
        </div>

        <Link
          href={href as never}
          data-testid={`lead-opportunity-${priority.lead_id}-cta`}
          className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
        >
          {priority.cta_label || "Open lead"}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </article>
    </li>
  );
}
