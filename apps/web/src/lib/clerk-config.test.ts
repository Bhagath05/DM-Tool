/**
 * NEXT_PUBLIC_AUTH_MODE + Clerk key truth table.
 *
 * Pins the contract that `isClerkActive()` returns true ONLY when:
 *   - NEXT_PUBLIC_AUTH_MODE = "clerk", AND
 *   - NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY is a structurally valid key
 *
 * Demo mode short-circuits regardless of whether keys are present —
 * the demo journey must not accidentally surface Clerk UI.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  getAuthMode,
  isAuthEnforced,
  isClerkActive,
  isClerkConfigured,
  isDemoMode,
} from "./clerk-config";

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  delete process.env.NEXT_PUBLIC_AUTH_MODE;
  delete process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
});

afterEach(() => {
  // Restore so other test files don't see leaked env.
  for (const k of Object.keys(process.env)) {
    if (k.startsWith("NEXT_PUBLIC_")) delete process.env[k];
  }
  Object.assign(process.env, ORIGINAL_ENV);
});

describe("getAuthMode", () => {
  it("defaults to 'demo' when env is unset", () => {
    expect(getAuthMode()).toBe("demo");
  });
  it("returns 'clerk' when env=clerk", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    expect(getAuthMode()).toBe("clerk");
  });
  it("returns 'hybrid' when env=hybrid", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    expect(getAuthMode()).toBe("hybrid");
  });
  it("returns 'demo' for any unrecognised value", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "wat";
    expect(getAuthMode()).toBe("demo");
  });
  it("returns 'demo' when explicitly set to 'demo'", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    expect(getAuthMode()).toBe("demo");
  });
});

describe("isAuthEnforced", () => {
  it("true only in strict clerk mode", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    expect(isAuthEnforced()).toBe(true);
  });
  it("false in hybrid mode (auth optional)", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    expect(isAuthEnforced()).toBe(false);
  });
  it("false in demo mode", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    expect(isAuthEnforced()).toBe(false);
  });
});

describe("isDemoMode", () => {
  it("true when mode is demo", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    expect(isDemoMode()).toBe(true);
  });
  it("false when mode is clerk", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    expect(isDemoMode()).toBe(false);
  });
  it("true when env unset (default)", () => {
    expect(isDemoMode()).toBe(true);
  });
});

describe("isClerkActive — truth table", () => {
  // Format: [mode, key, expected]
  const REAL_KEY = "pk_test_aaaabbbbccccddddeeeeffffgggg";

  it("demo mode + no key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    expect(isClerkActive()).toBe(false);
  });

  it("demo mode + real key → false (mode wins)", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = REAL_KEY;
    expect(isClerkActive()).toBe(false);
  });

  it("clerk mode + no key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    expect(isClerkActive()).toBe(false);
  });

  it("clerk mode + placeholder key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_replace_me";
    expect(isClerkActive()).toBe(false);
  });

  it("clerk mode + malformed key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "not-a-clerk-key";
    expect(isClerkActive()).toBe(false);
  });

  it("clerk mode + too-short key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_x";
    expect(isClerkActive()).toBe(false);
  });

  it("clerk mode + real test key → true", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = REAL_KEY;
    expect(isClerkActive()).toBe(true);
  });

  it("clerk mode + real live key → true", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY =
      "pk_live_aaaabbbbccccddddeeeeffff";
    expect(isClerkActive()).toBe(true);
  });

  it("hybrid mode + real key → true (Clerk machinery active alongside demo)", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = REAL_KEY;
    expect(isClerkActive()).toBe(true);
  });

  it("hybrid mode + no key → false (can't run Clerk UI without a key)", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    expect(isClerkActive()).toBe(false);
  });

  it("hybrid mode + placeholder key → false", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY = "pk_test_replace_me";
    expect(isClerkActive()).toBe(false);
  });
});

describe("isClerkConfigured (deprecated alias)", () => {
  it("delegates to isClerkActive", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
    expect(isClerkConfigured()).toBe(isClerkActive());

    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY =
      "pk_test_aaaabbbbccccddddeeeeffff";
    expect(isClerkConfigured()).toBe(isClerkActive());
  });
});
