/**
 * UserMenu — logout must return to the dedicated login page.
 *
 * Pins the contract that a signed-in user's <UserButton> is configured with
 * afterSignOutUrl="/sign-in" (never "/" — the public landing page), so
 * clicking Logout lands on the login experience.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Capture the props Clerk's <UserButton> is rendered with.
let userButtonProps: Record<string, unknown> | null = null;
let signedIn = true;

vi.mock("@clerk/nextjs", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) =>
    signedIn ? <>{children}</> : null,
  SignedOut: ({ children }: { children: React.ReactNode }) =>
    signedIn ? null : <>{children}</>,
  UserButton: (props: Record<string, unknown>) => {
    userButtonProps = props;
    return <div data-testid="user-button" />;
  },
}));

let clerkActive = true;
vi.mock("@/lib/clerk-config", () => ({
  isClerkActive: () => clerkActive,
  getAuthMode: () => (clerkActive ? "clerk" : "demo"),
}));

import { UserMenu } from "./user-menu";

beforeEach(() => {
  userButtonProps = null;
  signedIn = true;
  clerkActive = true;
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("UserMenu logout routing", () => {
  it("signed-in UserButton logs out to /sign-in (not the landing page)", () => {
    render(<UserMenu />);
    expect(screen.getByTestId("user-button")).toBeInTheDocument();
    expect(userButtonProps).not.toBeNull();
    expect(userButtonProps?.afterSignOutUrl).toBe("/sign-in");
    expect(userButtonProps?.afterSignOutUrl).not.toBe("/");
  });

  it("anonymous (hybrid demo session) shows the mode badge, not a UserButton", () => {
    signedIn = false;
    render(<UserMenu />);
    expect(screen.queryByTestId("user-button")).toBeNull();
    expect(screen.getByTestId("user-menu-fallback")).toBeInTheDocument();
  });

  it("clerk-inactive renders the fallback badge and no Clerk UI", () => {
    clerkActive = false;
    render(<UserMenu />);
    expect(screen.queryByTestId("user-button")).toBeNull();
    expect(screen.getByTestId("user-menu-fallback")).toBeInTheDocument();
  });
});
