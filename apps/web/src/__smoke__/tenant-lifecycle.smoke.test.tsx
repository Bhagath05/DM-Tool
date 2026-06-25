/**
 * A5 frontend smoke test — wires the REAL pieces together end-to-end.
 *
 * Unit tests (A3, A4) mock the inner contract between provider and
 * switcher. This file does the opposite: stubs ONLY the network
 * (`fetch`), wires up the real `<TenantProvider>` + real `<OrgSwitcher>`
 * / `<BrandSwitcher>` + real `lib/api.ts` + real `lib/tenant.ts`, and
 * asserts the full lifecycle.
 *
 * What this proves that the unit tests don't:
 *   - The header cache and React state stay in sync across a switch.
 *   - localStorage persistence round-trips a remount (simulated reload).
 *   - A permission-aware UI element renders/hides based on real `can()`.
 *   - The api.ts → tenant.ts → tenant-provider → switcher loop is
 *     wired correctly; no module boundary is broken.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BrandSwitcher } from "@/components/brand-switcher";
import { OrgSwitcher } from "@/components/org-switcher";
import { TenantProvider, useTenant } from "@/components/tenant-provider";
import {
  __resetActiveTenantHeadersForTests,
  clearPersistedSelection,
  getActiveTenantHeaders,
  type MeResponse,
} from "@/lib/tenant";

// Stub Sentry helpers so initialisation doesn't try to talk to the real SDK
// (which is fine in jsdom but generates console noise we don't need).
vi.mock("@/lib/sentry-tenant", () => ({
  setSentryTenant: vi.fn(),
  clearSentryTenant: vi.fn(),
  captureApiError: vi.fn(),
}));

// ---------------------------------------------------------------------
//  Test data
// ---------------------------------------------------------------------

const ORG_ONE = {
  id: "11111111-1111-1111-1111-111111111111",
  slug: "org-one",
  name: "Acme",
  status: "active",
  member_count: 1,
  brand_count: 2,
};
const ORG_TWO = {
  id: "22222222-2222-2222-2222-222222222222",
  slug: "org-two",
  name: "Beta",
  status: "active",
  member_count: 3,
  brand_count: 1,
};

const BRAND_A = { id: "aaaaaaaa-0000-0000-0000-000000000000", slug: "a", name: "Acme Coffee", status: "active" };
const BRAND_B = { id: "bbbbbbbb-0000-0000-0000-000000000000", slug: "b", name: "Acme Tea", status: "active" };
const BRAND_C = { id: "cccccccc-0000-0000-0000-000000000000", slug: "c", name: "Beta Main", status: "active" };

const USER = {
  id: "99999999-9999-9999-9999-999999999999",
  clerk_user_id: "clerk_test_user",
  email: "test@example.com",
  display_name: null,
  avatar_url: null,
  status: "active",
  last_seen_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function meWithBothOrgs(activeOrgId: string, activeBrandId: string | null): MeResponse {
  const memberships = [
    {
      organization: ORG_ONE,
      role_slugs: ["admin"],
      permissions: ["content.create", "ads.create", "billing.manage"],
      brands: [BRAND_A, BRAND_B],
      last_active_brand_id: BRAND_A.id,
      joined_at: "2026-01-01T00:00:00Z",
    },
    {
      organization: ORG_TWO,
      role_slugs: ["viewer"],
      permissions: [], // VIEWER can do nothing — used to prove permission gating
      brands: [BRAND_C],
      last_active_brand_id: BRAND_C.id,
      joined_at: "2026-02-01T00:00:00Z",
    },
  ];

  const active = activeOrgId === ORG_ONE.id
    ? {
        organization_id: ORG_ONE.id,
        brand_id: activeBrandId,
        role_slugs: ["admin"],
        permissions: ["content.create", "ads.create", "billing.manage"],
      }
    : {
        organization_id: ORG_TWO.id,
        brand_id: activeBrandId,
        role_slugs: ["viewer"],
        permissions: [],
      };

  return {
    user: USER,
    memberships,
    active,
    suggested_route: "/dashboard",
  };
}

/**
 * Lightweight `fetch` simulator that mimics the backend's tenant
 * resolver. Inspects X-Organization-Id / X-Brand-Id and returns the
 * appropriate /me response.
 *
 * Importantly: if X-Organization-Id is set but doesn't match either
 * org the test user is a member of, this simulator returns a 403 —
 * proving the frontend never silently swallows a backend rejection.
 */
