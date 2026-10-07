/**
 * Phase 6.1 — /overview consolidated into /today.
 *
 * /today is the single canonical home. /overview is kept as a redirect (not
 * deleted) because the command palette and legacy links/bookmarks still point
 * here. Its _components/ are retained — /today composes several of them.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function OverviewLegacyRoute() {
  redirect("/today");
}
