/**
 * Auth-token getter cache.
 *
 * Why a getter (not a cached string):
 *   Clerk JWTs expire ~60s after issuance and rotate silently in the
 *   background. We never want to cache the token itself — we want to
 *   call Clerk's `getToken()` on every outbound request so the SDK
 *   handles refresh for us.
 *
 * Why a module-level cache (not React context):
 *   `lib/api.ts:request()` is a plain function called from event
 *   handlers, hooks, effects, and one-off utilities. A context would
 *   require every caller to be inside a React tree — they aren't.
 *   Same architectural choice as `lib/tenant.ts`'s header cache.
 *
 * Wiring:
 *   `<ClerkTokenBridge>` (rendered inside `<ClerkProvider>` by
 *   AuthProvider) calls `setAuthTokenGetter(useAuth().getToken)` in a
 *   useLayoutEffect. By the time `<TenantProvider>` runs its first
 *   `/me` call, the getter is already set.
 *
 *   When Clerk isn't configured (dev-bypass), the bridge isn't
 *   rendered → getter stays null → `request()` sends no Authorization
 *   header → backend's dev-user bypass takes over. Correct dev UX.
 */

export type AuthTokenGetter = () => Promise<string | null>;

/** Never block outbound API calls longer than this waiting on Clerk. */
const TOKEN_TIMEOUT_MS = 4_000;

let _getter: AuthTokenGetter | null = null;

export function setAuthTokenGetter(fn: AuthTokenGetter | null): void {
  _getter = fn;
}

/**
 * Resolve the current Clerk JWT, or null if Clerk isn't wired / no
 * session. Errors from `getToken()` (e.g. network blip while refreshing)
 * are swallowed and treated as "no token" — the caller will see a 401
 * from the backend, which is the right downstream signal.
 */
export async function getAuthToken(): Promise<string | null> {
  if (!_getter) return null;
  try {
    const token = await Promise.race([
      _getter(),
      new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), TOKEN_TIMEOUT_MS),
      ),
    ]);
    return token;
  } catch {
    return null;
  }
}

/** Test-only — wipe module state between tests. */
export function __resetAuthTokenForTests(): void {
  _getter = null;
}
