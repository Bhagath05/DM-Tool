import { afterEach, describe, expect, it, vi } from "vitest";

import { isStudioEnabled } from "./studio-config";

const ORIGINAL = process.env.NEXT_PUBLIC_STUDIO_ENABLED;

afterEach(() => {
  process.env.NEXT_PUBLIC_STUDIO_ENABLED = ORIGINAL;
  vi.unstubAllEnvs();
});

describe("isStudioEnabled", () => {
  it("is false by default (dark launch)", () => {
    delete process.env.NEXT_PUBLIC_STUDIO_ENABLED;
    expect(isStudioEnabled()).toBe(false);
  });

  it("is true only for the exact string 'true'", () => {
    process.env.NEXT_PUBLIC_STUDIO_ENABLED = "true";
    expect(isStudioEnabled()).toBe(true);
  });

  it("treats other values as disabled", () => {
    process.env.NEXT_PUBLIC_STUDIO_ENABLED = "1";
    expect(isStudioEnabled()).toBe(false);
  });
});
