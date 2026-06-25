/**
 * Creative Studio (CS1) feature flag — frontend mirror of the backend's
 * `studio_enabled`. When false (default), the Studio UI is hidden and the
 * backend routes 409, so CS1 ships completely dark.
 *
 * Env-only (no React imports) so it's safe to import anywhere, including
 * the edge. Mirror the value on the backend via STUDIO_ENABLED.
 */

/** Read NEXT_PUBLIC_STUDIO_ENABLED; default to false (dark) when unset. */
export function isStudioEnabled(): boolean {
  return process.env.NEXT_PUBLIC_STUDIO_ENABLED === "true";
}
