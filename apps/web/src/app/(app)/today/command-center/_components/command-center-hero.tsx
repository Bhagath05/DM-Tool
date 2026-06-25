"use client";

/**
 * Phase 10.4 — AI Command Center hero band.
 *
 *   TODAY · AI Command Center · {timestamp}
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ Your six highest-leverage moves.                             │
 *   │ Each carries Why · Expected Impact · Confidence · Time.      │
 *   └──────────────────────────────────────────────────────────────┘
 *   [● Live]  [⚡ AI-curated]
 *
 * Stateless — the page passes the timestamp; the hero just renders.
 */

import { Sparkles, Zap } from "lucide-react";
import Link from "next/link";

import { BackLink } from "@/components/ui/back-link";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

export interface CommandCenterHeroProps {
  className?: string;
}

export function CommandCenterHero({ className }: CommandCenterHeroProps) {
  const today = formatToday();
  return (
    <header
      data-testid="command-center-hero"
      className={cn("animate-fade-up flex flex-col gap-5", className)}
    >
      {/* Back link — sits above the breadcrumb so the founder always
          has an obvious way out. Explicit destination ("Today") is
          more reliable than browser history (which can land on a
          search engine if the user came from a bookmark). */}
      <BackLink
        href="/today"
        label="Back to Today"
        data-testid="command-center-back"
      />

      <div className="flex flex-wrap items-center gap-2 text-meta">
        <Link
          href={"/today" as never}
          className="transition-colors hover:text-foreground"
        >
          Today
        </Link>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span>AI Command Center</span>
        <span aria-hidden className="text-muted-foreground/40">·</span>
        <span>{today}</span>
      </div>

      <div className="flex flex-col gap-2">
        <h1 className="text-display">Your highest-leverage moves.</h1>
        <p className="text-base text-muted-foreground sm:text-lg">
          Six executions ranked by impact. Each one tells you what to do,
          why, what to expect, and how long it'll take.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusPill tone="ai" size="md" dot icon={Zap}>
          Ready to execute
        </StatusPill>
        <StatusPill tone="neutral" size="md" icon={Sparkles}>
          AI-curated
        </StatusPill>
      </div>
    </header>
  );
}

function formatToday(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}
