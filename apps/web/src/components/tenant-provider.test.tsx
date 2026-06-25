/**
 * Tests for TenantProvider — the component that boots /me, holds the
 * active tenant in React state, and mirrors it into the header cache /
 * localStorage / Sentry.
 *
 * Coverage:
 *   1. Boot loads /me and exposes the resolved org/brand via useTenant().
 *   2. switchOrg() refetches with the new org and updates state.
 *   3. switchBrand() carries the current org as well as the new brand.
 *   4. status="no-memberships" when the response has zero memberships.
 *   5. status="error" when /me throws.
 *   6. Permissions exposed via can() reflect the active membership.
 *   7. Module-level header cache stays in sync with React state.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  TenantProvider,
  useTenant,
} from "./tenant-provider";
import {
  __resetActiveTenantHeadersForTests,
  getActiveTenantHeaders,
  type MeResponse,
} from "@/lib/tenant";

// Mock the api module so we control exactly what /me returns per test.
vi.mock("@/lib/api", () => ({
  api: {
    me: vi.fn(),
  },
}));

// Mock the Sentry helpers — we only need to assert they DON'T throw and
// (optionally) that they got called with the right args. Importing the
// real ones would pull in @sentry/nextjs which loads fine in jsdom but
// we'd rather not couple this test to its behaviour.
const setSentryTenantMock = vi.fn();
const clearSentryTenantMock = vi.fn();
vi.mock("@/lib/sentry-tenant", () => ({
  setSentryTenant: (...args: unknown[]) => setSentryTenantMock(...args),
  clearSentryTenant: () => clearSentryTenantMock(),
  captureApiError: vi.fn(),
}));

import { api } from "@/lib/api";

const meMock = api.me as unknown as ReturnType<typeof vi.fn>;

function makeMe(over: Partial<MeResponse> = {}): MeResponse {
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
    memberships: [
      {
        organization: {
          id: "org-1",
          slug: "org-1",
          name: "Org One",
          status: "active",
          member_count: 1,
          brand_count: 1,
        },
        role_slugs: ["admin"],
        permissions: ["content.create", "ads.create"],
        brands: [
          { id: "brand-1", slug: "b1", name: "Brand One", status: "active" },
        ],
        last_active_brand_id: "brand-1",
        joined_at: "2026-01-01T00:00:00Z",
      },
    ],
    active: {
      organization_id: "org-1",
      brand_id: "brand-1",
      role_slugs: ["admin"],
      permissions: ["content.create", "ads.create"],
    },
    suggested_route: "/dashboard",
    ...over,
  };
}

/** Tiny consumer that mirrors useTenant() into the DOM so we can assert
 *  on rendered values via @testing-library queries. */
function Probe() {
  const t = useTenant();
  return (
    <div>
      <div data-testid="status">{t.status}</div>
      <div data-testid="org">{t.activeOrg?.name ?? "—"}</div>
      <div data-testid="brand">{t.activeBrand?.name ?? "—"}</div>
      <div data-testid="role">{t.roleSlugs.join(",")}</div>
      <div data-testid="can-content">
        {t.can("content.create") ? "yes" : "no"}
      </div>
      <div data-testid="can-billing">
        {t.can("billing.manage") ? "yes" : "no"}
      </div>
      <div data-testid="env">{t.environment}</div>
      <button onClick={() => t.switchOrg("org-2")} data-testid="switch-org">
        switch
      </button>
      <button onClick={() => t.switchBrand("brand-2")} data-testid="switch-brand">
        switch brand
      </button>
    </div>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
  meMock.mockReset();
  setSentryTenantMock.mockReset();
  clearSentryTenantMock.mockReset();
});

afterEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
});

describe("TenantProvider boot", () => {
  it("loads /me, transitions to ready, and exposes the active tenant", async () => {
    meMock.mockResolvedValue(makeMe());

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    // Starts in loading.
    expect(screen.getByTestId("status").textContent).toMatch(/loading|ready/);

    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("ready");
    });
    expect(screen.getByTestId("org").textContent).toBe("Org One");
    expect(screen.getByTestId("brand").textContent).toBe("Brand One");
    expect(screen.getByTestId("role").textContent).toBe("admin");
    expect(screen.getByTestId("can-content").textContent).toBe("yes");
    expect(screen.getByTestId("can-billing").textContent).toBe("no");
  });

  it("mirrors resolved tenant into the header cache + Sentry", async () => {
    meMock.mockResolvedValue(makeMe());

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("ready"),
    );

    expect(getActiveTenantHeaders()).toEqual({
      organization_id: "org-1",
      brand_id: "brand-1",
    });
    expect(setSentryTenantMock).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "user-1",
        organizationId: "org-1",
        brandId: "brand-1",
        roleSlugs: ["admin"],
      }),
    );
  });

  it("transitions to no-memberships when /me returns empty", async () => {
    meMock.mockResolvedValue(
      makeMe({
        memberships: [],
        active: null,
        suggested_route: "/onboarding",
      }),
    );

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("no-memberships"),
    );
    expect(screen.getByTestId("org").textContent).toBe("—");
  });

  it("transitions to error when /me throws", async () => {
    meMock.mockRejectedValue(new Error("boom"));

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("error"),
    );
  });
});

