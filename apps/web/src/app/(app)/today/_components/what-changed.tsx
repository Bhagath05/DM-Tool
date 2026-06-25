"use client";

/**
 * Phase 10.3b — Section 5: What Changed Since You Were Last Here.
 *
 *   ✓ Lead cost dropped to ₹104 (down ₹16 — keep current ads running)
 *   ⚠ 2 competitors started running discount ads
 *   ✓ New lead from Mumbai enrolled overnight
 *
 * Derivation (no new APIs):
 *
 *   - Performance diagnostics that read as deltas (winner / waste /
 *     audience_winner) → friendly one-liner.
 *   - Lead count delta vs the last visit (read from localStorage,
 *     persisted by THIS component on every successful load).
 *
 * The "last visit" cache is the only state this component writes.
 * It's a single timestamp + previously-seen lead count under
 * `aicmo.today.last-visit.v1`. Defaults to "first visit" the first
 * time a founder lands here.
 *
 * Empty state is honest: when nothing genuinely changed, we say so
 * instead of inventing fake activity. CLAUDE.md Constitution: never
 * surface a metric without context.
 */

import { ArrowUpRight, Clock, MinusCircle, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { translateOverview } from "@/lib/performance-translator";
import { cn } from "@/lib/utils";

const LAST_VISIT_STORAGE_KEY = "aicmo.today.last-visit.v1";
const MAX_ITEMS = 4;

type Tone = "good" | "watch" | "neutral";

interface ChangeItem {
  id: string;
  tone: Tone;
  title: string;
  detail: string | null;
  href: string;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; items: ChangeItem[] };

export function WhatChanged({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    const items: ChangeItem[] = [];
    const lastVisit = readLastVisit();

    const [leadsResult, overviewResult] = await Promise.allSettled([
      api.leads.list({ limit: 1 }),
      api.performance.overview(),
    ]);

    if (leadsResult.status === "fulfilled") {
      const currentCount = leadsResult.value.total ?? 0;
      const leadItem = deriveLeadDelta(currentCount, lastVisit);
      if (leadItem) items.push(leadItem);
      writeLastVisit({
        timestamp: new Date().toISOString(),
        leadCount: currentCount,
      });
    } else if (!(leadsResult.reason instanceof ApiError)) {
      console.warn(leadsResult.reason);
    }

    if (overviewResult.status === "fulfilled") {
      const cards = translateOverview(overviewResult.value);
      for (const c of cards.cards) {
        if (items.length >= MAX_ITEMS) break;
        const item = perfCardToChange(c);
        if (item) items.push(item);
      }
    } else if (!(overviewResult.reason instanceof ApiError)) {
      console.warn(overviewResult.reason);
    }

    setState({ kind: "ready", items });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="what-changed"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            Since you were last here
          </span>
        }
        heading="What changed"
        description="Recent shifts worth your attention — the new things since your last visit."
      />

      {state.kind === "loading" && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-xl" />
          ))}
        </div>
      )}

      {state.kind === "ready" && state.items.length === 0 && (
        <EmptyState
          icon={MinusCircle}
          title="Nothing new since your last visit"
          description="When leads, performance, or competitor signals shift, you'll see them here."
          data-testid="what-changed-empty"
        />
      )}

      {state.kind === "ready" && state.items.length > 0 && (
        <ul className="flex flex-col gap-2" data-testid="what-changed-list">
          {state.items.map((item) => (
            <ChangeRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row + icon mapping
// ---------------------------------------------------------------------

function ChangeRow({ item }: { item: ChangeItem }) {
  const Icon =
    item.tone === "good"
      ? TrendingUp
      : item.tone === "watch"
        ? Sparkles
        : MinusCircle;
  return (
    <li>
      <Link
        href={item.href as never}
        data-testid={`what-changed-row-${item.id}`}
        className={cn(
          "group flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 transition-all duration-200",
          "hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm",
        )}
      >
        <span
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
            item.tone === "good" && "bg-good/15 text-good-foreground",
            item.tone === "watch" && "bg-watch/15 text-watch-foreground",
            item.tone === "neutral" && "bg-muted text-muted-foreground",
          )}
          aria-hidden
        >
          <Icon className="h-4 w-4" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium text-foreground">
            {item.title}
          </span>
          {item.detail && (
            <span className="truncate text-xs text-muted-foreground">
              {item.detail}
            </span>
          )}
        </span>
        <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
      </Link>
    </li>
  );
}

// ---------------------------------------------------------------------
//  Pure logic (exported for tests)
// ---------------------------------------------------------------------

export interface LastVisitSnapshot {
  timestamp: string;
  leadCount: number;
}

export function readLastVisit(): LastVisitSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(LAST_VISIT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LastVisitSnapshot>;
    if (typeof parsed?.timestamp !== "string") return null;
    if (typeof parsed?.leadCount !== "number") return null;
    return parsed as LastVisitSnapshot;
  } catch {
    return null;
  }
}

export function writeLastVisit(snapshot: LastVisitSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      LAST_VISIT_STORAGE_KEY,
      JSON.stringify(snapshot),
    );
  } catch {
    /* persistence is best-effort */
  }
}

export function deriveLeadDelta(
  currentCount: number,
  lastVisit: LastVisitSnapshot | null,
): ChangeItem | null {
  if (lastVisit === null) {
    // First visit — no delta to surface. We DON'T emit "you have N
    // leads" here because that's a static snapshot, not a change.
    return null;
  }
  const delta = currentCount - lastVisit.leadCount;
  if (delta <= 0) return null;
  return {
    id: "lead-delta",
    tone: "good",
    title:
      delta === 1
        ? "1 new lead since your last visit"
        : `${delta} new leads since your last visit`,
    detail: "Contact the warmest first — Get More Leads has the ranking.",
    href: "/grow/leads",
  };
}

/**
 * Turn a performance card into a "what changed" row, IF the card
 * reads as a recent shift rather than steady-state info. Returns
 * null for cards that don't carry delta meaning.
 *
 * The mapping is intentionally conservative — better to surface
 * fewer high-quality changes than spam the feed with steady-state
 * diagnostics framed as "news".
 */
function perfCardToChange(
  card: ReturnType<typeof translateOverview>["cards"][number],
): ChangeItem | null {
  // Only kinds that genuinely represent change. Steady-state cards
  // (e.g. `info`, `awaiting_data`) are excluded from "what changed".
  const SHIFT_KINDS = new Set([
    "winner",
    "audience_winner",
    "concept_winner",
    "creative_dna",
    "budget_waste",
    "audience_loser",
  ]);
  if (!SHIFT_KINDS.has(card.kind)) return null;

  const tone: Tone =
    card.kind === "budget_waste" || card.kind === "audience_loser"
      ? "watch"
      : "good";

  // `whatIsHappening` is the "this is the news" line; `recommendation`
  // is the action. The Constitution contract guarantees both are
  // non-empty by the time they reach here.
  return {
    id: card.id,
    tone,
    title: card.whatIsHappening,
    detail: card.recommendation,
    href: "/results",
  };
}
