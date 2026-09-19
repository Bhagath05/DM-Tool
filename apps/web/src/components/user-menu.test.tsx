/**
 * UserMenu — first-party identity + sign-out.
 *
 * Pins that sign-out revokes the server-side session (api.auth.signout) and
 * returns to the dedicated login page (/sign-in), never the public landing.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { push, refresh, signout } = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
  signout: vi.fn().mockResolvedValue({ message: "Signed out." }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));
vi.mock("@/lib/api", () => ({ api: { auth: { signout } } }));

let user: { display_name: string | null; email: string } | null = null;
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({ user }),
}));

import { UserMenu } from "./user-menu";

beforeEach(() => {
  user = { display_name: "Ann Owner", email: "ann@example.com" };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("UserMenu", () => {
  it("shows the signed-in identity and a sign-out control", () => {
    render(<UserMenu />);
    expect(screen.getByText("Ann Owner")).toBeInTheDocument();
    expect(screen.getByTestId("sign-out")).toBeInTheDocument();
  });

  it("falls back to the email when there is no display name", () => {
    user = { display_name: null, email: "ann@example.com" };
    render(<UserMenu />);
    expect(screen.getByText("ann@example.com")).toBeInTheDocument();
  });

  it("sign-out revokes the session and returns to /sign-in (never the landing)", async () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByTestId("sign-out"));
    await waitFor(() => expect(signout).toHaveBeenCalledTimes(1));
    expect(push).toHaveBeenCalledWith("/sign-in");
    expect(push).not.toHaveBeenCalledWith("/");
  });
});
