"use client";

import { ClerkProvider } from "@clerk/nextjs";

import { ClerkTokenBridge } from "@/components/clerk-token-bridge";
import { isClerkConfigured } from "@/lib/clerk-config";

const clerkSignInUrl = process.env.NEXT_PUBLIC_CLERK_SIGN_IN_URL ?? "/sign-in";
const clerkSignUpUrl = process.env.NEXT_PUBLIC_CLERK_SIGN_UP_URL ?? "/sign-up";
const clerkAfterSignIn =
  process.env.NEXT_PUBLIC_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL ?? "/dashboard";
const clerkAfterSignUp =
  process.env.NEXT_PUBLIC_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL ?? "/dashboard";

/**
 * Wraps ClerkProvider so the dashboard can boot without real Clerk keys
 * during initial scaffolding. Once a valid publishable key is set in
 * NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, the full ClerkProvider mounts and auth
 * starts working.
 *
 * The shared `isClerkConfigured` predicate is the source of truth — same
 * answer here as in sign-in/sign-up pages, so they all agree on whether
 * to render Clerk UI or the unconfigured fallback.
 *
 * ClerkTokenBridge is rendered as a sibling of children so it wires the
 * auth-token cache BEFORE child components (notably TenantProvider) make
 * their first API call. See clerk-token-bridge.tsx for why this matters.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (!isClerkConfigured()) {
    return <>{children}</>;
  }
  return (
    <ClerkProvider
      signInUrl={clerkSignInUrl}
      signUpUrl={clerkSignUpUrl}
      signInFallbackRedirectUrl={clerkAfterSignIn}
      signUpFallbackRedirectUrl={clerkAfterSignUp}
    >
      <ClerkTokenBridge />
      {children}
    </ClerkProvider>
  );
}
