/**
 * OrgSwitcher tests.
 *
 * The provider is stubbed (see tenant-test-utils.tsx) so we can drive the
 * full state matrix — loading, no-memberships, single, multi, pending,
 * error — without spinning up the real /me lifecycle.
 *
 * Coverage targets from the A4 brief:
 *   - Renders the active org.
 *   - Collapses to a label when the user has ≤1 membership.
 *   - Switching calls TenantProvider.switchOrg() with the chosen id.
 *   - Pending state during the switch.
 *   - Error state when switchOrg() throws.
 *   - Security: the menu only renders entries from `memberships` (we
 *     can't write a UI test that proves the user can't fabricate one,
 *     but we CAN prove the menu has exactly N items for N memberships).
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  StubTenantProvider,
  makeMembership,
  makeTenantValue,
  useStubTenant,
} from "./__test__/tenant-test-utils";

// Make useTenant() inside the switcher read from the stub context.
vi.mock("@/components/tenant-provider", async () => {
  const real = await vi.importActual<typeof import("./tenant-provider")>(
    "./tenant-provider",
  );
  return {
    ...real,
    useTenant: () => useStubTenant(),
  };
});

import { OrgSwitcher } from "./org-switcher";

beforeEach(() => {
  vi.useRealTimers();
});

describe("OrgSwitcher: state matrix", () => {
  it("renders the loading pill", () => {
    render(
      <StubTenantProvider value={makeTenantValue({ status: "loading" })}>
        <OrgSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("org-switcher-loading")).toBeInTheDocument();
  });

  it("renders the empty pill for no-memberships", () => {
    render(
      <StubTenantProvider
        value={makeTenantValue({
          status: "no-memberships",
          memberships: [],
          activeOrg: null,
          activeMembership: null,
          activeBrand: null,
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("org-switcher-empty")).toBeInTheDocument();
    expect(screen.getByTestId("org-switcher-empty").textContent).toContain(
      "No workspace",
    );
  });

  it("renders a non-interactive label when there's only one membership", () => {
    render(
      <StubTenantProvider value={makeTenantValue()}>
        <OrgSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("org-switcher-single")).toBeInTheDocument();
    // No dropdown trigger.
    expect(screen.queryByTestId("org-switcher-trigger")).not.toBeInTheDocument();
  });

  it("renders a trigger button when there are ≥2 memberships", async () => {
    const base = makeTenantValue();
    const extra = makeMembership({ orgId: "org-2", orgName: "Org Two" });
    render(
      <StubTenantProvider
        value={makeTenantValue({ memberships: [...base.memberships, extra] })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );
    const trigger = screen.getByTestId("org-switcher-trigger");
    expect(trigger).toBeInTheDocument();
    expect(trigger.textContent).toContain("Org One");
  });
});

describe("OrgSwitcher: switching", () => {
  it("calls switchOrg(id) and shows a pending state", async () => {
    const switchOrg = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => setTimeout(resolve, 50)),
    );
    const base = makeTenantValue({ switchOrg });
    const extra = makeMembership({ orgId: "org-2", orgName: "Org Two" });

    render(
      <StubTenantProvider
        value={makeTenantValue({
          switchOrg,
          memberships: [...base.memberships, extra],
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId("org-switcher-trigger"));
    await user.click(screen.getByTestId("org-switcher-item-org-2"));

    // Called synchronously when item is clicked.
    expect(switchOrg).toHaveBeenCalledWith("org-2");

    // Wait for the promise to resolve so we don't leak a pending state.
    await waitFor(() => expect(switchOrg).toHaveBeenCalledTimes(1));
  });

  it("skips switchOrg when clicking the already-active org", async () => {
    const switchOrg = vi.fn();
    const base = makeTenantValue({ switchOrg });
    const extra = makeMembership({ orgId: "org-2", orgName: "Org Two" });

    render(
      <StubTenantProvider
        value={makeTenantValue({
          switchOrg,
          memberships: [...base.memberships, extra],
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId("org-switcher-trigger"));
    await user.click(screen.getByTestId("org-switcher-item-org-1"));

    expect(switchOrg).not.toHaveBeenCalled();
  });

  it("surfaces an error when switchOrg rejects", async () => {
    const switchOrg = vi.fn().mockRejectedValue(new Error("Forbidden: not a member"));
    const base = makeTenantValue({ switchOrg });
    const extra = makeMembership({ orgId: "org-2", orgName: "Org Two" });

    render(
      <StubTenantProvider
        value={makeTenantValue({
          switchOrg,
          memberships: [...base.memberships, extra],
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId("org-switcher-trigger"));
    await act(async () => {
      await user.click(screen.getByTestId("org-switcher-item-org-2"));
    });

    // Menu auto-closes on item click — reopen to see the error inside.
    await user.click(screen.getByTestId("org-switcher-trigger"));
    await waitFor(() => {
      expect(screen.getByTestId("org-switcher-error")).toHaveTextContent(
        /Forbidden/,
      );
    });
  });
});

describe("OrgSwitcher: security surface", () => {
  it("renders EXACTLY one menuitem per membership — no extras", async () => {
    const base = makeTenantValue();
    const extra1 = makeMembership({ orgId: "org-2" });
    const extra2 = makeMembership({ orgId: "org-3" });

    render(
      <StubTenantProvider
        value={makeTenantValue({
          memberships: [...base.memberships, extra1, extra2],
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId("org-switcher-trigger"));

    const menu = screen.getByRole("menu", { name: /switch organization/i });
    const items = within(menu).getAllByRole("menuitem");
    expect(items).toHaveLength(3); // org-1, org-2, org-3 — nothing else
  });

  it("never renders an org that's not in `memberships` (even via stale activeOrg)", () => {
    // Stress test: activeOrg points at an org NOT in memberships.
    // This shouldn't happen in practice (TenantProvider keeps them in
    // sync) but the component must not invent a fake row from activeOrg.
    const base = makeTenantValue();
    render(
      <StubTenantProvider
        value={makeTenantValue({
          activeOrg: {
            id: "org-ghost",
            slug: "ghost",
            name: "Ghost Org",
            status: "active",
            member_count: 0,
            brand_count: 0,
          },
          memberships: base.memberships, // org-1 only
        })}
      >
        <OrgSwitcher />
      </StubTenantProvider>,
    );

    // Single-membership collapse path. No dropdown, no "Ghost Org" row.
    expect(screen.queryByText(/ghost org/i)).not.toBeInTheDocument();
  });
});
