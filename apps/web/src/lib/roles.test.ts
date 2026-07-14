import { describe, expect, it } from "vitest";

import {
  displayRoleName,
  isOwnerRole,
  memberIsOwner,
  roleColor,
  slugifyRoleName,
} from "./roles";

describe("displayRoleName", () => {
  it("never surfaces Owner — renders it as Admin", () => {
    expect(displayRoleName("owner")).toBe("Admin");
  });
  it("humanizes multi-word slugs", () => {
    expect(displayRoleName("marketing_manager")).toBe("Marketing Manager");
    expect(displayRoleName("performance_marketer")).toBe(
      "Performance Marketer",
    );
  });
});

describe("isOwnerRole / memberIsOwner", () => {
  it("flags the internal owner slug", () => {
    expect(isOwnerRole("owner")).toBe(true);
    expect(isOwnerRole("admin")).toBe(false);
  });
  it("detects an owner among a member's roles", () => {
    expect(memberIsOwner(["owner"])).toBe(true);
    expect(memberIsOwner(["admin", "analyst"])).toBe(false);
  });
});

describe("roleColor", () => {
  it("prefers an explicit color", () => {
    expect(roleColor({ slug: "admin", color: "#123456" })).toBe("#123456");
  });
  it("falls back to a per-slug default", () => {
    expect(roleColor({ slug: "analyst", color: null })).toBe("#a855f7");
  });
  it("falls back to neutral for unknown slugs", () => {
    expect(roleColor({ slug: "growth_lead", color: null })).toBe("#94a3b8");
  });
});

describe("slugifyRoleName", () => {
  it("produces a valid slug", () => {
    expect(slugifyRoleName("Growth Lead")).toBe("growth_lead");
  });
  it("prefixes when a name starts with a non-letter", () => {
    expect(slugifyRoleName("1st Responders")).toMatch(/^[a-z]/);
  });
  it("strips punctuation and trailing separators", () => {
    expect(slugifyRoleName("  VIP!! ")).toBe("vip");
  });
  it("stays within 64 chars", () => {
    expect(slugifyRoleName("a".repeat(120)).length).toBeLessThanOrEqual(64);
  });
});
