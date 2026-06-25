import { ConversationalFlow } from "./_components/conversational-flow";

export const dynamic = "force-dynamic";

export default function OnboardingPage() {
  // Phase 2.0 — conversational flow is the default. The legacy form-heavy
  // wizard is still available at /onboarding/profile/classic for rollback safety.
  return <ConversationalFlow />;
}
