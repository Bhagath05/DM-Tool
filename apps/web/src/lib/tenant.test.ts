/**
 * Tests for lib/tenant.ts — the framework-free tenant model.
 *
 * These cover:
 *   1. Persistence helpers (read/write/clear) round-trip and survive
 *      corrupt JSON / disabled storage gracefully.
 *   2. The active-header cache is a true module-level singleton.
 *   3. Permission helpers (`hasPermission`, `hasAllPermissions`,
 *      `hasAnyPermission`) handle the null/empty edge cases correctly.
 *   4. `resolveActiveMembership` + `resolveActiveBrand` honor the
 *      persisted preference, then fall back to backend `active`, then
 *      to first-in-list.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  STORAGE_KEY,
  __resetActiveTenantHeadersForTests,
  clearPersistedSelection,
  getActiveTenantHeaders,
  hasAllPermissions,
  hasAnyPermission,
  hasPermission,
  type MeResponse,
  type Membership,
  readPersistedSelection,
  resolveActiveBrand,
  resolveActiveMembership,
  setActiveTenantHeaders,
  writePersistedSelection,
} from "./tenant";

// Factory helpers — keep test data minimal but valid.
function membership(over: Partial<Membership> & { orgId: string }): Membership {
  return {
    organization: {
      id: over.orgId,
      slug: over.orgId,
      name: `Org ${over.orgId}`,
      status: "active",
      member_count: 1,
      brand_count: over.brands?.length ?? 1,
    },
    role_slugs: over.role_slugs ?? ["admin"],
    permissions: over.permissions ?? ["content.create"],
    brands: over.brands ?? [
      {
        id: `${over.orgId}-b1`,
        slug: "b1",
        name: "Brand 1",
        status: "active",
      },
    ],
    last_active_brand_id: over.last_active_brand_id ?? null,
    joined_at: over.joined_at ?? "2026-01-01T00:00:00Z",
  };
}

function me(over: Partial<MeResponse>): MeResponse {
  return {
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
    memberships: [],
    active: null,
    suggested_route: "/dashboard",
    ...over,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
});

afterEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
});

// ---------------------------------------------------------------------
//  Persistence
// ---------------------------------------------------------------------

describe("persisted selection", () => {
  it("returns null/null when storage is empty", () => {
    expect(readPersistedSelection()).toEqual({
      organization_id: null,
      brand_id: null,
    });
  });

  it("round-trips a write", () => {
    writePersistedSelection({ organization_id: "o1", brand_id: "b1" });
    expect(readPersistedSelection()).toEqual({
      organization_id: "o1",
      brand_id: "b1",
    });
  });

  it("clears with clearPersistedSelection", () => {
    writePersistedSelection({ organization_id: "o1", brand_id: "b1" });
    clearPersistedSelection();
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("recovers from corrupted JSON by wiping and returning empty", () => {
    window.localStorage.setItem(STORAGE_KEY, "{not json");
    expect(readPersistedSelection()).toEqual({
      organization_id: null,
      brand_id: null,
    });
    // And the corrupt blob got cleaned up.
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("treats non-string fields as null (defends against schema drift)", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ organization_id: 42, brand_id: { nope: true } }),
    );
    expect(readPersistedSelection()).toEqual({
      organization_id: null,
      brand_id: null,
    });
  });

  it("strips invalid tenant ids and clears storage when both are garbage", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        organization_id: "not valid id!",
        brand_id: "also bad",
      }),
    );
    expect(readPersistedSelection()).toEqual({
      organization_id: null,
      brand_id: null,
    });
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("drops brand when org id is invalid but brand looks valid", () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        organization_id: "",
        brand_id: "brand-1",
      }),
    );
    expect(readPersistedSelection()).toEqual({
      organization_id: null,
      brand_id: null,
    });
  });
});

// ---------------------------------------------------------------------
//  Module-level header cache
// ---------------------------------------------------------------------

describe("active tenant header cache", () => {
  it("starts empty", () => {
    expect(getActiveTenantHeaders()).toEqual({
      organization_id: null,
      brand_id: null,
    });
  });

  it("set + get round-trips", () => {
    setActiveTenantHeaders({ organization_id: "o-X", brand_id: "b-X" });
    expect(getActiveTenantHeaders()).toEqual({
      organization_id: "o-X",
      brand_id: "b-X",
    });
  });

  it("subsequent set overwrites", () => {
    setActiveTenantHeaders({ organization_id: "o1", brand_id: "b1" });
    setActiveTenantHeaders({ organization_id: "o2", brand_id: null });
    expect(getActiveTenantHeaders()).toEqual({
      organization_id: "o2",
      brand_id: null,
    });
  });
});

// ---------------------------------------------------------------------
//  Permission predicates
// ---------------------------------------------------------------------

describe("permission helpers", () => {
  it("hasPermission: false on null/empty", () => {
    expect(hasPermission(null, "content.create")).toBe(false);
    expect(hasPermission(undefined, "content.create")).toBe(false);
    expect(hasPermission([], "content.create")).toBe(false);
  });

  it("hasPermission: true on match", () => {
    expect(hasPermission(["content.create", "ads.create"], "content.create")).toBe(true);
  });

  it("hasAllPermissions: true iff every slug present", () => {
    const perms = ["content.create", "ads.create"];
    expect(hasAllPermissions(perms, ["content.create"])).toBe(true);
    expect(hasAllPermissions(perms, ["content.create", "ads.create"])).toBe(true);
    expect(hasAllPermissions(perms, ["content.create", "billing.manage"])).toBe(false);
  });

  it("hasAnyPermission: true iff at least one slug present", () => {
    const perms = ["content.create"];
    expect(hasAnyPermission(perms, ["billing.manage", "content.create"])).toBe(true);
    expect(hasAnyPermission(perms, ["billing.manage"])).toBe(false);
    expect(hasAnyPermission(null, ["content.create"])).toBe(false);
  });
});

// ---------------------------------------------------------------------
//  Resolution
// ---------------------------------------------------------------------

describe("resolveActiveMembership", () => {
  it("returns null when no memberships", () => {
    expect(resolveActiveMembership(me({}), null)).toBeNull();
  });

  it("honors preferredOrgId when it still exists", () => {
    const m1 = membership({ orgId: "o1" });
    const m2 = membership({ orgId: "o2" });
    const result = resolveActiveMembership(me({ memberships: [m1, m2] }), "o2");
    expect(result?.organization.id).toBe("o2");
  });

  it("falls through to backend `active` when preferredOrgId is stale", () => {
    const m1 = membership({ orgId: "o1" });
    const result = resolveActiveMembership(
      me({
        memberships: [m1],
        active: {
          organization_id: "o1",
          brand_id: null,
          role_slugs: [],
          permissions: [],
        },
      }),
      "o-deleted",
    );
    expect(result?.organization.id).toBe("o1");
  });

  it("defaults to first membership when nothing else matches", () => {
    const m1 = membership({ orgId: "o1" });
    const m2 = membership({ orgId: "o2" });
    expect(
      resolveActiveMembership(me({ memberships: [m1, m2] }), null)
        ?.organization.id,
    ).toBe("o1");
  });
});

describe("resolveActiveBrand", () => {
  const m = membership({
    orgId: "o1",
    brands: [
      { id: "b1", slug: "b1", name: "B1", status: "active" },
      { id: "b2", slug: "b2", name: "B2", status: "active" },
    ],
    last_active_brand_id: "b2",
  });

  it("honors preferredBrandId", () => {
    expect(resolveActiveBrand(m, "b1")?.id).toBe("b1");
  });

  it("falls back to last_active_brand_id when no preference", () => {
    expect(resolveActiveBrand(m, null)?.id).toBe("b2");
  });

  it("returns first brand when both preference and last-active are stale", () => {
    const stale = { ...m, last_active_brand_id: "b-gone" };
    expect(resolveActiveBrand(stale, "b-also-gone")?.id).toBe("b1");
  });

  it("returns null when membership is null or has no brands", () => {
    expect(resolveActiveBrand(null, "b1")).toBeNull();
    expect(
      resolveActiveBrand({ ...m, brands: [] }, "b1"),
    ).toBeNull();
  });
});
