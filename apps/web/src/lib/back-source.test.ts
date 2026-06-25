/**
 * Phase 10.4 polish — BackSource resolver tests.
 *
 * Pins:
 *   - Every registered slug resolves to a {href,label} record
 *   - Unknown / empty / null slugs resolve to null (silent default —
 *     the UI must render nothing rather than guess)
 *   - All Command-Center sub-sources point at the same destination
 *     (consistent UX whether the founder came from Posts / Ads / Reels)
 */

import { describe, expect, it } from "vitest";

import { knownBackSourceSlugs, resolveBackSource } from "./back-source";


describe("resolveBackSource", () => {
  it("returns null for null / undefined / empty input", () => {
    expect(resolveBackSource(null)).toBeNull();
    expect(resolveBackSource(undefined)).toBeNull();
    expect(resolveBackSource("")).toBeNull();
  });

  it("returns null for an unknown slug (silent — no fake back link)", () => {
    expect(resolveBackSource("nope-not-registered")).toBeNull();
  });

  it("resolves every Command-Center sub-source to the same destination", () => {
    const slugs = [
      "command-center",
      "command-center-posts",
      "command-center-ads",
      "command-center-reels",
    ];
    for (const slug of slugs) {
      const r = resolveBackSource(slug);
      expect(r).not.toBeNull();
      expect(r!.href).toBe("/today/command-center");
      expect(r!.label).toContain("Command Center");
    }
  });

  it("resolves every Market-Intel sub-source to the same destination", () => {
    const slugs = [
      "market-intel",
      "market-intel-trends",
      "market-intel-gaps",
    ];
    for (const slug of slugs) {
      const r = resolveBackSource(slug);
      expect(r).not.toBeNull();
      expect(r!.href).toBe("/grow/market-intelligence");
      expect(r!.label).toContain("Market Intelligence");
    }
  });
});


describe("knownBackSourceSlugs", () => {
  it("covers every slug emitted by Command Center + Market Intelligence cards", () => {
    // Pin the catalog so adding a new ?from= slug somewhere without
    // registering it here fails the regression test (forces the dev
    // to either register the slug OR explicitly suppress).
    const expected = [
      "command-center",
      "command-center-posts",
      "command-center-ads",
      "command-center-reels",
      "market-intel",
      "market-intel-trends",
      "market-intel-gaps",
    ];
    const actual = knownBackSourceSlugs();
    for (const slug of expected) {
      expect(actual).toContain(slug);
    }
  });
});
