import type { Metadata } from "next";

import { OnboardingWizard } from "@/components/onboarding-wizard";

export const metadata: Metadata = {
  title: "Welcome · DM Tool",
  description: "Set up your workspace to get started.",
};

/**
 * Onboarding wizard route — W1-15.
 *
 * Mounted OUTSIDE the `(app)` route group so the sidebar doesn't render
 * around the centered card and there's no TenantProvider context to
 * mismatch (the user has no tenant yet — that's why they're here).
 *
 * Auth is still required (Clerk middleware enforces it). The wizard
 * itself uses `api.onboarding.createWorkspace()` which goes through
 * the same fetch wrapper that attaches the Clerk JWT.
 */
export default function OnboardingPage() {
  return (
    <main className="min-h-dvh bg-background">
      <OnboardingWizard />
    </main>
  );
}
