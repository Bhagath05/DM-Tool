import { OnboardingWizard } from "../_components/wizard";

export const dynamic = "force-dynamic";

/**
 * Legacy form-heavy onboarding — preserved during the Phase 2.0 rollout so
 * we have a known-good fallback if the conversational flow misbehaves. The
 * wizard component itself is untouched; this route just remounts it.
 */
export default function OnboardingClassicPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Set up your business — classic form
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Fallback if the new guided onboarding isn&apos;t working. We&apos;ll
          retire this once the conversational flow is rock solid.
        </p>
      </div>
      <OnboardingWizard />
    </div>
  );
}
