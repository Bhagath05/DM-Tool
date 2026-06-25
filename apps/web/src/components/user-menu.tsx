"use client";

import { SignedIn, SignedOut, UserButton } from "@clerk/nextjs";

import { getAuthMode, isClerkActive } from "@/lib/clerk-config";

/**
 * Avatar / mode-badge in the topbar.
 *
 * Strict rule: NEVER mix sign-in UI into the demo experience. Sign-in
 * is a separate journey reachable only from the landing page.
 *
 *   demo                           → "Demo mode" badge
 *   clerk + signed                 → <UserButton>
 *   clerk + anon                   → (middleware would have redirected to /sign-in)
 *   hybrid + signed                → <UserButton>
 *   hybrid + anon (demo session)   → "Demo mode" badge (NOT a sign-in link)
 *
 * Clerk's <UserButton>, <SignedIn>, <SignedOut> internally call
 * useSession() and crash if <ClerkProvider> isn't mounted. We only use
 * them when isClerkActive() is true.
 */
export function UserMenu() {
  if (!isClerkActive()) {
    return <ModeBadge />;
  }

  return (
    <>
      <SignedIn>
        <UserButton afterSignOutUrl="/" />
      </SignedIn>
      <SignedOut>
        {/* Anonymous on hybrid: still the demo experience — no sign-in
            prompt. The landing page is where users discover sign-in. */}
        <ModeBadge />
      </SignedOut>
    </>
  );
}

function ModeBadge() {
  const mode = getAuthMode();
  const label =
    mode === "demo" || mode === "hybrid" ? "Demo mode" : "Auth not configured";
  return (
    <span
      data-testid="user-menu-fallback"
      className="rounded-md border border-dashed border-border px-2 py-1 text-xs text-muted-foreground"
    >
      {label}
    </span>
  );
}
