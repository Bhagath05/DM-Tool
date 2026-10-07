import { ConversationalFlow } from "./_components/conversational-flow";

export const dynamic = "force-dynamic";

export default function OnboardingPage() {
  // Phase 2.0 — conversational flow is the canonical onboarding. The legacy
  // form-heavy wizard component is preserved at _components/wizard; its old
  // /onboarding/profile/classic route now redirects here (Phase 6.2).
  return <ConversationalFlow />;
}
