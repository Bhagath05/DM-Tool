/**
 * Phase 6.1 — Sidebar regression pins (aligned to the real App Router).
 *
 * The load-bearing assertions:
 *   1. Primary nav is exactly the approved outcome-oriented IA, and every
 *      href is a real, canonical route (no dead/legacy links).
 *   2. Dropped/duplicate/legacy destinations never appear in the primary nav
 *      (they remain reachable by direct URL / command palette only).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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
  "Marketing Brain",
  "Needs Approval",
  "Leads",
  "Opportunities",
  "CRM",
  "Market Intelligence",
  "Creative Studio",
  "Publishing",
  "Measure",
  "Workspace",
];

// Every one of these is a real route (verified against the route tree).
const PRIMARY_HREFS = [
  "/today",
  "/ai",
  "/ai/approvals",
  "/leads",
  "/opportunities",
  "/crm",
  "/grow/market-intelligence",
  "/studio",
  "/publishing",
  "/analytics",
  "/settings",
];

// Legacy/dead/duplicate destinations that must never appear in primary nav.
const BANNED_HREFS = [
  "/overview",
  "/ai-coach",
  "/ai-employee",
  "/brand-brain",
  "/results",
  "/grow/leads",
  "/grow/opportunities",
  "/create/social-posts",
  "/create/ads",
  "/create/creatives",
  "/create/linkedin",
  "/campaigns",
  "/campaign-lab",
  "/trends",
  "/bundles",
  "/landing-pages",
  "/crm/dashboard",
];

function sidebarNavHrefs(): string[] {
  const nav = screen.getByTestId("sidebar-nav");
  return Array.from(nav.querySelectorAll("a[href]")).map(
    (el) => el.getAttribute("href") ?? "",
  );
}

describe("Sidebar — primary nav (Phase 6.1 IA)", () => {
  it("renders the approved outcome-oriented labels", () => {
    render(<Sidebar />);
    const nav = screen.getByTestId("sidebar-nav");
    for (const label of PRIMARY_LABELS) {
      expect(nav.textContent).toContain(label);
    }
  });

  it("links each primary item to its real canonical route", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    for (const href of PRIMARY_HREFS) {
      expect(hrefs).toContain(href);
    }
  });

  it("exposes no legacy/dead/duplicate destinations in primary nav", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    for (const href of BANNED_HREFS) {
      expect(hrefs).not.toContain(href);
    }
    // The removed Pro-tools drawer must not reappear.
    expect(screen.queryByTestId("sidebar-group-advanced")).toBeNull();
  });

  it("regression pin: exactly the documented primary hrefs", () => {
    render(<Sidebar />);
    const hrefs = sidebarNavHrefs();
    expect(hrefs.sort()).toEqual([...PRIMARY_HREFS].sort());
  });
});
