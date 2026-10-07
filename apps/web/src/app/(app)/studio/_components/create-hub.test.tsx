/**
 * Phase 6.4 — Create hub links only to real, canonical creative routes.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CreateHub } from "./create-hub";

// Every destination must be a real App Router page (not a dead/legacy route).
const EXPECTED = [
  "/content",
  "/visuals",
  "/ads",
  "/create/linkedin",
  "/bundles",
  "/landing-pages",
  "/publishing",
];

describe("CreateHub", () => {
  it("renders a Create heading", () => {
    render(<CreateHub />);
    expect(screen.getByRole("heading", { name: /^create$/i })).toBeInTheDocument();
  });

  it("links to exactly the canonical creative routes", () => {
    render(<CreateHub />);
    const hub = screen.getByTestId("create-hub");
    const hrefs = Array.from(hub.querySelectorAll("a[href]")).map((a) => a.getAttribute("href"));
    expect(hrefs.sort()).toEqual([...EXPECTED].sort());
  });

  it("exposes no legacy /create/* generator aliases", () => {
    render(<CreateHub />);
    const hub = screen.getByTestId("create-hub");
    const hrefs = Array.from(hub.querySelectorAll("a[href]")).map((a) => a.getAttribute("href") ?? "");
    for (const dead of ["/create/social-posts", "/create/ads", "/create/creatives", "/studio"]) {
      expect(hrefs).not.toContain(dead);
    }
  });

  it("each capability card has an accessible label", () => {
    render(<CreateHub />);
    const hub = screen.getByTestId("create-hub");
    for (const label of ["Content studio", "Visual studio", "Ad studio", "LinkedIn studio", "Campaign bundles", "Lead pages", "Publishing"]) {
      expect(within(hub).getByText(label)).toBeInTheDocument();
    }
  });
});
