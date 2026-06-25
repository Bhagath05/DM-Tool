import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

/**
 * Phase S1.3 — HTTP security headers. P1 hardening — CSP enforcement.
 *
 * CSP is ENFORCED in production (`Content-Security-Policy`) and ships
 * REPORT-ONLY in development (`Content-Security-Policy-Report-Only`), because
 * the Next.js dev server needs 'unsafe-eval' for HMR — which the prod policy
 * strips. The header key is selected by `isProd` below.
 *
 * Origins enumerated (production posture):
 *   - self / data: / blob:
 *   - Clerk: *.clerk.accounts.dev, *.clerk.com, img.clerk.com
 *   - Sentry: *.sentry.io (and our tunnel route /monitoring which proxies)
 *   - API: process.env.NEXT_PUBLIC_API_URL
 *
 * 'unsafe-inline' on style-src — Next.js + Tailwind inject inline
 * <style> tags. 'unsafe-eval' on script-src is the dev-only escape
 * hatch (Next.js dev server uses eval for HMR); we strip it in prod.
 */
const isProd = process.env.NODE_ENV === "production";
const apiOrigin = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const clerkHosts =
  "https://*.clerk.accounts.dev https://*.clerk.com https://img.clerk.com";
const sentryHosts = "https://*.sentry.io https://*.ingest.sentry.io";

const csp = [
  `default-src 'self'`,
  `script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"} ${clerkHosts}`,
  `style-src 'self' 'unsafe-inline'`,
  `img-src 'self' data: blob: https: ${clerkHosts}`,
  `font-src 'self' data:`,
  `connect-src 'self' ${apiOrigin} ${clerkHosts} ${sentryHosts} wss://*.clerk.accounts.dev`,
  `frame-src 'self' ${clerkHosts}`,
  `worker-src 'self' blob:`,
  `object-src 'none'`,
  `base-uri 'self'`,
  `form-action 'self' ${clerkHosts}`,
  `frame-ancestors 'none'`,
  // `upgrade-insecure-requests` is ignored by browsers in a report-only
  // policy (dev), where it just emits a console error on every navigation.
  // Only emit it in production, where the policy is enforced.
  ...(isProd ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  // CSP is ENFORCED in production and report-only in development (dev needs
  // 'unsafe-eval' for HMR, which the policy already strips from prod). This
  // is the P1 hardening flip from the report-only roll-out.
  {
    key: isProd
      ? "Content-Security-Policy"
      : "Content-Security-Policy-Report-Only",
    value: csp,
  },
  // HSTS — 2 years, includeSubDomains, preload-ready.
  // Only emit in prod: localhost over plain http would refuse to load.
  ...(isProd
    ? [
        {
          key: "Strict-Transport-Security",
          value: "max-age=63072000; includeSubDomains; preload",
        },
      ]
    : []),
  // Defense-in-depth on top of CSP frame-ancestors.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Disable browser features we never use. Add to the list as new
  // browser-feature policies land.
  {
    key: "Permissions-Policy",
    value: [
      "accelerometer=()",
      "autoplay=()",
      "camera=()",
      "display-capture=()",
      "geolocation=()",
      "gyroscope=()",
      "magnetometer=()",
      "microphone=()",
      "midi=()",
      "payment=()",
      "usb=()",
      "xr-spatial-tracking=()",
    ].join(", "),
  },
  // Browsers ignore this in favour of CSP, but keep it for crawlers
  // and legacy proxies that scan the header.
  { key: "X-DNS-Prefetch-Control", value: "on" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,

  headers: async () => [
    {
      // Apply to every route. Authorization-bearing API routes still
      // get these headers attached.
      source: "/:path*",
      headers: securityHeaders,
    },
  ],

  /**
   * Phase 10.3 — Founder Simplification Pass URL renames.
   *
   * Each rewrite makes a new outcome-shaped URL serve an existing
   * studio / inbox page without moving any files. The browser URL bar
   * stays at the new path (`/create/social-posts`, `/grow/leads`,
   * etc.) while Next.js internally renders the legacy page component
   * (`/content`, `/leads`, etc.). Zero duplicate components, zero
   * redirect machinery.
   *
   * Why rewrites instead of `redirect()` route shells:
   *
   *   In Next.js 15.x, a server-component leaf page that calls
   *   `redirect()` while nested inside a `"use client"` parent layout
   *   (we have one — `TenantProvider` in `(app)/layout.tsx`) can trip
   *   a "Rendered more hooks than during the previous render" error in
   *   the App Router's internal `useMemo`. Rewrites side-step the
   *   issue entirely because no leaf page renders — Next.js maps the
   *   URL to the destination's component at the route resolver.
   *
   * Slice 6 of the migration will move the canonical pages to these
   * new paths (file rename) and the rewrites will flip into legacy
   * redirects (`/content` → `/create/social-posts`). For now this is
   * the least-disruptive shape.
   */
  rewrites: async () => [
    { source: "/grow/leads", destination: "/leads" },
    { source: "/grow/opportunities", destination: "/opportunities" },
    { source: "/create/social-posts", destination: "/content" },
    { source: "/create/ads", destination: "/ads" },
    { source: "/create/creatives", destination: "/visuals" },
    { source: "/results", destination: "/performance" },
  ],

  // Back-compat: the workspace-creation wizard moved from /onboarding/org to
  // /onboarding. Redirect old bookmarks/links so they don't 404.
  redirects: async () => [
    {
      source: "/onboarding/org",
      destination: "/onboarding",
      permanent: false,
    },
  ],
};

// Wrap with Sentry so production builds upload source maps and inject
// the client/server SDK config. All Sentry behavior is gated on
// SENTRY_AUTH_TOKEN + NEXT_PUBLIC_SENTRY_DSN — without those, the
// wrapper is a no-op and behaves like the bare nextConfig.
export default withSentryConfig(nextConfig, {
  // Read these from env so nothing is hardcoded.
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,

  // Quiet the build unless something actually fails — CI logs stay clean.
  silent: !process.env.CI,

  // Upload a larger set of source maps so stack traces resolve to TSX.
  widenClientFileUpload: true,

  // Route browser→Sentry requests through our own domain to bypass
  // ad-blockers. Adds an /monitoring route to the Next.js app.
  tunnelRoute: "/monitoring",

  // Skip source-map upload entirely when the auth token is missing —
  // local dev builds shouldn't try to talk to Sentry. When the token IS
  // present, source maps are uploaded and then deleted from the public
  // bundle (deleteSourcemapsAfterUpload) so the browser can't fetch them.
  sourcemaps: {
    disable: !process.env.SENTRY_AUTH_TOKEN,
    deleteSourcemapsAfterUpload: true,
  },

  // Tree-shake Sentry logger statements out of the client bundle.
  disableLogger: true,
});
