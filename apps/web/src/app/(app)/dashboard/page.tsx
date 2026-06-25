/**
 * Phase 10.3 — /dashboard collapses into /today.
 *
 * /today is the new front door (Founder Simplification Pass). Legacy
 * /dashboard URLs (the original `suggested_route` value post-onboarding,
 * any persisted bookmarks) land here and 308-redirect onward.
 *
 * Chain in Slice 1: /dashboard → /today → /overview (current real
 * page). Slice 4 collapses that to /dashboard → /today (real page),
 * with /overview becoming a legacy redirect of its own.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function DashboardLegacyRoute() {
  redirect("/today");
}
