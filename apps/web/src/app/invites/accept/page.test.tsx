/**
 * /invites/accept — preview before login, accept after login, and
 * graceful handling of expired / revoked / invalid invitations.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InvitePreview } from "@/lib/api";

const nav = { push: vi.fn() };
let searchToken = "tok_abcdef_0123456789";

vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  useSearchParams: () =>
    new URLSearchParams(searchToken ? `token=${searchToken}` : ""),
}));

let signedIn = false;
vi.mock("@clerk/nextjs", () => ({
  SignedIn: ({ children }: { children: React.ReactNode }) =>
    signedIn ? <>{children}</> : null,
  SignedOut: ({ children }: { children: React.ReactNode }) =>
    signedIn ? null : <>{children}</>,
}));

let clerkActive = true;
vi.mock("@/lib/clerk-config", () => ({
  isClerkActive: () => clerkActive,
}));

const previewMock = vi.fn();
const acceptMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    team: {
      previewInvite: (t: string) => previewMock(t),
      acceptInvite: (t: string) => acceptMock(t),
    },
  },
}));

const writeSelMock = vi.fn();
vi.mock("@/lib/tenant", () => ({
  writePersistedSelection: (v: unknown) => writeSelMock(v),
}));

import AcceptInvitePage from "./page";

const PREVIEW: InvitePreview = {
  organization_name: "Acme",
  organization_slug: "acme",
  role_slug: "analyst",
  role_display_name: "Analyst",
  invited_email: "new@acme.com",
  expires_at: new Date(Date.now() + 6 * 86_400_000).toISOString(),
  is_expired: false,
};

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchToken = "tok_abcdef_0123456789";
    signedIn = false;
    clerkActive = true;
    previewMock.mockResolvedValue(PREVIEW);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("previews the invite while logged out and offers a sign-in link that returns here", async () => {
    render(<AcceptInvitePage />);

    expect(await screen.findByText("Join Acme")).toBeInTheDocument();
    // Role is shown in the subtitle and the detail row.
    expect(screen.getAllByText("Analyst").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("new@acme.com")).toBeInTheDocument();

    const link = screen.getByTestId("invite-signin-link");
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("/sign-in?redirect_url=");
    expect(decodeURIComponent(href)).toContain(
      "/invites/accept?token=tok_abcdef_0123456789",
    );
    // No accept button until signed in.
    expect(
      screen.queryByTestId("invite-accept-button"),
    ).not.toBeInTheDocument();
  });

  it("shows an expired invite up front, with no accept action", async () => {
    previewMock.mockResolvedValue({ ...PREVIEW, is_expired: true });
    render(<AcceptInvitePage />);

    expect(
      await screen.findByText("This invitation has expired"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("invite-accept-button"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("invite-signin-link")).not.toBeInTheDocument();
  });

  it("handles an invalid / missing invite gracefully", async () => {
    previewMock.mockRejectedValue(new Error("404 Not Found"));
    render(<AcceptInvitePage />);

    expect(
      await screen.findByText("Invitation unavailable"),
    ).toBeInTheDocument();
  });

  it("flags a link with no token", async () => {
    searchToken = "";
    render(<AcceptInvitePage />);

    expect(
      await screen.findByText(/missing its token/i),
    ).toBeInTheDocument();
    expect(previewMock).not.toHaveBeenCalled();
  });

  it("accepts when signed in, persists the new tenant, and redirects", async () => {
    signedIn = true;
    acceptMock.mockResolvedValue({
      organization_id: "org-1",
      brand_id: "brand-1",
      role_slugs: ["analyst"],
      next_route: "/dashboard",
    });
    const user = userEvent.setup();

    render(<AcceptInvitePage />);

    await user.click(await screen.findByTestId("invite-accept-button"));

    await waitFor(() =>
      expect(acceptMock).toHaveBeenCalledWith("tok_abcdef_0123456789"),
    );
    expect(writeSelMock).toHaveBeenCalledWith({
      organization_id: "org-1",
      brand_id: "brand-1",
    });
    expect(nav.push).toHaveBeenCalledWith("/dashboard");
  });

  it("surfaces the backend reason when accepting a revoked invite", async () => {
    signedIn = true;
    acceptMock.mockRejectedValue(
      new Error("This invite was already revoked."),
    );
    const user = userEvent.setup();

    render(<AcceptInvitePage />);

    await user.click(await screen.findByTestId("invite-accept-button"));

    expect(
      await screen.findByText("This invite was already revoked."),
    ).toBeInTheDocument();
    expect(writeSelMock).not.toHaveBeenCalled();
    expect(nav.push).not.toHaveBeenCalled();
  });
});
