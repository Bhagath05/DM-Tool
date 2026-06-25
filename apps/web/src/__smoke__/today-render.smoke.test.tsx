/**
 * Runtime repro — renders the REAL /today page through the REAL
 * TenantProvider with a signed-in, multi-membership /me, exactly like the
 * live dashboard. If any component on the /dashboard → /today path has a
 * runtime hook-order bug ("Rendered more hooks than during the previous
 * render"), React throws it during this render and the test fails naming
 * the component. A green run proves the current source renders this path
 * cleanly through React's real reconciler.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TodayPage from "@/app/(app)/today/page";
import { TenantProvider } from "@/components/tenant-provider";
import {
  __resetActiveTenantHeadersForTests,
  clearPersistedSelection,
  type MeResponse,
} from "@/lib/tenant";

vi.mock("@/lib/sentry-tenant", () => ({
  setSentryTenant: vi.fn(),
  clearSentryTenant: vi.fn(),
  captureApiError: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/today",
  useSearchParams: () => new URLSearchParams(),
}));

const USER = {
  id: "99999999-9999-9999-9999-999999999999",
  clerk_user_id: "clerk_test_user",
  email: "test@example.com",
  display_name: "Bhagath",
  avatar_url: null,
  status: "active",
  last_seen_at: null,
  created_at: "2026-01-01T00:00:00Z",
};
const ORG_ONE = { id: "11111111-1111-1111-1111-111111111111", slug: "org-one", name: "Acme", status: "active", member_count: 1, brand_count: 2 };
const ORG_TWO = { id: "22222222-2222-2222-2222-222222222222", slug: "org-two", name: "Beta", status: "active", member_count: 3, brand_count: 1 };
const BRAND_A = { id: "aaaaaaaa-0000-0000-0000-000000000000", slug: "a", name: "Acme Coffee", status: "active" };
const BRAND_B = { id: "bbbbbbbb-0000-0000-0000-000000000000", slug: "b", name: "Acme Tea", status: "active" };
const BRAND_C = { id: "cccccccc-0000-0000-0000-000000000000", slug: "c", name: "Beta Main", status: "active" };

const ME: MeResponse = {
  user: USER,
  memberships: [
    { organization: ORG_ONE, role_slugs: ["admin"], permissions: ["content.create"], brands: [BRAND_A, BRAND_B], last_active_brand_id: BRAND_A.id, joined_at: "2026-01-01T00:00:00Z" },
    { organization: ORG_TWO, role_slugs: ["viewer"], permissions: [], brands: [BRAND_C], last_active_brand_id: BRAND_C.id, joined_at: "2026-02-01T00:00:00Z" },
  ],
  active: { organization_id: ORG_ONE.id, brand_id: BRAND_A.id, role_slugs: ["admin"], permissions: ["content.create"] },
  suggested_route: "/today",
} as unknown as MeResponse;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  __resetActiveTenantHeadersForTests();
  clearPersistedSelection();
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    if (url.includes("/users/me")) return jsonResponse(ME);
    // Every card endpoint is best-effort; a 404 routes each card to its
    // own empty/error branch. The point is to exercise the FULL render
    // tree + the loading→ready transition, not the data itself.
    return jsonResponse({ detail: "not found" }, 404);
  }) as unknown as typeof globalThis.fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("today page runtime render (real provider, signed-in user)", () => {
  it("renders the /today tree through the real TenantProvider without a hook-order error", async () => {
    render(
      <TenantProvider>
        <TodayPage />
      </TenantProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("today-page")).toBeInTheDocument();
    });
    // Hero greeting proves useTenant resolved + the page re-rendered after
    // the loading→ready transition (the exact transition that surfaces a
    // "more hooks" violation if one exists).
    expect(screen.getByTestId("today-hero")).toBeInTheDocument();
  });
});
