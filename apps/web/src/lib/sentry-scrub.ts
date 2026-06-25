/**
 * Phase S2.8 — Sentry data protection scrubber (frontend).
 *
 * Mirrors apps/api/aicmo/observability/sentry.py:_scrub_event. Runs as
 * `beforeSend` + `beforeBreadcrumb` so no Authorization header, cookie,
 * password, JWT, or known-provider API key is ever uploaded to Sentry.
 *
 * Tenant headers (X-Organization-Id, X-Brand-Id) are KEPT — they are
 * triage signal, not secret.
 */

import type { ErrorEvent, EventHint, Breadcrumb } from "@sentry/nextjs";

const REDACTED = "[Filtered]";
const MAX_DEPTH = 6;

const SENSITIVE_HEADER_PREFIXES = [
  "authorization",
  "cookie",
  "set-cookie",
  "x-api-key",
  "proxy-authorization",
] as const;

const SENSITIVE_FIELD = new RegExp(
  [
    "password|passwd|pwd",
    "secret|api[_-]?key|access[_-]?token|refresh[_-]?token",
    "client[_-]?secret|signing[_-]?secret|webhook[_-]?secret",
    "private[_-]?key|encryption[_-]?key|integration[_-]?token",
    "authorization|bearer|session[_-]?id",
  ].join("|"),
  "i",
);

const SECRET_VALUE_PATTERNS: RegExp[] = [
  /sk_(live|test)_[a-zA-Z0-9]{20,}/g,
  /pk_live_[a-zA-Z0-9]{20,}/g,
  /sk-ant-[a-zA-Z0-9_\-]{40,}/g,
  /sk-(proj-)?[A-Za-z0-9_\-]{30,}/g,
  /AIza[0-9A-Za-z\-_]{35}/g,
  /whsec_[A-Za-z0-9+/=]{20,}/g,
  /eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+/g,
  /postgres(ql)?(\+psycopg)?:\/\/[^:\s]+:[^@\s]+@/g,
];

function scrubString(value: string): string {
  if (!value) return value;
  return SECRET_VALUE_PATTERNS.reduce(
    (acc, pat) => acc.replace(pat, REDACTED),
    value,
  );
}

function scrubValue(v: unknown, depth = 0): unknown {
  if (depth >= MAX_DEPTH) return v;
  if (v === null || v === undefined) return v;
  if (Array.isArray(v)) return v.map((item) => scrubValue(item, depth + 1));
  if (typeof v === "object") return scrubMapping(v as Record<string, unknown>, depth);
  if (typeof v === "string") return scrubString(v);
  return v;
}

function scrubMapping(
  obj: Record<string, unknown>,
  depth = 0,
): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (SENSITIVE_FIELD.test(k)) {
      cleaned[k] = REDACTED;
      continue;
    }
    cleaned[k] = scrubValue(v, depth + 1);
  }
  return cleaned;
}

function scrubHeaders(
  headers: Record<string, unknown>,
): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(headers)) {
    const kl = String(k).toLowerCase();
    if (SENSITIVE_HEADER_PREFIXES.some((p) => kl.startsWith(p))) {
      cleaned[k] = REDACTED;
    } else {
      cleaned[k] = scrubValue(v);
    }
  }
  return cleaned;
}

/** beforeSend / beforeSendTransaction hook. */
export function scrubSentryEvent(
  event: ErrorEvent,
  _hint?: EventHint,
): ErrorEvent | null {
  const request = (event.request ?? {}) as Record<string, unknown>;
  if (request.headers && typeof request.headers === "object") {
    request.headers = scrubHeaders(request.headers as Record<string, unknown>);
  }
  for (const key of ["data", "query_string", "cookies"] as const) {
    const body = request[key];
    if (body && typeof body === "object") {
      request[key] = scrubValue(body);
    } else if (typeof body === "string") {
      request[key] = scrubString(body);
    }
  }
  event.request = request as ErrorEvent["request"];

  for (const ctxKey of ["extra", "contexts", "tags"] as const) {
    const ctx = event[ctxKey];
    if (ctx && typeof ctx === "object") {
      (event as unknown as Record<string, unknown>)[ctxKey] = scrubValue(ctx);
    }
  }

  if (event.exception?.values) {
    for (const entry of event.exception.values) {
      if (entry && typeof entry.value === "string") {
        entry.value = scrubString(entry.value);
      }
    }
  }

  if (typeof event.message === "string") {
    event.message = scrubString(event.message);
  }

  return event;
}

/** beforeBreadcrumb hook. */
export function scrubSentryBreadcrumb(
  crumb: Breadcrumb,
  _hint?: { event?: Event } & Record<string, unknown>,
): Breadcrumb | null {
  if (crumb.data && typeof crumb.data === "object") {
    crumb.data = scrubValue(crumb.data) as Breadcrumb["data"];
  }
  if (typeof crumb.message === "string") {
    crumb.message = scrubString(crumb.message);
  }
  return crumb;
}
