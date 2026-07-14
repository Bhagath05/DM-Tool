/**
 * Phase 10.1 — Settings shell test.
 *
 * Pins the contract of the settings sub-nav:
 *   - All 10 routes appear.
 *   - Active route gets the active-state styling (background swap).
 *   - The settings-nav data-testid is stable for downstream tests
 *     that need to assert on navigation.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SettingsLayout from "@/app/(app)/settings/layout";
import { SETTINGS_NAV } from "@/app/(app)/settings/_nav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/organization",
}));

afterEach(() => {
  vi.clearAllMocks();
});

describe("Settings layout", () => {
  it("renders all 10 sub-nav items in the correct order", () => {
    render(
      <SettingsLayout>
        <div>page body</div>
      </SettingsLayout>,
    );
    const nav = screen.getByTestId("settings-nav");
    expect(nav).toBeInTheDocument();

    for (const item of SETTINGS_NAV) {
      const slug = item.href.split("/").pop() as string;
      expect(screen.getByTestId(`settings-nav-${slug}`)).toBeInTheDocument();
    }
    expect(SETTINGS_NAV.map((i) => i.label)).toEqual([
      "Organization",
      "Team",
      "Members",
      "Roles",
      "Audit log",
      "Billing",
      "Integrations",
      "Notifications",
      "Security",
      "Usage & Limits",
    ]);
  });

  it("renders the page header copy", () => {
    render(
      <SettingsLayout>
        <div />
      </SettingsLayout>,
    );
    expect(
      screen.getByRole("heading", { name: /workspace settings/i }),
    ).toBeInTheDocument();
  });

  it("renders children content area", () => {
    render(
      <SettingsLayout>
        <div data-testid="child">hello</div>
      </SettingsLayout>,
    );
    expect(screen.getByTestId("child")).toHaveTextContent("hello");
  });
});
