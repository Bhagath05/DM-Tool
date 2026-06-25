"use client";

/**
 * Phase 10.0 — Action Center.
 *
 * Aggregates actions from two sources we already have:
 *   - WeeklyPlan.actions (coach)
 *   - Performance overview cards (perf diagnostics, top-3 by confidence)
 *
 * Dedupes by underlying recommendation text. Groups by priority
 * (HIGH / MEDIUM / LOW). Each row supports "Mark done" / "Snooze"
 * which persist to localStorage — the backend doesn't have an
 * actions table yet (queued for 10.1). Honest copy: "Marked done on
 * this device. Cloud sync coming."
 *
 * Renders only "do this" rows — diagnostics-only cards (e.g.
 * audience_loser) become actions because their recommendation IS an
 * action ("move budget to winner") — we keep them.
 */

import {
  CheckCircle2,
  Clock,
  ListChecks,
  RotateCcw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { derive, type Priority } from "@/lib/performance-derived";
import type { PerformanceOpportunity } from "@/lib/performance-translator";
import type { WeeklyAction } from "@/lib/api";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "aicmo.action-center.v1";

interface ActionItem {
  id: string;
  source: "coach" | "performance";
  title: string;
  detail: string;
  priority: Priority;
  effort: string | null;
  expectedLeads: string | null;
  revenueImpact: string | null;
}

type Status = "pending" | "done" | "snoozed";

export interface ActionCenterProps {
  weekly: WeeklyAction[];
  performance: PerformanceOpportunity[];
  className?: string;
}

export function ActionCenter({
  weekly,
  performance,
  className,
}: ActionCenterProps) {
  const items = useMemo(
    () => buildActions(weekly, performance),
    [weekly, performance],
  );
  const [statusMap, setStatusMap] = useState<Record<string, Status>>({});

  // Hydrate from localStorage on mount. SSR-safe.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setStatusMap(JSON.parse(raw) as Record<string, Status>);
    } catch {
      /* ignore corrupted state */
    }
  }, []);

  const setStatus = useCallback((id: string, status: Status) => {
    setStatusMap((prev) => {
      const next = { ...prev, [id]: status };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* best effort */
      }
      return next;
    });
  }, []);

  const open = items.filter((i) => (statusMap[i.id] ?? "pending") === "pending");
  const grouped = {
    HIGH: open.filter((i) => i.priority === "HIGH"),
    MEDIUM: open.filter((i) => i.priority === "MEDIUM"),
    LOW: open.filter((i) => i.priority === "LOW"),
  };

  return (
    <section
      data-testid="action-center"
      className={cn("flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <ListChecks className="h-3 w-3" />
            Things to do
          </span>
        }
        heading="Action Center"
        description="Every action in one place. Mark them done as you go — we sync to the cloud in a future release."
        action={
          open.length > 0 ? (
            <StatusPill tone="neutral" size="md" data-testid="action-count">
              {open.length} pending
            </StatusPill>
          ) : null
        }
      />

      {open.length === 0 ? (
        <EmptyState
          icon={CheckCircle2}
          title="You're all caught up"
          description="Nothing to do right now. We'll surface new actions as your data grows."
          data-testid="action-center-empty"
        />
      ) : (
        <div className="flex flex-col gap-5" data-testid="action-center-list">
          {(["HIGH", "MEDIUM", "LOW"] as const).map((p) => {
            const rows = grouped[p];
            if (rows.length === 0) return null;
            return (
              <div key={p} className="flex flex-col gap-2.5">
                <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {p === "HIGH"
                    ? "High priority"
                    : p === "MEDIUM"
                      ? "Medium priority"
                      : "Worth a try"}
                </h4>
                {rows.map((row) => (
                  <ActionRow
                    key={row.id}
                    item={row}
                    onDone={() => setStatus(row.id, "done")}
                    onSnooze={() => setStatus(row.id, "snoozed")}
                  />
                ))}
              </div>
            );
          })}

          {/* Done-list tail — small undo affordance so the founder
              can recover from a misclick. */}
          {Object.keys(statusMap).length > 0 && (
            <DoneTail
              items={items}
              statusMap={statusMap}
              onReopen={(id) => setStatus(id, "pending")}
            />
          )}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Sub-views
// ---------------------------------------------------------------------

function ActionRow({
  item,
  onDone,
  onSnooze,
}: {
  item: ActionItem;
  onDone: () => void;
  onSnooze: () => void;
}) {
  return (
    <div
      data-testid={`action-row-${item.id}`}
      className="group flex flex-col gap-3 rounded-xl border border-border/70 bg-card p-4 shadow-xs transition-all duration-150 hover:border-ai-border hover:shadow-sm sm:flex-row sm:items-start"
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <p className="text-sm font-semibold leading-snug text-foreground">
          {item.title}
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {item.detail}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {item.effort && (
            <StatusPill tone="neutral" size="sm" icon={Clock}>
              {item.effort}
            </StatusPill>
          )}
          {item.expectedLeads && (
            <StatusPill tone="neutral" size="sm">
              Expected: {item.expectedLeads}
            </StatusPill>
          )}
          {item.revenueImpact && (
            <StatusPill tone="good" size="sm">
              {item.revenueImpact}
            </StatusPill>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 sm:flex-col">
        <button
          type="button"
          onClick={onDone}
          data-testid={`action-done-${item.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-good-border bg-good-soft px-3 py-1.5 text-xs font-medium text-good-soft-foreground transition-colors hover:bg-good hover:text-white"
        >
          <CheckCircle2 className="h-3.5 w-3.5" />
          Mark done
        </button>
        <button
          type="button"
          onClick={onSnooze}
          data-testid={`action-snooze-${item.id}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          Snooze
        </button>
      </div>
    </div>
  );
}

function DoneTail({
  items,
  statusMap,
  onReopen,
}: {
  items: ActionItem[];
  statusMap: Record<string, Status>;
  onReopen: (id: string) => void;
}) {
  const closed = items.filter((i) => statusMap[i.id] && statusMap[i.id] !== "pending");
  if (closed.length === 0) return null;
  return (
    <div className="flex flex-col gap-2 border-t border-border/60 pt-4">
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        Recently closed
      </h4>
      <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
        {closed.slice(0, 4).map((c) => (
          <li
            key={c.id}
            className="flex items-center justify-between gap-2 rounded-lg px-2 py-1"
          >
            <span className="truncate line-through">{c.title}</span>
            <button
              type="button"
              onClick={() => onReopen(c.id)}
              className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-foreground/80 hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" />
              Reopen
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Pure aggregation
// ---------------------------------------------------------------------

const COACH_PRIORITY: Record<WeeklyAction["priority"], Priority> = {
  focus: "HIGH",
  important: "MEDIUM",
  stretch: "LOW",
};

export function buildActions(
  weekly: WeeklyAction[],
  performance: PerformanceOpportunity[],
): ActionItem[] {
  const items: ActionItem[] = [];

  for (const [i, a] of weekly.entries()) {
    items.push({
      id: `coach-${i}-${slug(a.action_title)}`,
      source: "coach",
      title: a.action_title,
      detail: a.business_impact,
      priority: COACH_PRIORITY[a.priority],
      effort: a.estimated_time,
      expectedLeads: null,
      revenueImpact: null,
    });
  }

  for (const c of performance) {
    const d = derive(c);
    // Avoid double-rendering when the perf rec and a coach action
    // are literally the same sentence.
    const title = trimToHeadline(c.recommendation);
    if (items.some((existing) => existing.title.toLowerCase() === title.toLowerCase())) {
      continue;
    }
    items.push({
      id: `perf-${c.id}`,
      source: "performance",
      title,
      detail: c.expectedResult,
      priority: d.priority,
      effort: d.effort,
      expectedLeads: d.expectedLeads,
      revenueImpact: d.revenueImpact,
    });
  }

  // Stable order: priority desc then alphabetical (so the same
  // dataset always presents the same way).
  const order: Record<Priority, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  items.sort((a, b) => {
    if (order[a.priority] !== order[b.priority])
      return order[a.priority] - order[b.priority];
    return a.title.localeCompare(b.title);
  });
  return items;
}

function trimToHeadline(s: string): string {
  // First sentence ≤ 90 chars.
  const idx = s.search(/[.!?]\s/);
  if (idx >= 8 && idx <= 90) return s.slice(0, idx + 1).trim();
  if (s.length <= 90) return s.trim();
  return s.slice(0, 89).trimEnd() + "…";
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 48);
}
