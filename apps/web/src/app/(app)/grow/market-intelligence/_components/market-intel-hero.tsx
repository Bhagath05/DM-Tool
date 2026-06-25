"use client";

/**
 * Phase 10.3c — Market Intelligence page hero.
 *
 *   GROW · Market Intelligence
 *   ┌──────────────────────────────────────────────────────┐
 *   │ Your external radar                                  │
 *   │ Opportunities, competitors, trends, signals — all in │
 *   │ one place.                                           │
 *   └──────────────────────────────────────────────────────┘
 *   [● Live]   [⚡ AI-curated]
 *
 * Reads no API state directly — `signalsTracked` is derived by the
 * page from the data it already loads for the other sections, and
 * passed in. Keeps the hero stateless + cheap to render.
 */

import { Radar, Sparkles } from "lucide-react";

import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export interface MarketIntelHeroProps {
  signalsTracked: number | null;
  className?: string;
}

export function MarketIntelHero({
  signalsTracked,
  className,
}: MarketIntelHeroProps) {
  return (
    <header
      data-testid="market-intel-hero"
      className={cn("animate-fade-up flex flex-col gap-5", className)}
    >
      <div className="flex flex-wrap items-center gap-2 text-meta">
        <span>Grow</span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span>Market Intelligence</span>
      </div>

      <div className="flex flex-col gap-2">
        <h1 className="text-display">Your external radar.</h1>
        <p className="text-base text-muted-foreground sm:text-lg">
          Opportunities, competitors, trends, signals — all in one place.
          Refreshed automatically; act when something moves.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone="ai" size="md" dot icon={Radar}>
          Live radar
        </StatusPill>
        <StatusPill tone="neutral" size="md" icon={Sparkles}>
          AI-curated
        </StatusPill>
        {typeof signalsTracked === "number" && signalsTracked > 0 && (
          <StatusPill
            tone="muted"
            size="md"
            data-testid="market-intel-hero-signals"
          >
            {signalsTracked} signal{signalsTracked === 1 ? "" : "s"} tracked
          </StatusPill>
        )}
      </div>
    </header>
  );
}
