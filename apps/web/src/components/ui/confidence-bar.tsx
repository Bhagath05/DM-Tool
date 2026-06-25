/**
 * Phase 10.0 polish — `<ConfidenceBar>`.
 *
 * Visual confidence indicator. Replaces the bare "82%" text-only
 * treatment with a Linear/Stripe-grade bar:
 *
 *   ▮▮▮▮▮▮▮▮▯▯  82% · High confidence
 *
 * Band tones:
 *   80-100 → ai     (High)
 *   60-79  → ai     (Medium, dimmer)
 *   40-59  → watch  (Low)
 *   <40    → muted  (Speculative)
 *
 * The Constitution forbids shipping confidence < 40 as a CTA; we
 * still render the bar in that case so the founder sees how weak the
 * signal is — the surrounding component decides whether to show or
 * hide the recommendation itself.
 */

import { cn } from "@/lib/utils";

export interface ConfidenceBarProps {
  /** 0–100 */
  value: number;
  /** "lg" doubles the bar height + adds the label below. */
  size?: "sm" | "md" | "lg";
  /** Suppress the inline label when the caller renders one elsewhere. */
  hideLabel?: boolean;
  className?: string;
  "data-testid"?: string;
}

function band(v: number): { label: string; tone: "ai" | "watch" | "muted" } {
  if (v >= 80) return { label: "High confidence", tone: "ai" };
  if (v >= 60) return { label: "Medium confidence", tone: "ai" };
  if (v >= 40) return { label: "Low confidence", tone: "watch" };
  return { label: "Speculative", tone: "muted" };
}

const FILL_CLS: Record<"ai" | "watch" | "muted", string> = {
  ai: "bg-ai",
  watch: "bg-watch",
  muted: "bg-muted-foreground/50",
};

const TRACK_CLS = "bg-muted";

export function ConfidenceBar({
  value,
  size = "md",
  hideLabel = false,
  className,
  "data-testid": testId,
}: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const b = band(clamped);
  const heightCls = size === "sm" ? "h-1" : size === "lg" ? "h-2" : "h-1.5";

  return (
    <div
      data-testid={testId ?? "confidence-bar"}
      data-tone={b.tone}
      className={cn("flex flex-col gap-1.5", className)}
    >
      {!hideLabel && (
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-medium text-foreground/80">{b.label}</span>
          <span className="tabular font-medium text-muted-foreground">
            {clamped}%
          </span>
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Confidence ${clamped} percent — ${b.label}`}
        className={cn(
          "w-full overflow-hidden rounded-full",
          TRACK_CLS,
          heightCls,
        )}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500 ease-out",
            FILL_CLS[b.tone],
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
