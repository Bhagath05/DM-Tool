/**
 * Phase 10.0 — StatusPill primitive.
 *
 * Six tones, one shape. Used for confidence bands, status labels,
 * priority chips, and anywhere we need to communicate "what kind of
 * thing is this" in one glance.
 *
 * Color discipline: each tone maps to ONE of the 5 semantic palette
 * entries (good / watch / bad / ai / neutral) — never raw Tailwind
 * colors. Adding a 7th tone is a Constitution call, not a styling one.
 */

import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type PillTone = "good" | "watch" | "bad" | "ai" | "neutral" | "muted";

const TONE_CLS: Record<PillTone, string> = {
  good: "bg-good-soft text-good-soft-foreground border-good-border",
  watch: "bg-watch-soft text-watch-soft-foreground border-watch-border",
  bad: "bg-bad-soft text-bad-soft-foreground border-bad-border",
  ai: "bg-ai-soft text-ai-soft-foreground border-ai-border",
  neutral: "bg-secondary text-secondary-foreground border-border",
  muted: "bg-muted text-muted-foreground border-transparent",
};

export interface StatusPillProps {
  tone?: PillTone;
  icon?: LucideIcon;
  /** Render a tiny dot before the label — for "live" / "active" feel. */
  dot?: boolean;
  size?: "sm" | "md";
  children: React.ReactNode;
  className?: string;
  "data-testid"?: string;
}

export function StatusPill({
  tone = "neutral",
  icon: Icon,
  dot = false,
  size = "sm",
  children,
  className,
  "data-testid": testId,
}: StatusPillProps) {
  return (
    <span
      data-testid={testId ?? "status-pill"}
      data-tone={tone}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "sm"
          ? "px-2 py-0.5 text-[11px]"
          : "px-2.5 py-1 text-xs",
        TONE_CLS[tone],
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            // Use the foreground color of the tone for the dot so it
            // doesn't disappear against the soft background.
            tone === "good" && "bg-good",
            tone === "watch" && "bg-watch",
            tone === "bad" && "bg-bad",
            tone === "ai" && "bg-ai",
            (tone === "neutral" || tone === "muted") && "bg-muted-foreground",
          )}
        />
      )}
      {Icon && <Icon className="h-3 w-3" />}
      {children}
    </span>
  );
}
