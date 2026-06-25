/**
 * Phase 10.0 — Command palette filter tests.
 *
 * UI behaviour (open/close, keyboard nav) is best tested with the
 * real component, but the filter is the only piece of business
 * logic worth pinning. Keep it cheap and pure.
 */

import { describe, expect, it } from "vitest";

import { filterEntries } from "@/components/command-palette";

const ENTRIES = [
  { label: "Overview", href: "/overview", group: "Workspace" as const, keywords: ["home"] },
  { label: "Leads", href: "/leads", group: "Growth" as const, keywords: ["pipeline"] },
  { label: "Ads", href: "/ads", group: "Creative" as const, keywords: ["meta"] },
];

describe("filterEntries", () => {
  it("returns all entries on empty query", () => {
    expect(filterEntries(ENTRIES, "")).toEqual(ENTRIES);
    expect(filterEntries(ENTRIES, "   ")).toEqual(ENTRIES);
  });

  it("matches label", () => {
    const r = filterEntries(ENTRIES, "overview");
    expect(r).toHaveLength(1);
    expect(r[0].label).toBe("Overview");
  });

  it("is case-insensitive", () => {
    // Use OVERVIEW — the word doesn't appear as a substring inside
    // any other entry's label/keywords/href so we get a single match.
    expect(filterEntries(ENTRIES, "OVERVIEW")).toHaveLength(1);
  });

  it("matches keywords", () => {
    const r = filterEntries(ENTRIES, "pipeline");
    expect(r[0].label).toBe("Leads");
  });

  it("matches group", () => {
    const r = filterEntries(ENTRIES, "growth");
    expect(r[0].label).toBe("Leads");
  });

  it("matches partial href", () => {
    const r = filterEntries(ENTRIES, "/ad");
    expect(r[0].label).toBe("Ads");
  });

  it("returns empty when no match", () => {
    expect(filterEntries(ENTRIES, "zzz")).toEqual([]);
  });
});
