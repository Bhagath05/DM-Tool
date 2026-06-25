/**
 * Founder Experience Audit (Batch 2 / H3) tests.
 *
 * Focused on the objective humanizer because that's the one piece of
 * raw enum vocabulary still surfacing on result-card chip rows.
 * The other studio-card vocabulary changes are hardcoded string swaps
 * and are covered by the existing snapshot of headers; this file
 * locks in the *contract* — a non-marketer reads a verb phrase, not
 * a snake_case enum.
 */

import { describe, expect, it } from "vitest";

import { humanizeObjective } from "./humanize";

describe("humanizeObjective", () => {
  it("turns 'lead_generation' into a founder verb phrase", () => {
    expect(humanizeObjective("lead_generation")).toBe("Get more leads");
  });

  it("treats 'leads' as the same lead-gen intent", () => {
    expect(humanizeObjective("leads")).toBe("Get more leads");
  });

  it("maps brand_awareness / awareness to plain English", () => {
    expect(humanizeObjective("brand_awareness")).toBe("Get noticed");
    expect(humanizeObjective("awareness")).toBe("Get noticed");
  });

  it("maps conversions and sales to the same outcome line", () => {
    expect(humanizeObjective("conversions")).toBe("Close more sales");
    expect(humanizeObjective("sales")).toBe("Close more sales");
  });

  it("maps traffic / engagement / app_installs / retargeting", () => {
    expect(humanizeObjective("traffic")).toBe("Send people to the site");
    expect(humanizeObjective("engagement")).toBe("Spark conversation");
    expect(humanizeObjective("app_installs")).toBe("Get app installs");
    expect(humanizeObjective("retargeting")).toBe("Bring back past visitors");
  });

  it("is case-insensitive", () => {
    expect(humanizeObjective("LEAD_GENERATION")).toBe("Get more leads");
    expect(humanizeObjective("Conversions")).toBe("Close more sales");
  });

  it("falls back to a prettified label for unknown values (never leaks raw snake_case)", () => {
    // We never want the screen to show literal "loyalty_loop" — the
    // fallback at minimum capitalises and de-underscores it.
    expect(humanizeObjective("loyalty_loop")).toBe("Loyalty loop");
  });

  it("returns empty string for null / undefined / empty", () => {
    expect(humanizeObjective(null)).toBe("");
    expect(humanizeObjective(undefined)).toBe("");
    expect(humanizeObjective("")).toBe("");
  });
});
