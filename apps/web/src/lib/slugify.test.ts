import { describe, expect, it } from "vitest";

import { SLUG_MAX_LEN, isValidSlug, slugify } from "./slugify";

describe("slugify", () => {
  it("lowercases", () => {
    expect(slugify("Acme")).toBe("acme");
  });
  it("collapses spaces + punctuation", () => {
    expect(slugify("Acme Coffee Co.")).toBe("acme-coffee-co");
  });
  it("strips diacritics", () => {
    expect(slugify("Café Brûlée")).toBe("cafe-brulee");
  });
  it("trims leading/trailing hyphens that fall out of normalization", () => {
    expect(slugify("  !! Acme !! ")).toBe("acme");
  });
  it(`caps length at ${SLUG_MAX_LEN}`, () => {
    const long = "a".repeat(80);
    expect(slugify(long).length).toBeLessThanOrEqual(SLUG_MAX_LEN);
  });
  it("doesn't leave a trailing hyphen after truncation", () => {
    // 39 'a' + a space + 'b' → "aaaa...aaa-b" — truncated at 40 chars
    // shouldn't end with '-'.
    const input = "a".repeat(39) + " b";
    const out = slugify(input);
    expect(out.endsWith("-")).toBe(false);
  });
  it("returns empty string when input has no alnum chars", () => {
    expect(slugify("!!!")).toBe("");
    expect(slugify("   ")).toBe("");
  });
});

describe("isValidSlug", () => {
  it.each(["acme", "acme-coffee", "a", "ac-me-2", "a1b2c3"])(
    "accepts %s",
    (s) => {
      expect(isValidSlug(s)).toBe(true);
    },
  );
  it.each([
    "",
    "Acme",
    "-acme",
    "acme-",
    "ac me",
    "acme!",
    "acme/coffee",
    "a".repeat(41),
  ])("rejects %s", (s) => {
    expect(isValidSlug(s)).toBe(false);
  });
});
