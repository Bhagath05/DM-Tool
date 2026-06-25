/**
 * Next.js instrumentation hook — server + edge runtime Sentry init.
 *
 * Called once per worker at boot. Splits into two paths:
 * - `nodejs` runtime  → standard Node Sentry SDK
 * - `edge` runtime    → edge-compatible subset
 *
 * Browser-side init lives in `instrumentation-client.ts`.
 *
 * When NEXT_PUBLIC_SENTRY_DSN is empty (dev default), Sentry.init is
 * still called but with `dsn: undefined`, which is a documented no-op.
 */

import * as Sentry from "@sentry/nextjs";

import { scrubSentryBreadcrumb, scrubSentryEvent } from "@/lib/sentry-scrub";

export async function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN || undefined;
  const environment =
    process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ||
    process.env.NODE_ENV ||
    "development";
  const release = process.env.APP_VERSION || "0.0.0";

  // Phase S2.8 — shared scrubbers run on server + edge runtimes too.
  const shared = {
    sendDefaultPii: false,
    beforeSend: scrubSentryEvent,
    beforeBreadcrumb: scrubSentryBreadcrumb,
  };

  if (process.env.NEXT_RUNTIME === "nodejs") {
    Sentry.init({
      dsn,
      environment,
      release,
      // Edge requests + server actions inherit this. Performance traces
      // off by default (cost); flip per-deploy via env if needed.
      tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0),
      ...shared,
    });
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    Sentry.init({
      dsn,
      environment,
      release,
      tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0),
      ...shared,
    });
  }
}

// Required for server-side request error capture in app router.
export const onRequestError = Sentry.captureRequestError;
