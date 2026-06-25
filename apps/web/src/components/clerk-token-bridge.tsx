"use client";

/**
 * ClerkTokenBridge — pipes Clerk's `getToken()` into the module-level
 * auth-token cache that `lib/api.ts` reads.
 *
 * Must be rendered INSIDE `<ClerkProvider>` (useAuth() throws otherwise).
 * Only mounted when `isClerkConfigured()` — see AuthProvider.
 *
 * useLayoutEffect (not useEffect) so the wiring happens BEFORE any child
 * effects run. The TenantProvider's `/me` call kicks off in a child
 * useEffect; with useLayoutEffect here, the getter is wired in time for
 * that first call to carry the Authorization header.
 *
 * Returns null — it's a side-effect-only component.
 */

import { useAuth } from "@clerk/nextjs";
import { useEffect, useLayoutEffect, useRef } from "react";

import { isClerkActive } from "@/lib/clerk-config";
import { setAuthTokenGetter } from "@/lib/auth-token";

export function ClerkTokenBridge() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  // Ref keeps the getter closure fresh without re-registering on every
  // render — important because isLoaded/isSignedIn flip during boot.
  const authRef = useRef({ getToken, isLoaded, isSignedIn });
  authRef.current = { getToken, isLoaded, isSignedIn };

  // Set on mount + whenever auth state changes. useLayoutEffect runs
  // synchronously after DOM mutations, before child useEffects.
  useLayoutEffect(() => {
    if (!isClerkActive()) {
      setAuthTokenGetter(null);
      return;
    }
    setAuthTokenGetter(async () => {
      const { getToken, isLoaded, isSignedIn } = authRef.current;
      // Hybrid/demo: anonymous visitors must NOT call getToken(). A broken
      // or mismatched Clerk config makes getToken() hang in a refresh loop,
      // which blocks TenantProvider's first /me and freezes the app on
      // "Loading workspace…". The backend serves demo-user without JWT.
      if (!isLoaded || !isSignedIn) return null;
      try {
        return await getToken();
      } catch {
        return null;
      }
    });
  }, [getToken, isLoaded, isSignedIn]);

  // Clear on unmount so a sign-out doesn't leave a stale getter that
  // would silently attach a now-invalid token to subsequent requests.
  useEffect(() => {
    return () => setAuthTokenGetter(null);
  }, []);

  return null;
}
