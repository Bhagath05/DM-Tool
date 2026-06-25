/**
 * Phase 10.0 — SectionHeading primitive.
 *
 * Eyebrow + heading + optional description + optional CTA, used to
 * frame every band on the Overview page. Keeps the rhythm consistent
 * across the page so the eye learns to scan one way.
 */

import { cn } from "@/lib/utils";

export interface SectionHeadingProps {
  /** Short uppercase eyebrow above the heading. Optional. */
  eyebrow?: React.ReactNode;
  heading: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned action — usually a button or pill. */
  action?: React.ReactNode;
  size?: "md" | "lg";
  className?: string;
  "data-testid"?: string;
}

export function SectionHeading({
  eyebrow,
  heading,
  description,
  action,
  size = "md",
  className,
  "data-testid": testId,
}: SectionHeadingProps) {
  return (
    <div
      data-testid={testId ?? "section-heading"}
      className={cn(
        "flex items-end justify-between gap-4",
        className,
      )}
    >
      <div className="flex flex-col gap-1.5">
        {eyebrow && (
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ai-soft-foreground"
            data-testid="section-heading-eyebrow"
          >
            {eyebrow}
          </span>
        )}
        <h2
          className={cn(
            "font-semibold tracking-tight",
            size === "lg" ? "text-2xl" : "text-lg",
          )}
        >
          {heading}
        </h2>
        {description && (
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}
