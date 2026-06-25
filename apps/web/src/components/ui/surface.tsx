/**
 * Phase 10.0 polish — `<Surface>` primitive.
 *
 * Single source of truth for card-shaped surfaces across the app.
 * Five states map to the visual contract:
 *   - default   neutral card, soft shadow, no hover effect
 *   - hover     same as default + lift-on-hover
 *   - selected  AI border + soft AI ring
 *   - ai        AI-accent gradient backdrop + AI glow shadow
 *   - good / watch / bad
 *               status-colored top border for success/warning/risk
 *
 * Everywhere we used to write
 *   "rounded-lg border border-border bg-card p-5 shadow-sm"
 * we now write `<Surface hover>` — the radii, shadow, border, and
 * transitions stay in lock-step with the design tokens.
 *
 * Keeps the existing `<Card>` shadcn primitive intact for legacy
 * callers — Surface is the upgraded contract for new work and the
 * Phase 10.0 polish surfaces.
 */

import { cn } from "@/lib/utils";

export type SurfaceState =
  | "default"
  | "hover"
  | "selected"
  | "ai"
  | "good"
  | "watch"
  | "bad";

const STATE_CLS: Record<SurfaceState, string> = {
  default: "card-surface",
  hover: "card-surface card-surface-hover",
  selected: "card-surface card-surface-selected",
  ai: "card-surface-ai",
  good: "card-surface card-surface-hover border-t-2 border-t-good",
  watch: "card-surface card-surface-hover border-t-2 border-t-watch",
  bad: "card-surface card-surface-hover border-t-2 border-t-bad",
};

export interface SurfaceProps extends React.HTMLAttributes<HTMLElement> {
  state?: SurfaceState;
  as?: "div" | "article" | "section";
  /** Tailwind padding override; defaults to the card spacing. */
  padding?: "default" | "compact" | "none";
}

const PADDING_CLS = {
  default: "p-6 sm:p-7",
  compact: "p-4 sm:p-5",
  none: "",
} as const;

export function Surface({
  state = "default",
  as: Component = "div",
  padding = "default",
  className,
  ...rest
}: SurfaceProps) {
  return (
    <Component
      {...(rest as React.HTMLAttributes<HTMLDivElement>)}
      className={cn(STATE_CLS[state], PADDING_CLS[padding], className)}
    />
  );
}
