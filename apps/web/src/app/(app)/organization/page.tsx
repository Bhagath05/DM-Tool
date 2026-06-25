/**
 * Phase 10.1 — /organization is now a redirect to /settings/organization.
 *
 * Kept alive so any cached link, bookmark, or sidebar memory continues
 * to land on the right page. The settings shell owns the real route.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function OrganizationLegacyRoute() {
  redirect("/settings/organization");
}
