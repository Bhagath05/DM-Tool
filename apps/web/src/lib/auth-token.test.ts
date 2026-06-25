/**
 * Tests for lib/auth-token.ts — the getter cache.
 *
 * Covers:
 *   - empty state returns null
 *   - getter is invoked per call (not cached)
 *   - getter that throws is treated as "no token" (returns null)
 *   - clear via setAuthTokenGetter(null)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetAuthTokenForTests,
  getAuthToken,
  setAuthTokenGetter,
} from "./auth-token";

beforeEach(() => {
  __resetAuthTokenForTests();
});

afterEach(() => {
  __resetAuthTokenForTests();
});

describe("auth-token cache", () => {
  it("returns null when no getter is set", async () => {
    expect(await getAuthToken()).toBeNull();
  });

  it("returns the value the getter resolves to", async () => {
    setAuthTokenGetter(async () => "jwt-abc");
    expect(await getAuthToken()).toBe("jwt-abc");
  });

  it("invokes the getter on every call (no caching)", async () => {
    let n = 0;
    setAuthTokenGetter(async () => `jwt-${++n}`);
    expect(await getAuthToken()).toBe("jwt-1");
    expect(await getAuthToken()).toBe("jwt-2");
    expect(await getAuthToken()).toBe("jwt-3");
  });

  it("treats a thrown error as null token (lets backend 401 surface)", async () => {
    setAuthTokenGetter(async () => {
      throw new Error("clerk network blip");
    });
    expect(await getAuthToken()).toBeNull();
  });

  it("setAuthTokenGetter(null) clears the getter", async () => {
    setAuthTokenGetter(async () => "jwt-abc");
    setAuthTokenGetter(null);
    expect(await getAuthToken()).toBeNull();
  });

  it("respects the latest getter when overwritten", async () => {
    setAuthTokenGetter(async () => "old");
    setAuthTokenGetter(async () => "new");
    expect(await getAuthToken()).toBe("new");
  });

  it("supports a getter that resolves to null (no active session)", async () => {
    const spy = vi.fn().mockResolvedValue(null);
    setAuthTokenGetter(spy);
    expect(await getAuthToken()).toBeNull();
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("returns null when getter hangs past the timeout (Clerk refresh loop)", async () => {
    vi.useFakeTimers();
    setAuthTokenGetter(
      () => new Promise<string>(() => {
        /* never resolves — simulates Clerk redirect loop */
      }),
    );
    const pending = getAuthToken();
    await vi.advanceTimersByTimeAsync(4_000);
    expect(await pending).toBeNull();
    vi.useRealTimers();
  });
});
