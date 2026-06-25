"use client";

/**
 * (app) segment error boundary.
 *
 * Catches client-side render errors within the app shell so a single bad
 * component degrades to a readable panel instead of white-screening the
 * whole dashboard. In development it prints the error name, message, and
 * stack inline so the failing component is identifiable from a screenshot.
 */

import { useEffect } from "react";

export default function AppSegmentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Full object (incl. componentStack when present) to the console.
    console.error("[AppSegmentError]", error);
  }, [error]);

  const isDev = process.env.NODE_ENV !== "production";

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 py-12">
      <h2 className="text-xl font-semibold text-foreground">
        Something broke on this page
      </h2>
      <p className="text-sm text-muted-foreground">
        The dashboard hit a client-side error. Your data is safe — this is a
        rendering issue, not a data loss.
      </p>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background"
        >
          Try again
        </button>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium"
        >
          Reload page
        </button>
      </div>

      {isDev && (
        <div className="mt-2 flex flex-col gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-4">
          <p className="font-mono text-sm font-semibold text-destructive">
            {error.name}: {error.message}
          </p>
          {error.digest && (
            <p className="font-mono text-xs text-muted-foreground">
              digest: {error.digest}
            </p>
          )}
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground/80">
            {error.stack}
          </pre>
        </div>
      )}
    </div>
  );
}
