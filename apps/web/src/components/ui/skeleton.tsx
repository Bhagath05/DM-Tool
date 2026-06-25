/**
 * Phase 10.0 — Skeleton primitive.
 *
 * CSS-only shimmer (see globals.css `.skeleton`). Respects
 * `prefers-reduced-motion`. Use a wrapping `<SkeletonGroup>` to
 * stagger multiple skeletons via the natural animation; we don't
 * mess with per-element delays — keeps the dependency surface
 * small and the visual calm.
 */

import { cn } from "@/lib/utils";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Tailwind size/shape utilities — e.g. "h-4 w-32". */
  className?: string;
}

export function Skeleton({ className, ...rest }: SkeletonProps) {
  return (
    <div
      aria-hidden
      data-testid="skeleton"
      className={cn("skeleton rounded-md", className)}
      {...rest}
    />
  );
}

/**
 * A small composition helper for the common "stack of lines" pattern.
 * Pass `lines={4}` for a 4-line text skeleton; the last line is
 * intentionally narrower to feel like real text.
 */
export function SkeletonLines({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn("h-3", i === lines - 1 ? "w-2/3" : "w-full")}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Phase 10.0 polish — named compositions.
//
//  These keep individual page skeletons honest: instead of one-off
//  shimmer placeholders that drift visually, every page reaches for
//  one of these and the loading state becomes consistent across the
//  product.
// ---------------------------------------------------------------------

/** Tile-shaped card skeleton — Executive Summary, dashboard tiles. */
export function SkeletonTile({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton-tile"
      className={cn(
        "card-surface flex flex-col gap-3 p-5",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-7 w-7 rounded-lg" />
      </div>
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

/** Row-shaped skeleton — Quick Wins / Action Center items. */
export function SkeletonRow({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton-row"
      className={cn(
        "flex items-center gap-4 rounded-xl border border-border/70 bg-card px-4 py-3.5",
        className,
      )}
    >
      <Skeleton className="h-8 w-8 rounded-full" />
      <Skeleton className="h-4 flex-1" />
      <Skeleton className="h-5 w-24" />
    </div>
  );
}

/** Full recommendation-card skeleton — `<AiRecommendation>` shape. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton-card"
      className={cn("card-surface flex flex-col gap-5 p-6", className)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton className="h-7 w-7 rounded-lg" />
          <Skeleton className="h-3 w-32" />
        </div>
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>
      <Skeleton className="h-6 w-2/3" />
      <div className="flex flex-wrap gap-1.5">
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-5 w-20 rounded-full" />
        <Skeleton className="h-5 w-24 rounded-full" />
      </div>
      <SkeletonLines lines={3} />
    </div>
  );
}

/** Table-shaped skeleton — listing pages (leads, library, etc). */
export function SkeletonTable({
  rows = 5,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div
      data-testid="skeleton-table"
      className={cn("card-surface overflow-hidden", className)}
    >
      <div className="flex items-center gap-4 border-b border-border/60 px-5 py-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 flex-1" />
        <Skeleton className="h-3 w-16" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 border-b border-border/40 px-5 py-3 last:border-b-0"
        >
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-3 w-16" />
        </div>
      ))}
    </div>
  );
}

/** Upload dropzone skeleton. */
export function SkeletonUpload({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton-upload"
      className={cn(
        "flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed border-border bg-muted/30 px-6 py-10",
        className,
      )}
    >
      <Skeleton className="h-12 w-12 rounded-full" />
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-3 w-64" />
      <Skeleton className="h-9 w-28 rounded-lg" />
    </div>
  );
}
