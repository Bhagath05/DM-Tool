/**
 * Phase 6.2B — content-ops panel pure logic.
 * Pins the field editor round-trip, the version diff, and the review-transition
 * table (which must mirror the backend `_ALLOWED` exactly, or the UI would offer
 * moves the API rejects with 409).
 */

import { describe, expect, it } from "vitest";

import { REVIEW_STATUSES, REVIEW_TRANSITIONS } from "@/lib/api";

import { fromFields, toFields, wordDiff } from "./content-ops-panel";

describe("field editor", () => {
  it("extracts string + string[] fields and ignores others", () => {
    const fields = toFields({
      hook: "A hook",
      hashtags: ["a", "b"],
      score: 42, // ignored — not text
      nested: { x: 1 }, // ignored — not a flat string/list
    });
    expect(fields.map((f) => f.key).sort()).toEqual(["hashtags", "hook"]);
    expect(fields.find((f) => f.key === "hashtags")?.kind).toBe("list");
  });

  it("round-trips through fromFields preserving untouched fields", () => {
    const output = { hook: "old", hashtags: ["a", "b"], score: 42 };
    const fields = toFields(output).map((f) =>
      f.key === "hook" ? { ...f, value: "new" } : f,
    );
    const next = fromFields(output, fields);
    expect(next.hook).toBe("new");
    expect(next.hashtags).toEqual(["a", "b"]);
    expect(next.score).toBe(42); // non-editable field survives untouched
  });

  it("splits list fields on newlines and drops blanks", () => {
    const next = fromFields(
      { tags: [] },
      [{ key: "tags", kind: "list", value: "one\n\n  two  \n" }],
    );
    expect(next.tags).toEqual(["one", "two"]);
  });
});

describe("wordDiff", () => {
  it("marks additions and deletions", () => {
    const d = wordDiff("the quick fox", "the slow fox");
    const del = d.filter((t) => t.op === "del").map((t) => t.t);
    const add = d.filter((t) => t.op === "add").map((t) => t.t);
    expect(del).toContain("quick");
    expect(add).toContain("slow");
    // shared words stay "same"
    expect(d.some((t) => t.op === "same" && t.t === "fox")).toBe(true);
  });

  it("is empty-diff (all same) for identical text", () => {
    const d = wordDiff("hello world", "hello world");
    expect(d.every((t) => t.op === "same")).toBe(true);
  });
});

describe("review transition table", () => {
  it("covers every status", () => {
    for (const s of REVIEW_STATUSES) {
      expect(REVIEW_TRANSITIONS[s]).toBeDefined();
    }
  });

  it("mirrors the backend _ALLOWED table exactly", () => {
    // Any drift here means the UI offers a button the API 409s on.
    expect(REVIEW_TRANSITIONS).toEqual({
      draft: ["in_review", "archived"],
      in_review: ["changes_requested", "approved", "rejected"],
      changes_requested: ["in_review", "draft"],
      approved: ["published", "changes_requested", "archived"],
      rejected: ["draft", "archived"],
      published: ["archived"],
      archived: ["draft"],
    });
  });

  it("only lists known statuses as targets", () => {
    for (const targets of Object.values(REVIEW_TRANSITIONS)) {
      for (const t of targets) expect(REVIEW_STATUSES).toContain(t);
    }
  });
});
