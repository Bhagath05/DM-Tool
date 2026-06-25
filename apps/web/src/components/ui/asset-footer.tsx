"use client";

/**
 * Phase 10.5 — AssetFooter (Founder Rule enforcement).
 *
 * Every generated asset across the studios (social post, ad, reel
 * script, future poster) renders this footer beneath its preview.
 * Each instance MUST answer the four founder questions:
 *
 *   1. Why this works         → whyItWorks (the LLM's reason)
 *   2. Expected outcome       → expectedOutcome (leads, reach, CPL)
 *   3. Best time to publish   → bestTimeToPublish (window or "Always-on")
 *   4. Estimated effort       → estimatedEffort (Quick win / Some / Bigger)
 *
 * Constitution discipline: refuses to render if any required field is
 * empty. Better an honest "footer suppressed — incomplete" warning in
 * dev than shipping a card that fails the Founder Rule.
 *
 * Optional confidence% renders a small ConfidenceBar inline — surfaces
 * the calibration the backend already returns on every recommendation.
 */

import { Clock, Sparkles, Target, Wrench } from "lucide-react";

import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { cn } from "@/lib/utils";

export interface AssetFooterProps {
  whyItWorks: string;
  expectedOutcome: string;
  bestTimeToPublish: string;
  estimatedEffort: string;
  /** Optional 0-100. When present, renders a slim ConfidenceBar. */
  confidence?: number;
  className?: string;
  "data-testid"?: string;
}

/**
 * The four field labels are intentionally fixed (not props) so every
 * asset across the app surfaces the same wording for the same field.
 * Founders learn the pattern once.
 */
const FIELD_META = [
  { key: "whyItWorks", label: "Why this works", icon: Sparkles },
  { key: "expectedOutcome", label: "Expected outcome", icon: Target },
  { key: "bestTimeToPublish", label: "Best time", icon: Clock },
  { key: "estimatedEffort", label: "Estimated effort", icon: Wrench },
] as const;

export function AssetFooter({
  whyItWorks,
  expectedOutcome,
  bestTimeToPublish,
  estimatedEffort,
  confidence,
  className,
  "data-testid": testId,
}: AssetFooterProps) {
  // Constitution gate: refuse to render with empty required fields.
  // Dev console gets a clear warning so we catch silent gaps early.
  if (
    !whyItWorks.trim() ||
    !expectedOutcome.trim() ||
    !bestTimeToPublish.trim() ||
    !estimatedEffort.trim()
  ) {
    if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
      console.warn(
        "<AssetFooter> suppressed — one or more required fields are empty:",
        { whyItWorks, expectedOutcome, bestTimeToPublish, estimatedEffort },
      );
    }
    return null;
  }

  const values: Record<(typeof FIELD_META)[number]["key"], string> = {
    whyItWorks,
    expectedOutcome,
    bestTimeToPublish,
    estimatedEffort,
  };

  return (
    <footer
      data-testid={testId ?? "asset-footer"}
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-border bg-muted/40 p-4",
        className,
      )}
    >
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FIELD_META.map(({ key, label, icon: Icon }) => (
          <li key={key} className="flex flex-col gap-1">
            <span className="inline-flex items-center gap-1.5 text-meta">
              <Icon className="h-3 w-3" />
              {label}
            </span>
            <span className="text-sm text-foreground">{values[key]}</span>
          </li>
        ))}
      </ul>

      {typeof confidence === "number" && (
        <div className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
          <div className="flex items-center justify-between">
            <span className="text-meta">Confidence</span>
            <span className="text-xs font-semibold tabular-nums text-foreground">
              {confidence}%
            </span>
          </div>
          <ConfidenceBar value={confidence} />
        </div>
      )}
    </footer>
  );
}
