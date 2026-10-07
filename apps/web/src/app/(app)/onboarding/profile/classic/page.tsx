/**
 * Phase 6.2 — the classic form-heavy onboarding is consolidated into the
 * canonical conversational flow at /onboarding/profile.
 *
 * Kept as a redirect (not deleted) because the route was a documented rollback
 * fallback. The legacy wizard COMPONENT is preserved untouched at
 * ../_components/wizard, so it can be re-mounted instantly if a rollback is ever
 * needed — only this duplicate route is retired.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function OnboardingClassicLegacyRoute() {
  redirect("/onboarding/profile");
}
