/**
 * Phase 10.1 — /billing is now a redirect to /settings/billing.
 */

import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function BillingLegacyRoute() {
  redirect("/settings/billing");
}
