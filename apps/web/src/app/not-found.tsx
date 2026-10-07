/**
 * Phase 6.1 — branded 404.
 *
 * Next App Router renders this for any unmatched URL (within the root layout).
 * Calm, token-based, responsive, and accessible: a clear message plus a primary
 * "Go to Today" action and a secondary way home. No new colors or libraries.
 */

import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main
      role="main"
      className="flex min-h-[70vh] flex-col items-center justify-center gap-6 px-6 py-16 text-center"
    >
      <div className="flex flex-col items-center gap-3">
        <span
          aria-hidden
          className="flex h-12 w-12 items-center justify-center rounded-xl bg-ai-soft text-lg font-semibold text-ai-soft-foreground"
        >
          404
        </span>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          We couldn&apos;t find that page
        </h1>
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          The page may have moved or never existed. Your workspace is still here —
          let&apos;s get you back to something useful.
        </p>
      </div>
      <div className="flex flex-col items-center gap-3 sm:flex-row">
        <Button asChild>
          <Link href="/today">Go to Today</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/ai">Open Marketing Brain</Link>
        </Button>
      </div>
    </main>
  );
}
