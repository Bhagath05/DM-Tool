/**
 * Phase 10.1 — /team is now a redirect to /settings/team.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function TeamLegacyRoute() {
  redirect("/settings/team");
}
