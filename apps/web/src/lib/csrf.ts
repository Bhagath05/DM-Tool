/**
 * CSRF double-submit helper for first-party auth.
 *
 * On sign-in the backend sets a NON-HttpOnly `dmt_csrf` cookie. For every
 * state-changing request the SPA reads that cookie and echoes it in the
 * `X-CSRF-Token` header; the backend requires header == cookie. A cross-site
 * attacker can neither read our cookie nor set our custom header (blocked by
 * the CORS preflight), so a match proves the request came from our own origin.
 *
 * The session cookie itself stays HttpOnly and is never read here.
 */

export const CSRF_COOKIE = "dmt_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)dmt_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}
