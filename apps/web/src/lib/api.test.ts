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
  fetchMock = vi.fn().mockResolvedValue(mockJsonOk({ status: "ok", env: "test" }));
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
});

afterEach(() => {
  __resetActiveTenantHeadersForTests();
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

  it("sends credentials: 'include' so the session cookie travels with every request", async () => {
    await api.health();
    const init = fetchMock.mock.calls.at(-1)![1] as RequestInit;
    expect(init.credentials).toBe("include");
  });

  it("never attaches an Authorization header (no bearer tokens, cookie auth only)", async () => {
    document.cookie = "dmt_csrf=whatever";
    await api.health();
    expect(headersFromLastCall().has("Authorization")).toBe(false);
    document.cookie = "dmt_csrf=; Max-Age=0";
  });

  it("attaches the CSRF header from the cookie on state-changing requests", async () => {
    document.cookie = "dmt_csrf=csrf-token-abc";
    await api.auth.signout(); // POST
    expect(headersFromLastCall().get("X-CSRF-Token")).toBe("csrf-token-abc");
    document.cookie = "dmt_csrf=; Max-Age=0";
  });

  it("omits the CSRF header on safe (GET) requests", async () => {
    document.cookie = "dmt_csrf=csrf-token-abc";
    await api.health(); // GET
    expect(headersFromLastCall().has("X-CSRF-Token")).toBe(false);
    document.cookie = "dmt_csrf=; Max-Age=0";
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
