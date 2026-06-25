/**
 * TenantTopbar — composition test.
 *
 * Asserts the topbar composes the switchers + env badge + role badge,
 * and that error state takes over the whole strip.
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

import { TenantTopbar } from "./tenant-topbar";

describe("TenantTopbar", () => {
  it("renders all four slots in the happy path", () => {
    render(
      <StubTenantProvider value={makeTenantValue()}>
        <TenantTopbar />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("tenant-topbar")).toBeInTheDocument();
    expect(screen.getByTestId("org-switcher-single")).toBeInTheDocument();
    expect(screen.getByTestId("brand-switcher-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("environment-badge")).toHaveTextContent(
      /development/i,
    );
    expect(screen.getByTestId("role-badge")).toBeInTheDocument();
  });

  it("renders an error banner instead of switchers on status=error", () => {
    render(
      <StubTenantProvider
        value={makeTenantValue({
          status: "error",
          error: new Error("network down"),
        })}
      >
        <TenantTopbar />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("tenant-topbar-error")).toHaveTextContent(
      /network down/,
    );
    expect(screen.queryByTestId("tenant-topbar")).not.toBeInTheDocument();
  });

  it("hides the environment badge in production so founders never see dev-tool chrome", () => {
    // Founder Experience Audit (C3): the badge is staff-only. Production
    // is the only environment founders see, so it must render nothing there.
    render(
      <StubTenantProvider value={makeTenantValue({ environment: "production" })}>
        <TenantTopbar />
      </StubTenantProvider>,
    );
    expect(screen.queryByTestId("environment-badge")).not.toBeInTheDocument();
  });

  it("keeps the environment badge in staging / dev where the audience is internal", () => {
    render(
      <StubTenantProvider value={makeTenantValue({ environment: "staging" })}>
        <TenantTopbar />
      </StubTenantProvider>,
    );
    expect(screen.getByTestId("environment-badge")).toHaveTextContent(/staging/i);
  });
});
