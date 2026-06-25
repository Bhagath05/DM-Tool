/**
 * Auth-mode + Clerk configuration probe.
 *
 * Three product modes, controlled by NEXT_PUBLIC_AUTH_MODE:
 *
 *   "demo"   — landing page → /dashboard works without sign-in. Clerk
 *              UI / middleware / token bridge are all no-ops. Backend
 *              mirror returns a stable demo-user for every request.
 *
 *   "clerk"  — strict Clerk auth. ClerkProvider mounts, sign-in /
 *              sign-up pages render the real <SignIn>/<SignUp>, the
 *              middleware protects routes, the token bridge attaches
 *              JWTs to outbound API calls. Anonymous visits to
 *              protected routes get bounced to /sign-in.
 *
 *   "hybrid" — both. ClerkProvider mounts (so sign-in works), token
 *              bridge attaches JWTs WHEN signed in. But middleware
 *              does NOT protect routes — anonymous visits to
 *              /dashboard land on the demo path (backend serves
 *              demo-user when no Bearer token). Lets the public-demo
 *              journey AND real sign-in coexist in the same deploy.
 *
 * Default is "demo" by product decision. Mirror the value on the
 * backend via AUTH_MODE in root .env.
 *
 * Centralised because four call sites need the same answer:
 *   - AuthProvider          — whether to mount <ClerkProvider> at all
 *   - sign-in / sign-up     — whether <SignIn>/<SignUp> can render
 *   - middleware            — whether to run clerkMiddleware + protect
 *   - ClerkTokenBridge      — only mounted when Clerk is active
 *
 * NOTE: keep this module env-only (no React imports). middleware.ts
 * imports it at the edge.
 */

export type AuthMode = "demo" | "clerk" | "hybrid";

/** Read NEXT_PUBLIC_AUTH_MODE; default to "demo" when unset/unknown. */
export function getAuthMode(): AuthMode {
  const raw = process.env.NEXT_PUBLIC_AUTH_MODE;
  if (raw === "clerk") return "clerk";
  if (raw === "hybrid") return "hybrid";
  return "demo";
}

export function isDemoMode(): boolean {
  return getAuthMode() === "demo";
}

/**
 * Should the middleware ENFORCE auth on protected routes?
 * Only in strict "clerk" mode. In "hybrid" mode auth is optional —
 * anonymous visits to /dashboard land on the demo path.
 */
export function isAuthEnforced(): boolean {
  return getAuthMode() === "clerk";
}

const PLACEHOLDER_VALUES = [
  "",
  "pk_test_replace_me",
  "sk_test_replace_me",
];

/**
 * Are the Clerk publishable-key env values structurally valid?
 * Separate from `isClerkActive` because mode and keys are independent
 * settings — a deploy might have keys present but mode=demo.
 */
function hasValidClerkKey(): boolean {
  const key = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
  if (!key || PLACEHOLDER_VALUES.includes(key)) return false;
  if (!/^pk_(test|live)_/.test(key)) return false;
  if (key.length < 20) return false;
  return true;
}

/**
 * Should the frontend actually run Clerk's machinery (ClerkProvider,
 * sign-in/up UI, token bridge)? True iff (mode=clerk OR mode=hybrid)
 * AND a real publishable key is set.
 *
 * Mode=demo always returns false — even with valid keys, we don't
 * render Clerk UI in pure-demo mode.
 */
export function isClerkActive(): boolean {
  const mode = getAuthMode();
  if (mode === "demo") return false;
  return hasValidClerkKey();
}

/**
 * @deprecated kept for backwards compatibility with the pre-AUTH_MODE
 * call sites. Same semantics as `isClerkActive()`.
 */
export function isClerkConfigured(): boolean {
  return isClerkActive();
}
