"use client";

/**
 * TenantProvider — single source of truth for the active org / brand /
 * permissions / role across the React tree.
 *
 * Boot sequence:
 *  1. Read the persisted {org, brand} from localStorage.
 *  2. Write that selection into the api header cache so `/me` carries it.
 *  3. Call `/api/v1/me` — backend resolves the active tenant.
 *  4. Reconcile the response with the persisted selection:
 *       - If the persisted org is still in `memberships`, keep it.
 *       - Else fall back to whatever the backend picked (or first member).
 *  5. Mirror the resolved {user, org, brand, role} into Sentry tags.
 *  6. Honor `suggested_route` from the backend — if we're on /dashboard but
 *     the user has no memberships, redirect to /onboarding. The
 *     redirect happens *here* (not in middleware) because middleware can't
 *     read the response body cheaply.
 *
 * Header propagation:
 *  Every outbound `request()` call in `lib/api.ts` consults
 *  `getActiveTenantHeaders()`. This provider keeps that cache in sync
 *  with React state. Together, they form a one-way data flow:
 *    user-click → setState → effect → header cache → next fetch
 */

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api } from "@/lib/api";
import { getAuthToken } from "@/lib/auth-token";
import { isClerkActive } from "@/lib/clerk-config";
import {
  type ActiveTenant,
  type BrandSummary,
  type MeResponse,
  type Membership,
  type OrgSummary,
  type SuggestedRoute,
  type UserSummary,
  clearPersistedSelection,
  hasAllPermissions,
  hasAnyPermission,
  hasPermission,
  purgeBrandScopedCaches,
  readPersistedSelection,
  resolveActiveBrand,
  resolveActiveMembership,
  setActiveTenantHeaders,
  writePersistedSelection,
} from "@/lib/tenant";
import {
  clearSentryTenant,
  setSentryTenant,
} from "@/lib/sentry-tenant";

// ---------------------------------------------------------------------
//  Context shape
// ---------------------------------------------------------------------

export type TenantStatus = "loading" | "ready" | "error" | "no-memberships";

export interface TenantContextValue {
  status: TenantStatus;
  error: Error | null;

  // Identity
  user: UserSummary | null;

  // Tenant selection
  activeOrg: OrgSummary | null;
  activeBrand: BrandSummary | null;
  activeMembership: Membership | null;

  // All memberships for the org-switcher UI
  memberships: Membership[];

  // RBAC
  permissions: string[];
  roleSlugs: string[];
  can: (slug: string) => boolean;
  canAll: (slugs: string[]) => boolean;
  canAny: (slugs: string[]) => boolean;

  // Environment (resolved server-side at build time — handy for UI badges)
  environment: string;

  // Hints from backend
  suggestedRoute: SuggestedRoute | null;

  // Actions
  switchOrg: (organizationId: string) => Promise<void>;
  switchBrand: (brandId: string) => Promise<void>;
  refresh: () => Promise<void>;

  // What the backend resolved on the LAST /me call. Useful for debug
  // panels and the active-tenant badge in the topbar.
  active: ActiveTenant | null;
}

const TenantContext = createContext<TenantContextValue | null>(null);

// ---------------------------------------------------------------------
//  Provider
// ---------------------------------------------------------------------

const ENVIRONMENT =
  process.env.NEXT_PUBLIC_APP_ENV ||
  process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ||
  process.env.NODE_ENV ||
  "development";

export function TenantProvider({
  children,
  enforceSuggestedRoute = false,
}: {
  children: React.ReactNode;
  enforceSuggestedRoute?: boolean;
}) {
  if (!isClerkActive()) {
    return (
      <TenantProviderImpl enforceSuggestedRoute={enforceSuggestedRoute}>
        {children}
      </TenantProviderImpl>
    );
  }
  return (
    <TenantProviderClerkGate enforceSuggestedRoute={enforceSuggestedRoute}>
      {children}
    </TenantProviderClerkGate>
  );
}

function TenantProviderClerkGate({
  children,
  enforceSuggestedRoute,
}: {
  children: React.ReactNode;
  enforceSuggestedRoute: boolean;
}) {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) {
    return (
      <TenantContext.Provider
        value={{
          status: "loading",
          error: null,
          user: null,
          activeOrg: null,
          activeBrand: null,
          activeMembership: null,
          memberships: [],
          permissions: [],
          roleSlugs: [],
          can: () => false,
          canAll: () => false,
          canAny: () => false,
          environment: ENVIRONMENT,
          suggestedRoute: null,
          switchOrg: async () => {},
          switchBrand: async () => {},
          refresh: async () => {},
          active: null,
        }}
      >
        {children}
      </TenantContext.Provider>
    );
  }
  return (
    <TenantProviderImpl
      enforceSuggestedRoute={enforceSuggestedRoute}
      clerkSignedIn={isSignedIn}
    >
      {children}
    </TenantProviderImpl>
  );
}

