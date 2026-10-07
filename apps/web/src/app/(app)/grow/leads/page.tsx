/**
 * Phase 6.1 — legacy route shim. Canonical route is `/leads`.
 *
 * Kept as a redirect (not deleted) because existing cards/CTAs still deep-link
 * here; query params are forwarded so those links keep working.
 */

import { redirect } from "next/navigation";

import { legacyTarget } from "@/lib/legacy-redirect";

export const dynamic = "force-dynamic";

export default async function LegacyRedirectRoute({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  redirect(legacyTarget("/leads", await searchParams));
}
