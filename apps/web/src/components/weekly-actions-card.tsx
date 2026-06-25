"use client";

import {
  ArrowRight,
  CalendarCheck,
  Compass,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type ActionPriority,
  type ActionTarget,
  type WeeklyAction,
  type WeeklyPlan,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Phase 2.4 — Weekly Action Rollup.
 *
 * Single-card answer to "What should I do this week?". Pulls a fresh plan
 * from /coach/weekly on mount, then caches it in localStorage for 12 hours
 * so dashboard reloads don't re-bill a Gemini call.
 *
 * Action items are CTAs into the existing studios — content, ads, visuals,
 * campaigns, lead pages, trends, analytics. We never invent new studios;
 * we only point the founder at what already exists.
 */

const CACHE_KEY = "aicmo:weekly-plan:v1";
const CACHE_MAX_AGE_MS = 12 * 60 * 60 * 1000; // 12h

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; plan: WeeklyPlan };

export function WeeklyActionsCard() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      // Read cache unless caller insisted on a fresh fetch.
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({ kind: "ready", plan: cached });
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const plan = await api.coach.weekly();
        writeCache(plan);
        setState({ kind: "ready", plan });
      } catch (e) {
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyWeeklyError(e.message)
              : "Couldn't generate this week's plan.",
        });
      } finally {
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            Planning your week…
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          The AI is looking at your traction, trends, and what&apos;s working
          to figure out where to spend your time this week.
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Couldn&apos;t plan this week
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{state.message}</p>
          <Button onClick={() => void load({ force: true })} disabled={refreshing}>
            {refreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  const { plan } = state;
  const focusAction = plan.actions.find((a) => a.priority === "focus");
  const otherActions = plan.actions.filter((a) => a !== focusAction);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <CalendarCheck className="h-3.5 w-3.5" />
            This week
          </div>
          <CardTitle className="text-base leading-snug">
            {plan.headline}
          </CardTitle>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void load({ force: true })}
          disabled={refreshing}
          title="Regenerate this week's plan"
          className="text-muted-foreground"
        >
          {refreshing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* The single focus */}
        <div className="rounded-md border border-primary/30 bg-primary/5 px-4 py-3">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-primary">
            <Compass className="h-3.5 w-3.5" />
            Your focus this week
          </div>
          <p className="mt-1 text-sm leading-relaxed">{plan.week_focus}</p>
        </div>

        {/* Focus action (if any) */}
        {focusAction && (
          <ActionRow action={focusAction} emphasized />
        )}

        {/* Supporting actions */}
        {otherActions.length > 0 && (
          <div className="space-y-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Also this week
            </div>
            <div className="space-y-2">
              {otherActions.map((a, i) => (
                <ActionRow key={i} action={a} />
              ))}
            </div>
          </div>
        )}

        {/* Skip list */}
        {plan.skip_this_week.length > 0 && (
          <div className="rounded-md border border-dashed bg-muted/30 px-3 py-2.5">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <X className="h-3.5 w-3.5" />
              Skip this week
            </div>
            <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-muted-foreground">
              {plan.skip_this_week.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Provenance — collapsed by default */}
        {plan.signals_used.length > 0 && (
          <details className="rounded-md border bg-muted/20 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              <Sparkles className="mr-1 inline h-3 w-3" />
              How this was built
            </summary>
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground">
              {plan.signals_used.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <ArrowRight className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
            <div className="mt-2 text-[10px] text-muted-foreground">
              Generated {formatRelativeTime(plan.generated_at)}
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------- subcomponents ----------------

function ActionRow({
  action,
  emphasized,
}: {
  action: WeeklyAction;
  emphasized?: boolean;
}) {
  const href = HREF_BY_TARGET[action.cta_target] ?? "/dashboard";
  const palette = PRIORITY_PALETTE[action.priority];

  return (
    <div
      className={cn(
        "grid gap-3 rounded-md border bg-card px-3 py-3 sm:grid-cols-[1fr_auto]",
        emphasized && "border-primary/20 bg-primary/5",
      )}
    >
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
              palette,
            )}
          >
            {labelForPriority(action.priority)}
          </span>
          <span className="text-[10px] text-muted-foreground">
            · {action.estimated_time}
          </span>
        </div>
        <div className="text-sm font-medium leading-snug">{action.action_title}</div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {action.why}
        </p>
      </div>
      <div className="flex items-start sm:items-center">
        <Button asChild size="sm" variant={emphasized ? "default" : "outline"}>
          <Link href={href as never}>
            {action.cta_label}
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

// ---------------- lookup tables + helpers ----------------

const HREF_BY_TARGET: Record<ActionTarget, string> = {
  content: "/content",
  ads: "/ads",
  visuals: "/visuals",
  campaigns: "/campaigns",
  lead_pages: "/landing-pages",
  trends: "/trends",
  analytics: "/analytics",
  profile: "/onboarding/profile",
};

const PRIORITY_PALETTE: Record<ActionPriority, string> = {
  focus: "bg-primary/15 text-primary",
  important: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  stretch: "bg-muted text-muted-foreground",
};

function labelForPriority(p: ActionPriority): string {
  switch (p) {
    case "focus":
      return "Focus";
    case "important":
      return "Important";
    case "stretch":
      return "If time";
  }
}

function friendlyWeeklyError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("409") || lowered.includes("onboarding")) {
    return "Finish business onboarding first — the weekly plan needs your profile to know what to recommend.";
  }
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI is under heavy load. Try again in a moment.";
  }
  return "Something went wrong building your plan. Try again — the AI sometimes hiccups on the first call.";
}

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleString();
}

// ---------------- 12h client cache ----------------

function readCache(): WeeklyPlan | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { savedAt: number; plan: WeeklyPlan };
    if (Date.now() - parsed.savedAt > CACHE_MAX_AGE_MS) return null;
    return parsed.plan;
  } catch {
    return null;
  }
}

function writeCache(plan: WeeklyPlan): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ savedAt: Date.now(), plan }),
    );
  } catch {
    /* quota — ignore */
  }
}
