"use client";

/**
 * Topbar pill that toggles Simple ↔ Professional view mode.
 *
 * Simple Mode (default): plain-language explanations, technical details
 * collapsed everywhere they appear.
 *
 * Professional Mode: same plain-language is still primary (Constitution),
 * but technical-detail disclosures start expanded and deep-dive tables
 * on the analytics page render inline instead of behind a button.
 *
 * Persisted via lib/view-mode.ts so the choice survives reload.
 */

import { useViewMode } from "@/lib/use-view-mode";
import { cn } from "@/lib/utils";

export function ViewModeToggle() {
  const { mode, setMode } = useViewMode();

  return (
    <div
      role="radiogroup"
      aria-label="View mode"
      data-testid="view-mode-toggle"
      className="inline-flex items-center rounded-md border border-border bg-background p-0.5 text-xs"
    >
      <button
        type="button"
        role="radio"
        aria-checked={mode === "simple"}
        onClick={() => setMode("simple")}
        data-testid="view-mode-simple"
        className={cn(
          "rounded-sm px-2 py-1 font-medium transition-colors",
          mode === "simple"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        Simple
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === "professional"}
        onClick={() => setMode("professional")}
        data-testid="view-mode-professional"
        className={cn(
          "rounded-sm px-2 py-1 font-medium transition-colors",
          mode === "professional"
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        Pro
      </button>
    </div>
  );
}
