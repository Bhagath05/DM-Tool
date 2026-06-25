/**
 * Frontend tenant model — shape mirrors the backend MeResponse.
 *
 * Source of truth for the contract is `apps/api/aicmo/modules/users/schemas.py`.
 * If a field is added there, mirror it here AND update `useTenant` consumers.
 *
 * This module is intentionally framework-free (no React imports) so it can
 * be:
 *   - imported by `lib/api.ts` (which is also framework-free), and
 *   - exercised by Vitest in a node environment.
 *
 * The single piece of side-effecting state lives in the bottom section —
 * `setActiveTenantHeaders` / `getActiveTenantHeaders` — and exists so
 * `lib/api.ts`'s `request()` can attach `X-Organization-Id` /
 * `X-Brand-Id` without needing a React context (which it can't reach
 * from a plain function).
 *
 * `TenantProvider` owns the lifecycle: read from storage on mount,
 * write to storage on switch, mirror to the module-level cache so the
 * next outbound `fetch` picks up the new headers.
 */

// ---------------------------------------------------------------------
//  Types — mirror MeResponse from apps/api/aicmo/modules/users/schemas.py
// ---------------------------------------------------------------------

export interface BrandSummary {
  id: string;
  slug: string;
  name: string;
  status: string;
}

export interface OrgSummary {
  id: string;
  slug: string;
  name: string;
  status: string;
  member_count: number;
  brand_count: number;
}

export interface Membership {
  organization: OrgSummary;
  role_slugs: string[];
  permissions: string[];
  brands: BrandSummary[];
  last_active_brand_id: string | null;
  joined_at: string;
}

export interface ActiveTenant {
  organization_id: string;
  brand_id: string | null;
  role_slugs: string[];
  permissions: string[];
}

export interface UserSummary {
  id: string;
  clerk_user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  status: string;
  last_seen_at: string | null;
  created_at: string;
}

export type SuggestedRoute =
  | "/dashboard"
  | "/onboarding"
  | "/orgs/select";

export interface MeResponse {
  user: UserSummary;
  memberships: Membership[];
  active: ActiveTenant | null;
  suggested_route: SuggestedRoute;
}

// ---------------------------------------------------------------------
//  Persisted selection (localStorage)
//
//  The user's choice of {org, brand} across reloads. Without this, every
//  refresh would require the backend to re-auto-resolve, which works
//  only when the user has exactly one membership / one brand. As soon
//  as they have two of either, the wrong default becomes very visible.
// ---------------------------------------------------------------------

export interface PersistedSelection {
  organization_id: string | null;
  brand_id: string | null;
}

export const STORAGE_KEY = "aicmo.tenant.selection.v1";

/** Brand-scoped caches cleared when org/brand changes to prevent cross-tenant bleed. */
export const BRAND_SCOPED_CACHE_KEYS = [
  "aicmo:today:v2",
  "aicmo:lead-intelligence:v1",
  "aicmo:opportunity-center:v1",
  "aicmo:generation-context:v1",
  "aicmo:weekly-plan:v1",
  "aicmo:analytics-summary:v1",
] as const;

const EMPTY: PersistedSelection = { organization_id: null, brand_id: null };

/** Accept UUIDs and backend slug-style ids; reject garbage from corrupt storage. */
const TENANT_ID_RE = /^[a-zA-Z0-9_-]{1,64}$/;

export function isValidTenantId(id: string | null | undefined): boolean {
  if (!id) return false;
  return TENANT_ID_RE.test(id.trim());
}

function sanitizeTenantId(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!TENANT_ID_RE.test(trimmed)) return null;
  return trimmed;
}

/** SSR-safe localStorage probe. Returns null when storage is unavailable. */
function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    // Safari private mode / disabled storage throws on access — treat as
    // no storage rather than crash the app.
    return null;
  }
}

export function readPersistedSelection(): PersistedSelection {
  const s = storage();
  if (!s) return { ...EMPTY };
  try {
    const raw = s.getItem(STORAGE_KEY);
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<PersistedSelection> | null;
    if (!parsed || typeof parsed !== "object") return { ...EMPTY };
    const organization_id = sanitizeTenantId(parsed.organization_id);
    const brand_id = sanitizeTenantId(parsed.brand_id);
    // Drop brand when org is missing — brand without org is unusable.
    const selection: PersistedSelection = {
      organization_id,
      brand_id: organization_id ? brand_id : null,
    };
    // Rewrite storage when sanitization stripped invalid ids.
    if (
      selection.organization_id !== parsed.organization_id ||
      selection.brand_id !== parsed.brand_id
    ) {
      if (!selection.organization_id && !selection.brand_id) {
        s.removeItem(STORAGE_KEY);
      } else {
        writePersistedSelection(selection);
      }
    }
    return selection;
  } catch {
    // Corrupted JSON — wipe and start fresh rather than hard-fail.
    s.removeItem(STORAGE_KEY);
    return { ...EMPTY };
  }
}