function TenantProviderImpl({
  children,
  enforceSuggestedRoute = false,
  clerkSignedIn = false,
}: {
  children: React.ReactNode;
  enforceSuggestedRoute?: boolean;
  clerkSignedIn?: boolean;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<TenantStatus>("loading");
  const [error, setError] = useState<Error | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(null);
  const [activeBrandId, setActiveBrandId] = useState<string | null>(null);

  // Prevent concurrent /me calls from clobbering each other (e.g. user
  // double-clicks the org-switcher). Latest wins.
  const inFlight = useRef<number>(0);

  /**
   * Load /me carrying the given org/brand override (or whatever's persisted
   * if not given). Reconciles the response and writes:
   *   - React state (active{Org,Brand}Id, me)
   *   - localStorage
   *   - header cache (so the NEXT fetch picks up the new tenant)
   *   - Sentry tags
   */
  const loadMe = useCallback(
    async (override?: { organizationId?: string; brandId?: string }) => {
      const ticket = ++inFlight.current;

      const persisted = readPersistedSelection();
      const requestedOrg = override?.organizationId ?? persisted.organization_id;
      const requestedBrand = override?.brandId ?? persisted.brand_id;

      const tenantSelectionChanged = (
        resolvedOrgId: string | null,
        resolvedBrandId: string | null,
      ) =>
        persisted.organization_id !== resolvedOrgId ||
        persisted.brand_id !== resolvedBrandId;

      // Deliberately DO NOT prime the header cache with the persisted org
      // here. /me carries it as an explicit override below, so the backend
      // still resolves the persisted choice on cold boot — but priming an
      // UNVALIDATED org id would let a brand-scoped page request fire with a
      // stale org before /me confirms membership (→ 403 "Not a member of
      // this organization"). The cache is populated only AFTER /me validates
      // the org against the user's memberships (see the safeguard below).

      try {
        const resp = await api.me({
          organizationId: requestedOrg,
          brandId: requestedBrand,
        });

        // Race-condition guard: a newer call superseded us.
        if (ticket !== inFlight.current) return;

        // --- Stale-selection safeguard -----------------------------------
        // If a persisted org id isn't in the memberships /me returned (left
        // over from a previous session or a different account), it's invalid:
        // drop it so it can never be re-sent, and fall through to the first
        // valid membership. resolveActiveMembership() already performs that
        // fallback; here we additionally PURGE the stale localStorage entry
        // and warn (dev only) so the 403 loop can't recur on reload.
        const requestedOrgIsStale =
          !!requestedOrg &&
          !resp.memberships.some((m) => m.organization.id === requestedOrg);

        const membership = resolveActiveMembership(resp, requestedOrg);
        const requestedBrandIsStale =
          !!requestedBrand &&
          !!membership &&
          !membership.brands.some((b) => b.id === requestedBrand);

        if (requestedOrgIsStale || resp.memberships.length === 0) {
          clearPersistedSelection();
          purgeBrandScopedCaches();
          if (process.env.NODE_ENV !== "production") {
            console.warn(
              resp.memberships.length === 0
                ? "[TenantProvider] /me returned no memberships — cleared persisted tenant selection; routing to onboarding."
                : `[TenantProvider] Persisted organization "${requestedOrg}" is not in the current user's memberships — cleared stale selection; falling back to the first valid membership.`,
            );
          }
        } else if (requestedBrandIsStale) {
          purgeBrandScopedCaches();
          if (process.env.NODE_ENV !== "production") {
            console.warn(
              `[TenantProvider] Persisted brand "${requestedBrand}" is not in the active org — falling back to a valid brand.`,
            );
          }
        }

        const brand = resolveActiveBrand(membership, requestedBrand);

        const resolvedOrgId = membership?.organization.id ?? null;
        const resolvedBrandId = brand?.id ?? null;

        if (
          !requestedOrgIsStale &&
          resp.memberships.length > 0 &&
          tenantSelectionChanged(resolvedOrgId, resolvedBrandId)
        ) {
          purgeBrandScopedCaches();
        }

        // Mirror the RESOLVED (validated) ids into the side channels. The
        // header cache now only ever carries an org id that exists in the
        // user's memberships, so brand-scoped requests can't 403 on a stale id.
        setActiveTenantHeaders({
          organization_id: resolvedOrgId,
          brand_id: resolvedBrandId,
        });
        writePersistedSelection({
          organization_id: resolvedOrgId,
          brand_id: resolvedBrandId,
        });
        setSentryTenant({
          userId: resp.user.id,
          organizationId: resolvedOrgId,
          brandId: resolvedBrandId,
          roleSlugs: membership?.role_slugs ?? [],
        });

        setMe(resp);
        setActiveOrgId(resolvedOrgId);
        setActiveBrandId(resolvedBrandId);
        setError(null);

        if (resp.memberships.length === 0) {
          setStatus("no-memberships");
        } else {
          setStatus("ready");
        }

        // Honor suggested_route only when explicitly enabled. Avoid
        // looping by checking the current path.
        //
        // The no-workspace state (suggested_route "/onboarding") is handled
        // IN-APP by RequireTenant's "Set up your workspace" card — we do NOT
        // auto-redirect to the full-screen wizard. The user stays in the
        // shell and enters the wizard only by clicking "Create workspace".
        // Other suggested routes (e.g. /orgs/select) still redirect.
        if (
          enforceSuggestedRoute &&
          resp.suggested_route &&
          resp.suggested_route !== "/onboarding"
        ) {
          const current =
            typeof window !== "undefined" ? window.location.pathname : "";
          if (
            current !== resp.suggested_route &&
            // Don't kick the user out of an in-progress onboarding step.
            !current.startsWith("/onboarding")
          ) {
            router.push(resp.suggested_route as never);
          }
        }
      } catch (err) {
        if (ticket !== inFlight.current) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setStatus("error");
      }
    },
    [enforceSuggestedRoute, router],
  );

  // Initial load on mount. When Clerk is active and the user is signed in,
  // wait briefly for ClerkTokenBridge to attach a JWT before /me — otherwise
  // hybrid mode resolves the demo-user and the sidebar shows dev-user@pending.local.
  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      if (isClerkActive() && clerkSignedIn) {
        for (let i = 0; i < 20 && !cancelled; i++) {
          const token = await getAuthToken();
          if (token) break;
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
      }
      if (!cancelled) {
        await loadMe();
      }
    };

    void boot();
    return () => {
      cancelled = true;
    };
  }, [loadMe, clerkSignedIn]);

  // Cleanup: drop Sentry tags on unmount so a sign-out doesn't leak the
  // previous user's identity into any subsequent errors.
  useEffect(() => {
    return () => {
      clearSentryTenant();
      setActiveTenantHeaders({ organization_id: null, brand_id: null });
    };
  }, []);

  const switchOrg = useCallback(
    async (organizationId: string) => {
      purgeBrandScopedCaches();
      // Optimistic header update so any in-flight component that just
      // rendered against the new org doesn't accidentally fire with the
      // old org header.
      setActiveTenantHeaders({
        organization_id: organizationId,
        brand_id: null,
      });
      await loadMe({ organizationId });
    },
    [loadMe],
  );

  const switchBrand = useCallback(
    async (brandId: string) => {
      if (brandId !== activeBrandId) {
        purgeBrandScopedCaches();
      }
      setActiveTenantHeaders({
        organization_id: activeOrgId,
        brand_id: brandId,
      });
      await loadMe({
        organizationId: activeOrgId ?? undefined,
        brandId,
      });
    },
    [activeOrgId, activeBrandId, loadMe],
  );

  const refresh = useCallback(() => loadMe(), [loadMe]);

  // Derive everything that consumers actually use from the current
  // {me, activeOrgId, activeBrandId} triple.
  const value = useMemo<TenantContextValue>(() => {
    const membership = me
      ? me.memberships.find((m) => m.organization.id === activeOrgId) ?? null
      : null;
    const brand = membership
      ? membership.brands.find((b) => b.id === activeBrandId) ?? null
      : null;
    const permissions = membership?.permissions ?? [];
    const roleSlugs = membership?.role_slugs ?? [];

    return {
      status,
      error,
      user: me?.user ?? null,
      activeOrg: membership?.organization ?? null,
      activeBrand: brand,
      activeMembership: membership,
      memberships: me?.memberships ?? [],
      permissions,
      roleSlugs,
      can: (slug) => hasPermission(permissions, slug),
      canAll: (slugs) => hasAllPermissions(permissions, slugs),
      canAny: (slugs) => hasAnyPermission(permissions, slugs),
      environment: ENVIRONMENT,
      suggestedRoute: me?.suggested_route ?? null,
      switchOrg,
      switchBrand,
      refresh,
      active: me?.active ?? null,
    };
  }, [
    me,
    activeOrgId,
    activeBrandId,
    status,
    error,
    switchOrg,
    switchBrand,
    refresh,
  ]);

  return (
    <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
  );
}

// ---------------------------------------------------------------------
//  Hooks
// ---------------------------------------------------------------------

export function useTenant(): TenantContextValue {
  const ctx = useContext(TenantContext);
  if (!ctx) {
    throw new Error(
      "useTenant() called outside TenantProvider. " +
        "Wrap your tree (or this subtree) in <TenantProvider> first.",
    );
  }
  return ctx;
}

/**
 * Optional variant — returns null instead of throwing when no provider
 * is mounted. Useful for components that render on both public and
 * private routes (e.g. a shared header).
 */
export function useTenantOptional(): TenantContextValue | null {
  return useContext(TenantContext);
}

/**
 * Convenience: re-export the storage clear so sign-out flows can wipe
 * the persisted selection without importing the lib directly.
 */
export { clearPersistedSelection };
