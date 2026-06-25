"use client";

/**
 * Phase 10.1 — /settings index.
 *
 * Settings doesn't have a canonical overview; the canonical entry is
 * the Organization profile. This page exists only to redirect there
 * so the sidebar's "Settings" link lands on a real page rather than
 * an empty index.
 *
 * Why client-side redirect (router.replace) instead of the server-side
 * `redirect()` from next/navigation:
 *
 *   The two layouts above this page — `(app)/layout.tsx` and
 *   `settings/layout.tsx` — are both client components (`"use client"`).
 *   When a server-component page calls `redirect()` while sitting
 *   beneath a client-component layout, Next.js App Router has to mix
 *   server-side throw semantics with client streaming. In practice that
 *   manifests as a "Rendered more hooks than during the previous render"
 *   error during hydration — the client tree's hook count diverges from
 *   what was streamed.
 *
 *   Making this page a client component with a `useEffect` redirect
 *   keeps the whole subtree client-rendered consistently. The visible
 *   gap is one paint frame (effects flush right after first commit),
 *   which is invisible at typical render speeds.
 *
 *   The returned `null` is a safe placeholder — the layout's empty
 *   content slot renders, then the effect fires `router.replace`
 *   instantly, and the founder never sees a flash.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SettingsIndex() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/settings/organization");
  }, [router]);
  return null;
}
