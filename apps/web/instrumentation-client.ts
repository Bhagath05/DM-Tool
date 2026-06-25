/**
 * Browser-side Sentry init.
 *
 * Sentry's @sentry/nextjs auto-discovers this file at the project root
 * and loads it on the client only. Keep it small — every byte ships to
 * the user's browser.
 *
 * Tenant tags are NOT set here. They're attached after the user is
 * authenticated, via `lib/sentry-tenant.ts:setSentryTenant()`. That
 * helper is callable from anywhere the active tenant is known.
 */

import * as Sentry from "@sentry/nextjs";

import { scrubSentryBreadcrumb, scrubSentryEvent } from "@/lib/sentry-scrub";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || undefined;
const environment =
  process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ||
  process.env.NODE_ENV ||
  "development";
const release = process.env.NEXT_PUBLIC_APP_VERSION || "0.0.0";

Sentry.init({
  dsn,
  environment,
  release,
  // Replay is opt-in and bandwidth-hungry; off by default.
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0,
  // Don't auto-capture browser console.error/console.warn — they're
  // noisy and the real bugs surface via unhandled exceptions anyway.
  integrations: [],
  tracesSampleRate: Number(
    process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0,
  ),
  // Don't ship cookies or auth headers if Sentry SDK ever captures a fetch.
  sendDefaultPii: false,
  // Phase S2.8 — strip secrets from every event + breadcrumb before
  // upload. See apps/web/src/lib/sentry-scrub.ts.
  beforeSend: scrubSentryEvent,
  beforeBreadcrumb: scrubSentryBreadcrumb,
});

// Sentry's recommended router-instrumentation hook for App Router.
// Required so client-side navigation events thread through traces.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
