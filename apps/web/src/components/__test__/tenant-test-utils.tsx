/**
 * Test helpers for components that consume `useTenant()`.
 *
 * We don't want to drive every switcher test through a real
 * <TenantProvider> + mocked `/me`. Three reasons:
 *   1. The provider is already comprehensively tested in
 *      `tenant-provider.test.tsx`; reusing it here doubles up.
 *   2. The switchers care about the *shape* of useTenant()'s output,
 *      not the lifecycle that produces it.
 *   3. Driving switchOrg / switchBrand through a real provider would
 *      mean asserting on subsequent /me calls — same coverage we
 *      already have on the provider.
 *
 * So tests inject a hand-built context value via this stub provider.
 */

import { createContext, useContext, type ReactNode } from "react";
import { vi } from "vitest";

import type { TenantContextValue } from "@/components/tenant-provider";

// We can't reuse the real TenantContext because it's private to the
// provider module. Instead this stub creates its own context and we
// vi.mock the provider module to swap useTenant() to read from it.
const StubContext = createContext<TenantContextValue | null>(null);

export function StubTenantProvider({
  value,
  children,
}: {
  value: TenantContextValue;
  children: ReactNode;
}) {
  return <StubContext.Provider value={value}>{children}</StubContext.Provider>;
}

export function useStubTenant(): TenantContextValue {
  const v = useContext(StubContext);
  if (!v) throw new Error("StubTenantProvider missing");
  return v;
}

/**
 * Factory for a default-happy TenantContextValue. Override any field
 * via the partial argument.
 */
export function makeTenantValue(
  over: Partial<TenantContextValue> = {},
): TenantContextValue {
  const defaultMembership = {
    organization: {
      id: "org-1",
      slug: "org-1",
      name: "Org One",
      status: "active",
      member_count: 1,
      brand_count: 2,
    },
    role_slugs: ["admin"],
    permissions: ["content.create"],
    brands: [
      { id: "brand-1", slug: "b1", name: "Brand One", status: "active" },
      { id: "brand-2", slug: "b2", name: "Brand Two", status: "active" },
    ],
    last_active_brand_id: "brand-1",
    joined_at: "2026-01-01T00:00:00Z",
  };
  return {
    status: "ready",
    error: null,
    user: {
      id: "user-1",
      clerk_user_id: "clerk_1",
      email: "u@example.com",
      display_name: null,
      avatar_url: null,
      status: "active",
      last_seen_at: null,
      created_at: "2026-01-01T00:00:00Z",
    },
    activeOrg: defaultMembership.organization,
    activeBrand: defaultMembership.brands[0],
    activeMembership: defaultMembership,
    memberships: [defaultMembership],
    permissions: defaultMembership.permissions,
    roleSlugs: defaultMembership.role_slugs,
    can: (slug) => defaultMembership.permissions.includes(slug),
    canAll: (slugs) =>
      slugs.every((s) => defaultMembership.permissions.includes(s)),
    canAny: (slugs) =>
      slugs.some((s) => defaultMembership.permissions.includes(s)),
    environment: "development",
    suggestedRoute: "/dashboard",
    switchOrg: vi.fn().mockResolvedValue(undefined),
    switchBrand: vi.fn().mockResolvedValue(undefined),
    refresh: vi.fn().mockResolvedValue(undefined),
    active: null,
    ...over,
  };
}

/** Builds an extra membership for multi-org tests. */
export function makeMembership(over: {
  orgId: string;
  orgName?: string;
  brands?: { id: string; name: string }[];
  roles?: string[];
}) {
  return {
    organization: {
      id: over.orgId,
      slug: over.orgId,
      name: over.orgName ?? `Org ${over.orgId}`,
      status: "active",
      member_count: 1,
      brand_count: over.brands?.length ?? 1,
    },
    role_slugs: over.roles ?? ["admin"],
    permissions: ["content.create"],
    brands: (
      over.brands ?? [{ id: `${over.orgId}-b1`, name: "Brand One" }]
    ).map((b) => ({
      id: b.id,
      slug: b.id,
      name: b.name,
      status: "active",
    })),
    last_active_brand_id: null,
    joined_at: "2026-01-01T00:00:00Z",
  };
}
