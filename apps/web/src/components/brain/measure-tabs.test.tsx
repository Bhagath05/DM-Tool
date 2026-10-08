/**
 * Phase 6.5 — MeasureTabs links only to real, canonical Measure routes and
 * conveys the active tab accessibly (aria-current, not color alone).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MeasureTabs } from "./measure-tabs";

const EXPECTED = ["/analytics", "/performance", "/social", "/campaign-lab", "/history"];

describe("MeasureTabs", () => {
  it("links to exactly the canonical Measure routes", () => {
    render(<MeasureTabs active="analytics" />);
    const nav = screen.getByTestId("measure-tabs");
    const hrefs = Array.from(nav.querySelectorAll("a[href]")).map((a) => a.getAttribute("href"));
    expect(hrefs.sort()).toEqual([...EXPECTED].sort());
  });

  it("marks the active tab with aria-current", () => {
    render(<MeasureTabs active="performance" />);
    const current = screen.getByRole("link", { current: "page" });
    expect(current).toHaveAttribute("href", "/performance");
  });

  it("does not expose trends or campaigns (those are not Measure)", () => {
    render(<MeasureTabs active="analytics" />);
    const nav = screen.getByTestId("measure-tabs");
    const hrefs = Array.from(nav.querySelectorAll("a[href]")).map((a) => a.getAttribute("href") ?? "");
    expect(hrefs).not.toContain("/trends");
    expect(hrefs).not.toContain("/campaigns");
  });
});
