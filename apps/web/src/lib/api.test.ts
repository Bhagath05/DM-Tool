/**
 * Tests for the tenant-header injection path in lib/api.ts.
 *
 * The full api.ts is ~1500 lines of endpoint wrappers — we test the ONE
 * piece A3 changes: that every outbound request carries
 * X-Organization-Id / X-Brand-Id when the module-level cache (or per-call
 * override) is set.
 *
 * Strategy: stub `globalThis.fetch`, call `api.health()` /
 * `api.me({...})`, inspect the `Headers` that were passed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import {
  __resetAuthTokenForTests,
  setAuthTokenGetter,
} from "./auth-token";
import {
  __resetActiveTenantHeadersForTests,
  setActiveTenantHeaders,
} from "./tenant";

type FetchMock = ReturnType<typeof vi.fn>;

function mockJsonOk(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: FetchMock;

beforeEach(() => {
  __resetActiveTenantHeadersForTests();
  __resetAuthTokenForTests();
  fetchMock = vi.fn().mockResolvedValue(mockJsonOk({ status: "ok", env: "test" }));
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
});

afterEach(() => {
  __resetActiveTenantHeadersForTests();
  __resetAuthTokenForTests();
  vi.restoreAllMocks();
});

function headersFromLastCall(): Headers {
  const lastCall = fetchMock.mock.calls.at(-1);
  if (!lastCall) throw new Error("fetch was not called");
  const init = lastCall[1] as RequestInit;
  return new Headers(init.headers);
}

describe("api.request header injection", () => {
  it("omits tenant headers when cache is empty and no override", async () => {
    await api.health();
    const h = headersFromLastCall();
    expect(h.has("X-Organization-Id")).toBe(false);
    expect(h.has("X-Brand-Id")).toBe(false);
    // Sanity: always sets content-type.
    expect(h.get("Content-Type")).toBe("application/json");
  });

  it("attaches headers from the module-level cache", async () => {
    setActiveTenantHeaders({
      organization_id: "org-123",
      brand_id: "brand-456",
    });
    await api.health();
    const h = headersFromLastCall();
    expect(h.get("X-Organization-Id")).toBe("org-123");
    expect(h.get("X-Brand-Id")).toBe("brand-456");
  });

  it("per-call override beats the cache", async () => {
    setActiveTenantHeaders({
      organization_id: "org-cache",
      brand_id: "brand-cache",
    });
    fetchMock.mockResolvedValueOnce(
      mockJsonOk({
        user: {
          id: "u",
          clerk_user_id: "c",
          email: "e",
          display_name: null,
          avatar_url: null,
          status: "active",
          last_seen_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        memberships: [],
        active: null,
        suggested_route: "/dashboard",
      }),
    );
    await api.me({ organizationId: "org-override", brandId: "brand-override" });
    const h = headersFromLastCall();
    expect(h.get("X-Organization-Id")).toBe("org-override");
    expect(h.get("X-Brand-Id")).toBe("brand-override");
  });

  it("explicit null override suppresses the cached header", async () => {
    setActiveTenantHeaders({
      organization_id: "org-cache",
      brand_id: "brand-cache",
    });
    fetchMock.mockResolvedValueOnce(
      mockJsonOk({
        user: {
          id: "u",
          clerk_user_id: "c",
          email: "e",
          display_name: null,
          avatar_url: null,
          status: "active",
          last_seen_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        memberships: [],
        active: null,
        suggested_route: "/dashboard",
      }),
    );
    await api.me({ organizationId: null, brandId: null });
    const h = headersFromLastCall();
    expect(h.has("X-Organization-Id")).toBe(false);
    expect(h.has("X-Brand-Id")).toBe(false);
  });

  it("omits Authorization when no token getter is set (dev-bypass path)", async () => {
    await api.health();
    const h = headersFromLastCall();
    expect(h.has("Authorization")).toBe(false);
  });

  it("attaches Authorization from the auth-token getter", async () => {
    setAuthTokenGetter(async () => "jwt-from-clerk");
    await api.health();
    const h = headersFromLastCall();
    expect(h.get("Authorization")).toBe("Bearer jwt-from-clerk");
  });

  it("omits Authorization when getter resolves to null (no session)", async () => {
    setAuthTokenGetter(async () => null);
    await api.health();
    const h = headersFromLastCall();
    expect(h.has("Authorization")).toBe(false);
  });

  it("re-invokes the getter on every request (fresh JWT per call)", async () => {
    let n = 0;
    setAuthTokenGetter(async () => `jwt-${++n}`);
    await api.health();
    await api.health();
    await api.health();
    // Each call should carry a different token — proves we're not caching.
    const tokens = fetchMock.mock.calls.map((c) => {
      const init = c[1] as RequestInit;
      return new Headers(init.headers).get("Authorization");
    });
    expect(tokens).toEqual([
      "Bearer jwt-1",
      "Bearer jwt-2",
      "Bearer jwt-3",
    ]);
  });

  it("api.me targets /api/v1/users/me", async () => {
    fetchMock.mockResolvedValueOnce(
      mockJsonOk({
        user: {
          id: "u",
          clerk_user_id: "c",
          email: "e",
          display_name: null,
          avatar_url: null,
          status: "active",
          last_seen_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
        memberships: [],
        active: null,
        suggested_route: "/onboarding",
      }),
    );
    await api.me();
    const lastCall = fetchMock.mock.calls.at(-1)!;
    const url = String(lastCall[0]);
    expect(url.endsWith("/api/v1/users/me")).toBe(true);
  });
});