export function writePersistedSelection(value: PersistedSelection): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Quota exceeded / disabled — swallow. Persistence is a nice-to-have.
  }
}

export function clearPersistedSelection(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

/** Wipe brand-scoped localStorage caches after tenant switch or stale purge. */
export function purgeBrandScopedCaches(): void {
  const s = storage();
  if (!s) return;
  for (const key of BRAND_SCOPED_CACHE_KEYS) {
    try {
      s.removeItem(key);
    } catch {
      // ignore
    }
  }
}

// ---------------------------------------------------------------------
//  Active-tenant header cache (read by lib/api.ts on every request)
//
//  Module-level mutable state. The TenantProvider effect writes here
//  whenever the active selection changes. Plain `request()` calls in
//  api.ts read it and attach X-Organization-Id / X-Brand-Id.
//
//  Why not a React context: api.ts is invoked from event handlers, hooks,
//  effects — anywhere. A context value would require the API client to
//  be reconstructed on every render. A module-level getter is the same
//  pattern Clerk uses for `getToken()`.
// ---------------------------------------------------------------------

let _activeOrg: string | null = null;
let _activeBrand: string | null = null;

export function setActiveTenantHeaders(value: {
  organization_id: string | null;
  brand_id: string | null;
}): void {
  _activeOrg = value.organization_id;
  _activeBrand = value.brand_id;
}

export function getActiveTenantHeaders(): {
  organization_id: string | null;
  brand_id: string | null;
} {
  return { organization_id: _activeOrg, brand_id: _activeBrand };
}

/** Test-only: wipe module state between tests. */
export function __resetActiveTenantHeadersForTests(): void {
  _activeOrg = null;
  _activeBrand = null;
}

// ---------------------------------------------------------------------
//  Permission helper — used by useTenant.can() and any UI gate
// ---------------------------------------------------------------------

/**
 * O(n) check; n is typically <20 permissions per membership so a Set
 * conversion is more overhead than the linear scan is worth.
 */
export function hasPermission(
  permissions: string[] | null | undefined,
  slug: string,
): boolean {
  if (!permissions || permissions.length === 0) return false;
  return permissions.includes(slug);
}

/** Permission-set predicate: true iff EVERY slug is present. */
export function hasAllPermissions(
  permissions: string[] | null | undefined,
  slugs: string[],
): boolean {
  if (!permissions) return false;
  for (const slug of slugs) {
    if (!permissions.includes(slug)) return false;
  }
  return true;
}

/** Permission-set predicate: true iff AT LEAST ONE slug is present. */
export function hasAnyPermission(
  permissions: string[] | null | undefined,
  slugs: string[],
): boolean {
  if (!permissions) return false;
  for (const slug of slugs) {
    if (permissions.includes(slug)) return true;
  }
  return false;
}

// ---------------------------------------------------------------------
//  Resolution helpers — derive {activeOrg, activeBrand} from a MeResponse
//  + persisted selection. Pure functions, fully testable.
// ---------------------------------------------------------------------

export interface Resolved {
  membership: Membership | null;
  brand: BrandSummary | null;
}

export function resolveActiveMembership(
  me: MeResponse,
  preferredOrgId: string | null,
): Membership | null {
  if (me.memberships.length === 0) return null;
  if (preferredOrgId) {
    const hit = me.memberships.find(
      (m) => m.organization.id === preferredOrgId,
    );
    if (hit) return hit;
    // Persisted org no longer accessible (removed, deleted). Fall through.
  }
  // Backend may have already picked one (single-membership case).
  if (me.active) {
    const hit = me.memberships.find(
      (m) => m.organization.id === me.active!.organization_id,
    );
    if (hit) return hit;
  }
  // Default to first (orderly: backend sorts by joined_at).
  return me.memberships[0];
}

export function resolveActiveBrand(
  membership: Membership | null,
  preferredBrandId: string | null,
): BrandSummary | null {
  if (!membership || membership.brands.length === 0) return null;
  if (preferredBrandId) {
    const hit = membership.brands.find((b) => b.id === preferredBrandId);
    if (hit) return hit;
  }
  if (membership.last_active_brand_id) {
    const hit = membership.brands.find(
      (b) => b.id === membership.last_active_brand_id,
    );
    if (hit) return hit;
  }
  return membership.brands[0];
}
