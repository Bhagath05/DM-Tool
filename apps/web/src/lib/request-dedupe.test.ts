import { afterEach, describe, expect, it } from "vitest";

import {
  __resetRequestDedupeForTests,
  dedupeRequest,
} from "./request-dedupe";

afterEach(() => {
  __resetRequestDedupeForTests();
});

describe("dedupeRequest", () => {
  it("coalesces concurrent calls with the same key", async () => {
    let calls = 0;
    const fn = () => {
      calls += 1;
      return Promise.resolve({ ok: true });
    };

    const [a, b] = await Promise.all([
      dedupeRequest("test-key", fn),
      dedupeRequest("test-key", fn),
    ]);

    expect(calls).toBe(1);
    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
  });

  it("returns cached value within TTL without re-fetching", async () => {
    let calls = 0;
    const fn = () => {
      calls += 1;
      return Promise.resolve("value");
    };

    await dedupeRequest("ttl-key", fn, 60_000);
    await dedupeRequest("ttl-key", fn, 60_000);

    expect(calls).toBe(1);
  });
});
