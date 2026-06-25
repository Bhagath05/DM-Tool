/**
 * Phase 10.0 polish — `<TrendDelta>`.
 *
 * Arrow + value badge for relative performance — "3× cheaper" /
 * "40% lift" / "-18% CPL" — colored against the semantic palette.
 * Used wherever the card surfaces a comparative number we want the
 * eye to land on.
 */

import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { cn } from "@/lib/utils";

export interface TrendDeltaProps {
  /** Plain-language label. e.g. "3.0× cheaper". */
  label: string;
  /**
   * Semantic direction. `up` = positive outcome for the business
   * (more leads, more revenue). `down` = negative (more cost, more
   * waste). The arrow follows the semantic direction, not the
   * literal arithmetic.
   */
  direction: "up" | "down" | "neutral";
  size?: "sm" | "md";
  className?: string;
  "data-testid"?: string;
}

export function TrendDelta({
  label,
  direction,
  size = "sm",
  className,
  "data-testid": testId,
}: TrendDeltaProps) {
  const Arrow = direction === "down" ? ArrowDownRight : ArrowUpRight;
  return (
    <span
      data-testid={testId ?? "trend-delta"}
      data-direction={direction}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-medium",
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        direction === "up" &&
          "bg-good-soft text-good-soft-foreground border-good-border",
        direction === "down" &&
          "bg-bad-soft text-bad-soft-foreground border-bad-border",
        direction === "neutral" &&
          "bg-muted text-muted-foreground border-transparent",
        className,
      )}
    >
      <Arrow className="h-3 w-3" aria-hidden />
      {label}
    </span>
  );
}
