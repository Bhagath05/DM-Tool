/**
 * Frontend tenant-tag helpers for Sentry.
 *
 * Why these are separated from the Sentry init: the init runs at module
 * load when the active tenant isn't known yet (user might not be signed
 * in). These helpers are invoked from wherever the active tenant becomes
 * known (the TenantProvider once A3 lands, or any future side-effect
 * that switches org/brand).
 *
 * Safe to call when Sentry isn't configured — `setUser` / `setTag` on
 * an uninitialised SDK is a no-op.
 */

import * as Sentry from "@sentry/nextjs";

export type TenantTags = {
  userId?: string | null;
  organizationId?: string | null;
  brandId?: string | null;
  roleSlugs?: string[];
};

/**
 * Attach the active tenant to Sentry's current scope. Every exception
 * captured after this runs will carry these tags until cleared.
 *
 * Call when:
 * - Active org / brand changes (TenantProvider effect)
 * - User signs in
 * - `/api/v1/me` resolves
 */
export function setSentryTenant({
  userId,
  organizationId,
  brandId,
  roleSlugs,
}: TenantTags): void {
  if (userId != null) {
    Sentry.setUser({ id: userId });
  }
  if (organizationId != null) {
    Sentry.setTag("organization_id", organizationId);
  }
  if (brandId != null) {
    Sentry.setTag("brand_id", brandId);
  }
  if (roleSlugs && roleSlugs.length > 0) {
    Sentry.setTag("role", roleSlugs.slice().sort().join(","));
  }
}

/**
 * Drop tenant tags. Call on sign-out so a subsequent error isn't
 * attributed to the prior session's user.
 */
export function clearSentryTenant(): void {
  Sentry.setUser(null);
}

/**
 * Manually capture an exception with extra context. Use in api.ts
 * catch blocks where the failure is a known API error rather than an
 * unhandled JS exception.
 */
export function captureApiError(
  err: unknown,
  context: {
    method: string;
    path: string;
    status?: number;
  },
): void {
  Sentry.captureException(err, {
    tags: {
      api_method: context.method,
      api_path: context.path,
      ...(context.status != null
        ? { api_status: String(context.status) }
        : {}),
    },
  });
}
