"use client";

/**
 * Phase 10.3b — Section 3: Your Day At A Glance.
 *
 * Four mini-tiles in a single horizontal row:
 *
 *   Leads Waiting   Posts Ready   Opportunities   Tasks Done
 *
 * Discipline:
 *   - Numbers ONLY, no charts (Founder Simplification Pass).
 *   - Each tile links to the destination that satisfies it.
 *   - Loading + empty states never block the rest of the page.
 *   - Reuses existing APIs only — no new backend.
 *
 * Data sources (every one already exists):
 *   - Leads waiting   → api.leads.list({ status: 'new', limit: 1 }).total
 *   - Posts ready     → api.content.list({ limit: 5 }).length
 *   - Opportunities   → api.opportunities.center() arrays
 *   - Tasks done      → ActionCenter's localStorage counter (read-only here)
 *
 * The ActionCenter counter key is duplicated as a constant rather than
 * imported, to avoid coupling Today to Overview's component internals.
 * If ActionCenter changes its storage shape, the counter degrades to
 * "—" instead of crashing.
 */

import { ArrowRight, Inbox, Lightbulb, Send, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TileData {
  leadsWaiting: number | null;
  postsReady: number | null;
  opportunities: number | null;
  tasksDone: number | null;
}

const ACTION_CENTER_STORAGE_KEY = "aicmo.action-center.v1";

export function DayAtAGlance({ className }: { className?: string }) {
  const [data, setData] = useState<TileData>({
    leadsWaiting: null,
    postsReady: null,
    opportunities: null,
    tasksDone: null,
  });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);

    // Read the tasks-done counter from localStorage synchronously —
    // no network round-trip needed.
    const tasksDone = readTasksDone();

    // Fire all three network reads in parallel. Each is best-effort:
    // a single failure surfaces as "—" on that tile, not a page error.
    const [leadsRes, postsRes, oppRes] = await Promise.all([
      api.leads
        .list({ status: "new", limit: 1 })
        .then((r) => r.total)
        .catch((err) => {
          if (!(err instanceof ApiError)) console.warn(err);
          return null;
        }),
      api.content
        .list({ limit: 5 })
        .then((r) => r.length)
        .catch((err) => {
          if (!(err instanceof ApiError)) console.warn(err);
          return null;
        }),
      api.opportunities
        .center()
        .then(
          (r) =>
            (r.content_opportunities?.length ?? 0) +
            (r.ad_opportunities?.length ?? 0),
        )
        .catch((err) => {
          if (!(err instanceof ApiError)) console.warn(err);
          return null;
        }),
    ]);

    setData({
      leadsWaiting: leadsRes,
      postsReady: postsRes,
      opportunities: oppRes,
      tasksDone,
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="day-at-a-glance"
      aria-label="Your day at a glance"
      className={cn(
        "grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4",
        className,
      )}
    >
      <Tile
        href="/grow/leads"
        label="Leads waiting"
        value={data.leadsWaiting}
        unit={data.leadsWaiting === 1 ? "new lead" : "new leads"}
        icon={Inbox}
        loading={loading}
        testId="glance-leads"
      />
      <Tile
        href="/create/social-posts"
        label="Posts ready"
        value={data.postsReady}
        unit={data.postsReady === 1 ? "draft" : "drafts"}
        icon={Send}
        loading={loading}
        testId="glance-posts"
      />
      <Tile
        href="/grow/opportunities"
        label="Opportunities"
        value={data.opportunities}
        unit={data.opportunities === 1 ? "to act on" : "to act on"}
        icon={Lightbulb}
        loading={loading}
        testId="glance-opportunities"
      />
      <Tile
        href="/today"
        label="Tasks done"
        value={data.tasksDone}
        unit="this week"
        icon={CheckCircle2}
        loading={loading}
        testId="glance-tasks"
      />
    </section>
  );
}

// ---------------------------------------------------------------------
//  Tile
// ---------------------------------------------------------------------

function Tile({
  href,
  label,
  value,
  unit,
  icon: Icon,
  loading,
  testId,
}: {
  href: string;
  label: string;
  value: number | null;
  unit: string;
  icon: React.ComponentType<{ className?: string }>;
  loading: boolean;
  testId: string;
}) {
  const display = value === null ? "—" : value.toLocaleString();

  return (
    <Link
      href={href as never}
      data-testid={testId}
      className={cn(
        "group flex flex-col gap-2 rounded-2xl border border-border bg-card px-4 py-3.5 transition-all duration-200",
        "hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm",
      )}
    >
      <div className="flex items-center justify-between text-meta">
        <span className="inline-flex items-center gap-1.5">
          <Icon className="h-3 w-3" />
          {label}
        </span>
        <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-60" />
      </div>
      <div className="flex items-baseline gap-1.5">
        {loading ? (
          <Skeleton className="h-7 w-12" />
        ) : (
          <span
            className="text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl"
            data-testid={`${testId}-value`}
          >
            {display}
          </span>
        )}
        <span className="text-xs text-muted-foreground">{unit}</span>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------
//  Pure helpers (exported for tests)
// ---------------------------------------------------------------------

/**
 * Read the ActionCenter's "done" count from localStorage.
 *
 * ActionCenter persists `{ [id]: { status: "done" | "snoozed" | "pending" } }`
 * under `aicmo.action-center.v1`. We count `done` entries. Returns 0
 * if localStorage is unavailable or the blob is malformed — never throws.
 */
export function readTasksDone(): number {
  if (typeof window === "undefined") return 0;
  try {
    const raw = window.localStorage.getItem(ACTION_CENTER_STORAGE_KEY);
    if (!raw) return 0;
    const parsed = JSON.parse(raw) as Record<
      string,
      { status?: string } | undefined
    >;
    if (!parsed || typeof parsed !== "object") return 0;
    let n = 0;
    for (const v of Object.values(parsed)) {
      if (v && v.status === "done") n += 1;
    }
    return n;
  } catch {
    return 0;
  }
}