describe("TenantProvider switchOrg / switchBrand", () => {
  it("switchOrg refetches with the new org and updates state", async () => {
    const orgOne = makeMe();
    const orgTwoMembership = {
      organization: {
        id: "org-2",
        slug: "org-2",
        name: "Org Two",
        status: "active",
        member_count: 3,
        brand_count: 1,
      },
      role_slugs: ["editor"],
      permissions: ["content.create"],
      brands: [
        { id: "brand-2", slug: "b2", name: "Brand Two", status: "active" },
      ],
      last_active_brand_id: "brand-2",
      joined_at: "2026-02-01T00:00:00Z",
    };
    const orgTwoMe: MeResponse = {
      ...makeMe(),
      memberships: [...makeMe().memberships, orgTwoMembership],
      active: {
        organization_id: "org-2",
        brand_id: "brand-2",
        role_slugs: ["editor"],
        permissions: ["content.create"],
      },
    };

    // Use an arg-based implementation rather than mockResolvedValueOnce
    // because React 19's strict-mode effect-double-invoke would consume
    // the queue out of order and starve the actual `switchOrg` call.
    meMock.mockImplementation(async (opts?: { organizationId?: string }) => {
      if (opts?.organizationId === "org-2") return orgTwoMe;
      return orgOne;
    });

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("org").textContent).toBe("Org One"),
    );

    await act(async () => {
      screen.getByTestId("switch-org").click();
    });

    await waitFor(() =>
      expect(screen.getByTestId("org").textContent).toBe("Org Two"),
    );
    expect(screen.getByTestId("brand").textContent).toBe("Brand Two");
    expect(screen.getByTestId("role").textContent).toBe("editor");

    // Header cache reflects the new org.
    expect(getActiveTenantHeaders().organization_id).toBe("org-2");
    expect(getActiveTenantHeaders().brand_id).toBe("brand-2");

    // At least one /me invocation carried the org-2 override.
    const switchCall = meMock.mock.calls.find(
      (c) => (c[0] as { organizationId?: string } | undefined)?.organizationId === "org-2",
    );
    expect(switchCall).toBeTruthy();
  });

  it("switchBrand carries the current org and the new brand in the next request", async () => {
    const twoBrandsMe: MeResponse = {
      ...makeMe(),
      memberships: [
        {
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
        },
      ],
    };

    const switchedMe: MeResponse = {
      ...twoBrandsMe,
      active: {
        organization_id: "org-1",
        brand_id: "brand-2",
        role_slugs: ["admin"],
        permissions: ["content.create"],
      },
    };

    meMock.mockImplementation(async (opts?: { brandId?: string }) => {
      if (opts?.brandId === "brand-2") return switchedMe;
      return twoBrandsMe;
    });

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("brand").textContent).toBe("Brand One"),
    );

    await act(async () => {
      screen.getByTestId("switch-brand").click();
    });

    await waitFor(() =>
      expect(screen.getByTestId("brand").textContent).toBe("Brand Two"),
    );

    // The brand-2 switch call carried the current org alongside the new brand.
    const switchCall = meMock.mock.calls.find(
      (c) => (c[0] as { brandId?: string } | undefined)?.brandId === "brand-2",
    );
    expect(switchCall).toBeTruthy();
    expect(switchCall![0]).toEqual({
      organizationId: "org-1",
      brandId: "brand-2",
    });
  });
});

describe("TenantProvider persisted selection", () => {
  it("reads persisted selection on boot and passes it as an override to /me", async () => {
    window.localStorage.setItem(
      "aicmo.tenant.selection.v1",
      JSON.stringify({ organization_id: "org-7", brand_id: "brand-9" }),
    );
    meMock.mockResolvedValue(makeMe());

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() => expect(meMock).toHaveBeenCalled());
    const firstCallArgs = meMock.mock.calls[0]?.[0];
    expect(firstCallArgs).toEqual({
      organizationId: "org-7",
      brandId: "brand-9",
    });
  });

  it("writes the resolved selection back to localStorage after load", async () => {
    meMock.mockResolvedValue(makeMe());

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("ready"),
    );

    const stored = window.localStorage.getItem("aicmo.tenant.selection.v1");
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored!)).toEqual({
      organization_id: "org-1",
      brand_id: "brand-1",
    });
  });

  it("drops a stale persisted org not in /me memberships and falls back to the first valid one — never caching the invalid id", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    window.localStorage.setItem(
      "aicmo.tenant.selection.v1",
      JSON.stringify({ organization_id: "org-stale", brand_id: "brand-stale" }),
    );
    meMock.mockResolvedValue(makeMe());

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("ready"),
    );

    // Resolved to the first valid membership, NOT the stale org.
    expect(screen.getByTestId("org").textContent).toBe("Org One");
    // The header cache carries ONLY the validated org — the stale id never
    // reaches a brand-scoped request (which would 403 "Not a member…").
    expect(getActiveTenantHeaders()).toEqual({
      organization_id: "org-1",
      brand_id: "brand-1",
    });
    // The stale localStorage entry was purged + rewritten to the valid one.
    expect(
      JSON.parse(window.localStorage.getItem("aicmo.tenant.selection.v1")!),
    ).toEqual({ organization_id: "org-1", brand_id: "brand-1" });
    // Dev-only warning emitted (vitest runs with NODE_ENV !== production).
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining("not in the current user's memberships"),
    );
    warn.mockRestore();
  });

  it("clears a stale persisted selection and goes to no-memberships when /me has none", async () => {
    window.localStorage.setItem(
      "aicmo.tenant.selection.v1",
      JSON.stringify({ organization_id: "org-stale", brand_id: "brand-stale" }),
    );
    meMock.mockResolvedValue(
      makeMe({ memberships: [], active: null, suggested_route: "/onboarding" }),
    );

    render(
      <TenantProvider>
        <Probe />
      </TenantProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("status").textContent).toBe("no-memberships"),
    );
    // No valid org → header cache holds no org id (nothing invalid can be sent).
    expect(getActiveTenantHeaders().organization_id).toBeNull();
    // Persisted org id was dropped.
    const stored = window.localStorage.getItem("aicmo.tenant.selection.v1");
    expect(stored === null || JSON.parse(stored).organization_id === null).toBe(
      true,
    );
  });
});
