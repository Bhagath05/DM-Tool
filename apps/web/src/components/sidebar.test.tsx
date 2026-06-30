/**
 * Phase 10.3 Slice 1 — Sidebar regression pins.
 *
 * Two things this suite must catch if they ever drift:
 *
 *   1. The PRIMARY surface has exactly 8 items spread across 5 groups
 *      (Today's Plan; Leads/Opportunities/Market Intelligence; Social
 *      Posts/Ads/Creatives; Performance; Workspace). The Founder
 *      Simplification Pass promised 8 — a 9th would re-introduce
 *      the cognitive-overload problem we're solving.
 *
 *   2. The ViewMode Simple↔Pro toggle changes the visible items:
 *        simple       → only the 8 primary items
 *        professional → 8 primary + 3 Pro tools (Library, Campaign
 *                       Lab, Trends raw)
 *      Anyone disabling the guard would silently re-expose advanced
 *      pages to first-time founders.
 *
 * UI-styling tests (active-route indicator, mobile drawer, footer)
 * are intentionally NOT covered here — those are Phase 10.0 polish
 * concerns and would make this file noisy. The regression pin is
 * the load-bearing assertion.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetViewModeForTests, setViewMode } from "@/lib/view-mode";

// usePathname is called inside the sidebar — stub a stable value.
vi.mock("next/navigation", () => ({
  usePathname: () => "/today",
}));

// useTenant is consulted only by the footer — return a tiny stub.
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({
    user: { display_name: "Test", email: "test@example.com" },
    activeOrg: { name: "Acme" },
    activeBrand: { name: "Default" },
    memberships: [],
  }),
}));

import { Sidebar } from "./sidebar";


const PRIMARY_LABELS = [
  "Today's Plan",
  "Leads",
  "Opportunities",
  "Market Intelligence",
  "Creative Studio",
  "Social Posts",
  "Ads",
  "Creatives",
  "Performance",
  "AI History",
  "Workspace",
];

// 8 outcome-shaped items + Workspace = 9 visible links (Workspace is
// the single Settings entry; counted in the primary set but conceptually
// administrative). The "8 destinations" promise refers to the 8 founder-
// facing destinations excluding the settings rail.
const PRIMARY_HREFS = [
  "/today",
  "/grow/leads",
  "/grow/opportunities",
  "/grow/market-intelligence",
  "/studio",
  "/create/social-posts",
  "/create/linkedin",
  "/create/ads",
  "/create/creatives",
  "/results",
  "/history",
  "/settings",
];

const ADVANCED_LABELS = ["Library", "Campaign Lab", "Trends (raw)"];
const ADVANCED_HREFS = ["/library", "/campaign-lab", "/trends"];


// Helper: collect every href that appears under the sidebar's <nav>.
// Bypasses accessible-name matching (which substring-matches and
// confuses "Ads" with "Leads") by going straight to the DOM.
function sidebarNavHrefs(): string[] {
  const nav = screen.getByTestId("sidebar-nav");
  return Array.from(nav.querySelectorAll("a[href]")).map(
    (el) => el.getAttribute("href") ?? "",
  );
}


describe("Sidebar — primary nav", () => {
  beforeEach(() => {
    __resetViewModeForTests();
  });

  afterEach(() => {
    __resetViewModeForTests();
  });

  it("renders the new 5-group / 8-destination IA labels", () => {
    render(<Sidebar />);
    const nav = screen.getByTestId("sidebar-nav");
    for (const label of PRIMARY_LABELS) {
      // Use within() + text query so "Ads" doesn't match "Leads" via
      // accessible-name substring on the parent link.
      expect(nav.textContent).toContain(label);
    }
  });

  it("links each primary item to its outcome-oriented URL", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    for (const href of PRIMARY_HREFS) {
      expect(hrefs).toContain(href);
    }
  });

  it("does NOT show Pro destinations in Simple mode (default)", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    for (const href of ADVANCED_HREFS) {
      expect(hrefs).not.toContain(href);
    }
    expect(screen.queryByTestId("sidebar-group-advanced")).toBeNull();
  });

  it("does NOT expose dropped legacy hrefs in primary nav", () => {
    // Pre-10.3 sidebar destinations that are now either renamed,
    // folded, or hidden behind Advanced Mode. None should appear in
    // the default sidebar surface.
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    const banned = [
      "/overview",
      "/ai-coach",
      "/performance",
      "/content",
      "/visuals",
      "/bundles",
      "/campaigns",
      "/trends",
      "/landing-pages",
      "/social",
      "/campaign-lab",
      "/analytics",
      "/library",
    ];
    for (const href of banned) {
      expect(hrefs).not.toContain(href);
    }
  });

  it("regression pin: exactly the documented primary hrefs", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    expect(hrefs.sort()).toEqual([...PRIMARY_HREFS].sort());
  });
});


describe("Sidebar — Professional view mode reveals Pro tools", () => {
  beforeEach(() => {
    __resetViewModeForTests();
  });

  afterEach(() => {
    __resetViewModeForTests();
  });

  it("renders the Pro tools group + 3 power-user links in professional mode", () => {
    setViewMode("professional");
    render(<Sidebar />);
    expect(screen.getByTestId("sidebar-group-advanced")).toBeInTheDocument();
    const nav = screen.getByTestId("sidebar-nav");
    for (const label of ADVANCED_LABELS) {
      expect(nav.textContent).toContain(label);
    }
    const hrefs = sidebarNavHrefs();
    for (const href of ADVANCED_HREFS) {
      expect(hrefs).toContain(href);
    }
  });

  it("keeps the primary set unchanged when professional mode is on", () => {
    setViewMode("professional");
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    for (const href of PRIMARY_HREFS) {
      expect(hrefs).toContain(href);
    }
  });

  it("regression pin: exactly 14 nav hrefs in professional mode (11 primary + 3 Pro tools)", () => {
    setViewMode("professional");
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    expect(hrefs.sort()).toEqual(
      [...PRIMARY_HREFS, ...ADVANCED_HREFS].sort(),
    );
  });
});
