"use client";

/**
 * AI Marketing Health — the "how healthy is my marketing, and what do I fix
 * first?" layer of the AI headquarters.
 *
 * Reads GET /advisor/health, which is computed from this brand's real rows
 * (no LLM, so it renders instantly and can't invent a number). Every score
 * carries the constitution contract: what it means, why it matters, whether
 * it's good or bad, and what to do next — in plain English, no jargon.
 *
 * Renders nothing when there's no profile yet; the page's own onboarding
 * prompts already cover that state.
 */

import { ChevronDown, HeartPulse } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type HealthScore, type MarketingHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

const TONE: Record<HealthScore["status"], { dot: string; bar: string }> = {
  good: { dot: "bg-good", bar: "bg-good" },
  watch: { dot: "bg-watch", bar: "bg-watch" },
  bad: { dot: "bg-bad", bar: "bg-bad" },
};

export function MarketingHealthCard() {
  const [data, setData] = useState<MarketingHealth | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    // Wrapped in an async IIFE so a *synchronous* throw (e.g. the endpoint
    // not being available) is caught too — this is a bonus panel and must
    // never take the page down with it.
    void (async () => {
      try {
        const d = await api.advisor.health();
        if (alive) setData(d);
      } catch {
        /* leave the panel hidden */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (!data || data.scores.length === 0) return null;

  return (
    <section
      className="rounded-xl border border-border bg-background p-4 sm:p-5"
      data-testid="marketing-health"
    >
      <div className="mb-3 flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <HeartPulse className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">How your marketing is doing</h2>
            <span
              className={cn("h-2 w-2 rounded-full", TONE[data.overall_status].dot)}
              aria-hidden
            />
            <span className="text-sm font-semibold tabular-nums">
              {data.overall}%
            </span>
          </div>
          <p className="text-xs text-muted-foreground">{data.headline}</p>
        </div>
      </div>

      <ul className="flex flex-col divide-y divide-border">
        {data.scores.map((s) => {
          const isOpen = open === s.key;
          const isFocus = s.key === data.focus_key;
          return (
            <li key={s.key} data-testid={`health-${s.key}`}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : s.key)}
                aria-expanded={isOpen}
                className="flex w-full items-center gap-3 py-2.5 text-left"
              >
                <span
                  className={cn("h-2 w-2 shrink-0 rounded-full", TONE[s.status].dot)}
                  aria-hidden
                />
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="truncate text-sm">{s.label}</span>
                  {isFocus && (
                    <span className="shrink-0 rounded-full bg-ai-soft px-1.5 py-0.5 text-[10px] font-medium text-ai-soft-foreground">
                      Start here
                    </span>
                  )}
                </span>
                <span className="hidden w-24 shrink-0 sm:block">
                  <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
                    <span
                      className={cn("block h-full rounded-full", TONE[s.status].bar)}
                      style={{ width: `${s.score}%` }}
                    />
                  </span>
                </span>
                <span className="w-9 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                  {s.score}%
                </span>
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                    isOpen && "rotate-180",
                  )}
                />
              </button>

              {isOpen && (
                <div className="flex flex-col gap-2 pb-3 pl-5 pr-2 text-xs">
                  <p>{s.explanation}</p>
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">Why this matters: </span>
                    {s.why}
                  </p>
                  <p className="rounded-md bg-ai-soft px-2.5 py-1.5 text-ai-soft-foreground">
                    <span className="font-medium">Do this next: </span>
                    {s.recommendation}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
