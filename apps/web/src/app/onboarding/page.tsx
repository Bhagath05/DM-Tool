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
 * Auth is still required (the session-cookie middleware redirects an
 * unauthenticated user to /sign-in). The wizard uses
 * `api.onboarding.createWorkspace()`, which sends the session cookie like
 * every other API call.
 */
export default function OnboardingPage() {
  return (
    <main className="min-h-dvh bg-background">
      <OnboardingWizard />
    </main>
  );
}