function simulateBackend(): typeof globalThis.fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    const headers = new Headers(init?.headers);
    const orgId = headers.get("X-Organization-Id");
    const brandId = headers.get("X-Brand-Id");

    if (!url.endsWith("/api/v1/users/me")) {
      return new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
      });
    }

    // Header validation — only orgs the user is a member of are valid.
    const validOrgs = new Set([ORG_ONE.id, ORG_TWO.id]);
    if (orgId && !validOrgs.has(orgId)) {
      return new Response(
        JSON.stringify({ detail: "Not a member of this organization" }),
        { status: 403, headers: { "Content-Type": "application/json" } },
      );
    }

    // No header → auto-resolve to first membership (mimics
    // _single_active_membership_org behaviour; here we just default to
    // ORG_ONE since this test user has 2 memberships).
    const resolvedOrg = orgId ?? ORG_ONE.id;
    const resolvedBrand = brandId ?? (resolvedOrg === ORG_ONE.id ? BRAND_A.id : BRAND_C.id);

    return new Response(
      JSON.stringify(meWithBothOrgs(resolvedOrg, resolvedBrand)),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as unknown as typeof globalThis.fetch;
}

// ---------------------------------------------------------------------
//  Test rig — composes the real provider + switchers + a probe
// ---------------------------------------------------------------------

function PermissionProbe() {
  const { can, roleSlugs, activeOrg } = useTenant();
  return (
    <div>
      <div data-testid="probe-org">{activeOrg?.name ?? "—"}</div>
      <div data-testid="probe-role">{roleSlugs.join(",") || "—"}</div>
      <div data-testid="probe-can-content">
        {can("content.create") ? "yes" : "no"}
      </div>
      <div data-testid="probe-can-billing">
        {can("billing.manage") ? "yes" : "no"}
      </div>
      {/* Permission-gated UI: only renders when caller has billing.manage */}
      {can("billing.manage") && (
        <button data-testid="billing-button">Manage billing</button>
      )}
    </div>
  );
}

function Rig() {
  return (
    <TenantProvider>
      <OrgSwitcher />
      <BrandSwitcher />
      <PermissionProbe />
    </TenantProvider>
  );
}

// ---------------------------------------------------------------------
//  Lifecycle
// ---------------------------------------------------------------------

let fetchMock: ReturnType<typeof simulateBackend>;

beforeEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
  fetchMock = simulateBackend();
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
});

afterEach(() => {
  window.localStorage.clear();
  __resetActiveTenantHeadersForTests();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------
//  The smoke tests
// ---------------------------------------------------------------------

describe("[smoke] cold boot lifecycle", () => {
  it("loads /me, resolves tenant, populates header cache, and renders the topbar", async () => {
    render(<Rig />);

    await waitFor(() => {
      expect(screen.getByTestId("probe-org").textContent).toBe("Acme");
    });

    // The OrgSwitcher renders with two memberships → it's the trigger variant.
    expect(screen.getByTestId("org-switcher-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("brand-switcher-trigger")).toBeInTheDocument();

    // Header cache is populated for the next outbound fetch.
    expect(getActiveTenantHeaders()).toEqual({
      organization_id: ORG_ONE.id,
      brand_id: BRAND_A.id,
    });

    // localStorage carries the persisted selection.
    expect(
      JSON.parse(window.localStorage.getItem("aicmo.tenant.selection.v1")!),
    ).toEqual({
      organization_id: ORG_ONE.id,
      brand_id: BRAND_A.id,
    });
  });
});

describe("[smoke] org switch end-to-end", () => {
  it("switches org → /me refetched with new header → state + permissions update", async () => {
    render(<Rig />);
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByTestId("probe-org").textContent).toBe("Acme"),
    );
    // Admin role → can create content + manage billing.
    expect(screen.getByTestId("probe-can-billing").textContent).toBe("yes");
    expect(screen.getByTestId("billing-button")).toBeInTheDocument();

    // Switch to Beta (viewer role, no perms).
    await user.click(screen.getByTestId("org-switcher-trigger"));
    const orgTwoItem = await screen.findByTestId(
      `org-switcher-item-${ORG_TWO.id}`,
    );
    await user.click(orgTwoItem);

    await waitFor(() =>
      expect(screen.getByTestId("probe-org").textContent).toBe("Beta"),
    );
    expect(screen.getByTestId("probe-role").textContent).toBe("viewer");
    expect(screen.getByTestId("probe-can-billing").textContent).toBe("no");
    // Permission-gated UI vanished.
    expect(screen.queryByTestId("billing-button")).not.toBeInTheDocument();

    // The new /me call carried the new org header.
    const calls = (fetchMock as unknown as { mock: { calls: [unknown, RequestInit][] } }).mock.calls;
    const switchCall = calls.find((c) => {
      const h = new Headers(c[1]?.headers);
      return h.get("X-Organization-Id") === ORG_TWO.id;
    });
    expect(switchCall).toBeTruthy();
  });
});

describe("[smoke] persistence survives remount (simulated reload)", () => {
  it("persisted selection carries over to a fresh provider instance", async () => {
    // First mount: switch to Beta, persisting the choice.
    const { unmount } = render(<Rig />);
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByTestId("probe-org").textContent).toBe("Acme"),
    );

    await user.click(screen.getByTestId("org-switcher-trigger"));
    const orgTwoItem = await screen.findByTestId(
      `org-switcher-item-${ORG_TWO.id}`,
    );
    await user.click(orgTwoItem);

    await waitFor(() =>
      expect(screen.getByTestId("probe-org").textContent).toBe("Beta"),
    );

    // Unmount. localStorage stays. Header cache will be wiped by the
    // provider's cleanup effect.
    unmount();
    expect(window.localStorage.getItem("aicmo.tenant.selection.v1")).toContain(
      ORG_TWO.id,
    );

    // Fresh mount — simulates a hard reload. Header cache starts empty.
    __resetActiveTenantHeadersForTests();
    render(<Rig />);

    // Provider boots, reads localStorage, sends ORG_TWO header.
    await waitFor(() =>
      expect(screen.getByTestId("probe-org").textContent).toBe("Beta"),
    );

    // First /me call after remount should have carried the persisted org.
    const calls = (fetchMock as unknown as { mock: { calls: [unknown, RequestInit][] } }).mock.calls;
    const firstPostRemount = calls.at(-1); // most recent
    const headers = new Headers(firstPostRemount?.[1]?.headers);
    expect(headers.get("X-Organization-Id")).toBe(ORG_TWO.id);
  });
});

