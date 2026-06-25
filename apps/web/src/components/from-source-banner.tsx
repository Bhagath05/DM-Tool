"use client";

/**
 * FromSourceBanner — auto-mounted "Back to {source}" surface.
 *
 * Reads the `?from=` query param on every page render. When the slug
 * matches a registered BackSource (lib/back-source.ts), renders a
 * <BackLink> at the top of the page. When the slug is missing or
 * unknown, renders nothing — silent default.
 *
 * Mounted once at the (app)/layout.tsx level so every page in the
 * authenticated app surface gets smart back navigation for free.
 * Sub-pages with hard-coded back links (e.g. /today/command-center)
 * still render their own explicit one — both work together because
 * the explicit one is in the page hero (below this banner).
 */

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { BackLink } from "@/components/ui/back-link";
import { resolveBackSource } from "@/lib/back-source";

/**
 * Inner component — uses `useSearchParams` which must be wrapped in
 * a Suspense boundary per Next.js 15 App-Router rules. Otherwise the
 * whole route gets pulled into client-side rendering.
 */
function FromSourceBannerInner() {
  const params = useSearchParams();
  const from = params?.get("from") ?? null;
  const source = resolveBackSource(from);

  if (!source) return null;

  return (
    <div
      data-testid="from-source-banner"
      className="mx-auto w-full max-w-6xl"
    >
      <BackLink
        href={source.href}
        label={source.label}
        data-testid="from-source-banner-link"
      />
    </div>
  );
}

export function FromSourceBanner() {
  return (
    <Suspense fallback={null}>
      <FromSourceBannerInner />
    </Suspense>
  );
}
