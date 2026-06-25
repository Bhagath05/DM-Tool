/**
 * Phase 10.3b — Today's Plan pure-logic tests.
 *
 * Pin the two pieces of derivation logic that don't need a full DOM
 * render to validate:
 *
 *   - readTasksDone() — counts "done"-status entries in the
 *     ActionCenter's localStorage blob; degrades to 0 on missing or
 *     malformed data.
 *
 *   - deriveLeadDelta() — surfaces a "What Changed" row ONLY when the
 *     current lead count is strictly greater than the count we saw on
 *     the previous visit. First visits, no-change visits, and
 *     negative deltas all return null (no fake activity).
 *
 * The component tests for layout / rendering live in the page-level
 * smoke suite that ships with Phase 10.3 Slice 7.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { readTasksDone } from "./day-at-a-glance";
import { deriveLeadDelta, readLastVisit, writeLastVisit } from "./what-changed";

describe("readTasksDone", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns 0 when storage is empty", () => {
    expect(readTasksDone()).toBe(0);
  });

  it("counts entries with status='done'", () => {
    window.localStorage.setItem(
      "aicmo.action-center.v1",
      JSON.stringify({
        a: { status: "done" },
        b: { status: "done" },
        c: { status: "pending" },
        d: { status: "snoozed" },
        e: { status: "done" },
      }),
    );
    expect(readTasksDone()).toBe(3);
  });

  it("returns 0 on malformed JSON", () => {
    window.localStorage.setItem("aicmo.action-center.v1", "not json");
    expect(readTasksDone()).toBe(0);
  });

  it("returns 0 when the blob is not an object", () => {
    window.localStorage.setItem("aicmo.action-center.v1", JSON.stringify("foo"));
    expect(readTasksDone()).toBe(0);
  });

  it("ignores entries missing a status", () => {
    window.localStorage.setItem(
      "aicmo.action-center.v1",
      JSON.stringify({
        a: { status: "done" },
        b: {},
        c: null,
      }),
    );
    expect(readTasksDone()).toBe(1);
  });
});


describe("deriveLeadDelta", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns null on the first visit", () => {
    expect(deriveLeadDelta(5, null)).toBeNull();
  });

  it("returns null when count is unchanged", () => {
    expect(
      deriveLeadDelta(5, { timestamp: "2026-06-01T00:00:00Z", leadCount: 5 }),
    ).toBeNull();
  });

  it("returns null when count decreased (lead deleted / archived)", () => {
    // We never surface a "you lost leads" delta — those decreases come
    // from cleanups, not from genuine pipeline movement.
    expect(
      deriveLeadDelta(3, { timestamp: "2026-06-01T00:00:00Z", leadCount: 5 }),
    ).toBeNull();
  });

  it("surfaces singular when one new lead arrived", () => {
    const item = deriveLeadDelta(6, {
      timestamp: "2026-06-01T00:00:00Z",
      leadCount: 5,
    });
    expect(item).not.toBeNull();
    expect(item?.title).toBe("1 new lead since your last visit");
    expect(item?.tone).toBe("good");
    expect(item?.href).toBe("/grow/leads");
  });

  it("surfaces plural when multiple new leads arrived", () => {
    const item = deriveLeadDelta(10, {
      timestamp: "2026-06-01T00:00:00Z",
      leadCount: 5,
    });
    expect(item?.title).toBe("5 new leads since your last visit");
  });
});


describe("readLastVisit / writeLastVisit", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("returns null when nothing has been written", () => {
    expect(readLastVisit()).toBeNull();
  });

  it("round-trips a snapshot", () => {
    const snap = { timestamp: "2026-06-08T10:00:00Z", leadCount: 42 };
    writeLastVisit(snap);
    expect(readLastVisit()).toEqual(snap);
  });

  it("returns null when the stored blob is malformed", () => {
    window.localStorage.setItem("aicmo.today.last-visit.v1", "{invalid");
    expect(readLastVisit()).toBeNull();
  });

  it("returns null when required keys are missing", () => {
    window.localStorage.setItem(
      "aicmo.today.last-visit.v1",
      JSON.stringify({ leadCount: 5 }), // no timestamp
    );
    expect(readLastVisit()).toBeNull();
  });
});
