"use client";

import { AlertTriangle, BookOpen, TrendingDown } from "lucide-react";

import type { EvidenceGrounding } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Phase 7.18 — Coach evidence provenance.
 *
 * A calm "Why this recommendation?" disclosure that traces an AI Coach
 * recommendation back to the business's own evidence. Reuses the same
 * collapsed-<details> idiom as the "Why this score?" / "How this was built"
 * expanders already on the Coach cards — no new UI language.
 *
 * Honesty rules (match the server contract):
 *   - `grounding` absent  → render NOTHING. We never imply we checked when the
 *     server attached no provenance (e.g. an older/cached payload).
 *   - `insufficient_evidence` / no beliefs → say so plainly: this is a
 *     hypothesis to test, not a proven result. (The "missing evidence" state.)
 *   - `grounded` → show the supporting beliefs with their SERVER-DERIVED
 *     confidence + freshness, and surface contradictory findings as "do not
 *     rely on". The numbers come from the server, never the model.
 */
export function EvidenceProvenance({
  grounding,
  className,
}: {
  grounding?: EvidenceGrounding | null;
  className?: string;
}) {
  if (!grounding) return null;

  const beliefs = grounding.beliefs ?? [];
  const contradictions = grounding.contradictions ?? [];
  const grounded = grounding.status === "grounded" && beliefs.length > 0;

  return (
    <details className={cn("rounded-md border bg-muted/20 px-3 py-2", className)}>
      <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <BookOpen className="mr-1 inline h-3 w-3" />
        Why this recommendation?
      </summary>

      <div className="mt-2 space-y-3 text-[11px] text-muted-foreground">
        {grounded ? (
          <div className="space-y-1.5">
            <p className="font-medium text-foreground/80">
              Based on what your own results have taught us:
            </p>
            <ul className="space-y-1.5">
              {beliefs.map((b, i) => (
                <li
                  key={i}
                  className="rounded border bg-card/50 px-2 py-1.5"
                  data-testid="supporting-belief"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-foreground/90">{b.statement}</span>
                    <ConfidenceChip value={b.confidence} />
                  </div>
                  {b.freshness_reason && (
                    <div className="mt-0.5 text-[10px] leading-snug text-muted-foreground">
                      {b.freshness_reason}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p data-testid="insufficient-evidence">
            No validated results yet — this is a smart starting point to test,
            not something your own numbers have proven. We&apos;ll ground it as
            soon as your campaigns produce evidence.
          </p>
        )}

        {contradictions.length > 0 && (
          <div data-testid="contradictions">
            <p className="flex items-center gap-1 font-medium text-amber-600 dark:text-amber-400">
              <AlertTriangle className="h-3 w-3" />
              Findings that complicate this
            </p>
            <ul className="mt-1 space-y-1">
              {contradictions.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <TrendingDown className="mt-0.5 h-2.5 w-2.5 shrink-0" />
                  <span>
                    {c.statement}{" "}
                    <span className="opacity-70">
                      (newer results question this — we don&apos;t rely on it)
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {grounding.note && (
          <p className="text-[10px] italic leading-snug opacity-80">
            {grounding.note}
          </p>
        )}
      </div>
    </details>
  );
}

/** Small, non-technical confidence chip. Tone tracks the Constitution bands. */
function ConfidenceChip({ value }: { value: number }) {
  const tone =
    value >= 80
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
      : value >= 60
        ? "bg-teal-500/15 text-teal-700 dark:text-teal-300"
        : "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
        tone,
      )}
      title="How confident your past results make us — set by the system, not the AI"
    >
      {value}% sure
    </span>
  );
}