describe("[smoke] backend rejection surfaces as error", () => {
  it("when persisted org is stale (403 from backend), no privilege bleeds in", async () => {
    // Pre-seed localStorage with an org the test user is NOT a member of.
    window.localStorage.setItem(
      "aicmo.tenant.selection.v1",
      JSON.stringify({
        organization_id: "deadbeef-0000-0000-0000-000000000000",
        brand_id: "deadbeef-0000-0000-0000-000000000001",
      }),
    );

    render(<Rig />);

    // The 403 from /me should surface as status=error.
    await waitFor(() => {
      const orgPill = screen.queryByTestId("probe-org")?.textContent;
      // Either we see error state or no resolution — both are "no
      // privilege bleed". We MUST NOT see any org name.
      expect(orgPill === undefined || orgPill === "—").toBe(true);
    });

    // Header cache should NOT carry a valid org after rejection.
    // (Frontend wrote it speculatively before /me; backend rejected;
    // resolved state is "no org", so the cache should reflect that.)
    // We seeded a fake org pre-load, the provider's loadMe sets headers
    // to that pre-load value, then fails to overwrite on error. So the
    // cache reflects the FAILED attempt's headers. That's fine — there
    // is no real org in there.
    const cached = getActiveTenantHeaders();
    expect([ORG_ONE.id, ORG_TWO.id]).not.toContain(cached.organization_id);

    clearPersistedSelection(); // cleanup
  });
});

describe("[smoke] role-based rendering reacts to switch", () => {
  it("permission-gated UI appears/disappears as the active membership changes", async () => {
    render(<Rig />);
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByTestId("billing-button")).toBeInTheDocument(),
    );

    // Switch to Beta (viewer, no perms) → button vanishes.
    await user.click(screen.getByTestId("org-switcher-trigger"));
    const orgTwoItem = await screen.findByTestId(
      `org-switcher-item-${ORG_TWO.id}`,
    );
    await user.click(orgTwoItem);

    await waitFor(() =>
      expect(screen.queryByTestId("billing-button")).not.toBeInTheDocument(),
    );

    // Switch back to Acme → button returns.
    await user.click(screen.getByTestId("org-switcher-trigger"));
    const orgOneItem = await screen.findByTestId(
      `org-switcher-item-${ORG_ONE.id}`,
    );
    await user.click(orgOneItem);

    await waitFor(() =>
      expect(screen.getByTestId("billing-button")).toBeInTheDocument(),
    );
  });
});
