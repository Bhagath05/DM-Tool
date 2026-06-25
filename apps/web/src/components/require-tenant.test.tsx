/**
 * RequireTenant — the page-content gate.
 *
 * Drives the component through every state via the stub provider and
 * asserts on the rendered output. Each branch has its own testid for
 * stable querying.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

import { RequireTenant } from "./require-tenant";

const CHILD_TEXT = "real-page-content-12345";

function harness(value: ReturnType<typeof makeTenantValue>) {
  return render(
    <StubTenantProvider value={value}>
      <RequireTenant>
        <div data-testid="child">{CHILD_TEXT}</div>
      </RequireTenant>
    </StubTenantProvider>,
  );
}

describe("RequireTenant — gating behavior", () => {
  it("renders loading card while status='loading'", () => {
    harness(
      makeTenantValue({
        status: "loading",
        activeOrg: null,
        activeBrand: null,
      }),
    );
    expect(screen.getByTestId("require-tenant-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("renders error card with retry on status='error'", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    harness(
      makeTenantValue({
        status: "error",
        error: new Error("boom"),
        activeOrg: null,
        activeBrand: null,
        refresh,
      }),
    );
    expect(screen.getByTestId("require-tenant-error")).toHaveTextContent(
      /boom/,
    );
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("require-tenant-retry"));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("renders 'create workspace' card when no memberships", () => {
    harness(
      makeTenantValue({
        status: "no-memberships",
        memberships: [],
        activeOrg: null,
        activeMembership: null,
        activeBrand: null,
      }),
    );
    expect(
      screen.getByTestId("require-tenant-missing-org"),
    ).toHaveTextContent(/Set up your workspace/i);
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("renders 'missing brand' card when org present but no active brand", () => {
    const base = makeTenantValue();
    harness(
      makeTenantValue({
        activeMembership: { ...base.activeMembership!, brands: [] },
        activeBrand: null,
      }),
    );
    expect(
      screen.getByTestId("require-tenant-missing-brand"),
    ).toHaveTextContent(/Create your first brand/i);
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("renders children only when status='ready' AND activeOrg AND activeBrand", () => {
    harness(makeTenantValue());
    expect(screen.getByTestId("child")).toHaveTextContent(CHILD_TEXT);
    expect(screen.queryByTestId("require-tenant-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("require-tenant-error")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("require-tenant-missing-org"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("require-tenant-missing-brand"),
    ).not.toBeInTheDocument();
  });

  it("never renders children when status is anything other than ready", () => {
    // Sanity: even if activeOrg + activeBrand are somehow set during a
    // non-ready state, the gate must trust `status` first.
    harness(
      makeTenantValue({
        status: "loading",
      }),
    );
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });
});

describe("RequireTenant — defense in depth", () => {
  it("treats status='ready' + null activeOrg as missing-org (impossible-but-defended)", () => {
    // The provider should never produce this state, but if it ever did,
    // the gate must NOT render children pointed at a tenant that doesn't
    // exist.
    harness(
      makeTenantValue({
        status: "ready",
        activeOrg: null,
        activeBrand: null,
        memberships: [],
      }),
    );
    expect(screen.getByTestId("require-tenant-missing-org")).toBeInTheDocument();
  });
});
