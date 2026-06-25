/**
 * BrandSwitcher tests — mirror OrgSwitcher's coverage on the brand axis.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  StubTenantProvider,
  makeTenantValue,
  useStubTenant,
} from "./__test__/tenant-test-utils";

vi.mock("@/components/tenant-provider", async () => {
  const real = await vi.importActual<typeof import("./tenant-provider")>(
    "./tenant-provider",
  );
  return { ...real, useTenant: () => useStubTenant() };
});

import { BrandSwitcher } from "./brand-switcher";

beforeEach(() => {
  vi.useRealTimers();
});

describe("BrandSwitcher: state matrix", () => {
  it("renders the loading pill", () => {
    render(
      <StubTenantProvider value={makeTenantValue({ status: "loading" })}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("brand-switcher-loading")).toBeInTheDocument();
  });

  it("renders nothing for no-memberships (OrgSwitcher handles it)", () => {
    const { container } = render(
      <StubTenantProvider
        value={makeTenantValue({
          status: "no-memberships",
          memberships: [],
          activeOrg: null,
          activeMembership: null,
          activeBrand: null,
        })}
      >
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders 'No brand yet' when the org has zero brands", () => {
    const base = makeTenantValue();
    render(
      <StubTenantProvider
        value={makeTenantValue({
          activeMembership: { ...base.activeMembership!, brands: [] },
          activeBrand: null,
        })}
      >
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("brand-switcher-empty")).toHaveTextContent(
      /no brand yet/i,
    );
  });

  it("collapses to a label when the org has exactly one brand", () => {
    const base = makeTenantValue();
    render(
      <StubTenantProvider
        value={makeTenantValue({
          activeMembership: {
            ...base.activeMembership!,
            brands: [base.activeMembership!.brands[0]],
          },
        })}
      >
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("brand-switcher-single")).toBeInTheDocument();
    expect(
      screen.queryByTestId("brand-switcher-trigger"),
    ).not.toBeInTheDocument();
  });

  it("renders a trigger when there are ≥2 brands", () => {
    render(
      <StubTenantProvider value={makeTenantValue()}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("brand-switcher-trigger")).toBeInTheDocument();
  });
});

describe("BrandSwitcher: switching", () => {
  it("calls switchBrand(id) on item click", async () => {
    const switchBrand = vi.fn().mockResolvedValue(undefined);
    render(
      <StubTenantProvider value={makeTenantValue({ switchBrand })}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("brand-switcher-trigger"));
    await user.click(screen.getByTestId("brand-switcher-item-brand-2"));
    expect(switchBrand).toHaveBeenCalledWith("brand-2");
  });

  it("is a no-op when clicking the currently-active brand", async () => {
    const switchBrand = vi.fn();
    render(
      <StubTenantProvider value={makeTenantValue({ switchBrand })}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("brand-switcher-trigger"));
    await user.click(screen.getByTestId("brand-switcher-item-brand-1"));
    expect(switchBrand).not.toHaveBeenCalled();
  });

  it("surfaces an error when switchBrand throws", async () => {
    const switchBrand = vi.fn().mockRejectedValue(new Error("brand not in org"));
    render(
      <StubTenantProvider value={makeTenantValue({ switchBrand })}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("brand-switcher-trigger"));
    await act(async () => {
      await user.click(screen.getByTestId("brand-switcher-item-brand-2"));
    });
    // Reopen menu to see error
    await user.click(screen.getByTestId("brand-switcher-trigger"));
    await waitFor(() => {
      expect(screen.getByTestId("brand-switcher-error")).toHaveTextContent(
        /brand not in org/,
      );
    });
  });
});

describe("BrandSwitcher: only renders brands in the active org", () => {
  it("menu contains exactly the brands from activeMembership.brands", async () => {
    render(
      <StubTenantProvider value={makeTenantValue()}>
        <BrandSwitcher />
      </StubTenantProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("brand-switcher-trigger"));

    const menu = screen.getByRole("menu", { name: /switch brand/i });
    const items = within(menu).getAllByRole("menuitem");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain("Brand One");
    expect(items[1].textContent).toContain("Brand Two");
  });
});
