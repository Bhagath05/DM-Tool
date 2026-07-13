/**
 * RoleBadge — permission-aware rendering test.
 *
 * The badge surfaces the caller's role on the active org. Not the role
 * the user *could* have on some other org — strictly the resolved active
 * membership's roles. That's what makes it permission-aware: switching
 * tenant changes the badge.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import { RoleBadge } from "./role-badge";

describe("RoleBadge", () => {
  it("renders the primary role when ready", () => {
    render(
      <StubTenantProvider value={makeTenantValue({ roleSlugs: ["admin"] })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("role-badge")).toHaveTextContent(/admin/i);
  });

  it("displays the internal 'owner' role as 'Admin', never 'Owner'", () => {
    // Phase 6.6 — Owner is a DB-only concept; the UI must never show it.
    render(
      <StubTenantProvider value={makeTenantValue({ roleSlugs: ["owner"] })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    const badge = screen.getByTestId("role-badge");
    expect(badge).toHaveTextContent("Admin");
    expect(badge).not.toHaveTextContent(/owner/i);
  });

  it("renders nothing while loading", () => {
    const { container } = render(
      <StubTenantProvider value={makeTenantValue({ status: "loading" })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when the user has no roles", () => {
    const { container } = render(
      <StubTenantProvider value={makeTenantValue({ roleSlugs: [] })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  it("collapses multiple roles into primary + count chip", () => {
    render(
      <StubTenantProvider
        value={makeTenantValue({ roleSlugs: ["editor", "admin"] })}
      >
        <RoleBadge />
      </StubTenantProvider>,
    );
    // Sorted ascending → 'admin' wins primary.
    const badge = screen.getByTestId("role-badge");
    expect(badge).toHaveTextContent(/admin/i);
    expect(badge).toHaveTextContent(/\+1/);
    expect(badge.title).toMatch(/admin.*editor/i);
  });

  it("switches roles when the active membership changes (permission-aware)", () => {
    const { rerender } = render(
      <StubTenantProvider value={makeTenantValue({ roleSlugs: ["admin"] })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("role-badge")).toHaveTextContent(/admin/i);

    rerender(
      <StubTenantProvider value={makeTenantValue({ roleSlugs: ["viewer"] })}>
        <RoleBadge />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("role-badge")).toHaveTextContent(/viewer/i);
  });
});
