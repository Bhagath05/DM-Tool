/**
 * Settings · Team — wired to the live `GET /api/v1/team` overview.
 *
 * These tests pin the contract that the page renders REAL data (no
 * fabricated members, no fake invitation counts) and that the invite
 * and revoke affordances call the real endpoints with the right args,
 * gated on the server-supplied `can_invite` flag.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InviteCreateResponse, TeamOverview } from "@/lib/api";

const overviewMock = vi.fn();
const createInviteMock = vi.fn();
const revokeInviteMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      team: {
        overview: () => overviewMock(),
        createInvite: (p: { email: string; role_slug: string }) =>
          createInviteMock(p),
        revokeInvite: (id: string) => revokeInviteMock(id),
        previewInvite: vi.fn(),
        acceptInvite: vi.fn(),
      },
    },
  };
});

vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({
    user: { email: "owner@acme.com" },
    roleSlugs: ["owner"],
  }),
}));

import TeamSettingsPage from "./page";

function buildOverview(overrides: Partial<TeamOverview> = {}): TeamOverview {
  const future = new Date(Date.now() + 6 * 86_400_000).toISOString();
  return {
    members: [
      {
        member_id: "m1",
        user_id: "u1",
        email: "owner@acme.com",
        display_name: "Olivia Owner",
        role_slugs: ["owner"],
        is_owner: true,
        joined_at: "2026-01-02T00:00:00Z",
        last_active_at: null,
      },
      {
        member_id: "m2",
        user_id: "u2",
        email: "ana@acme.com",
        display_name: "Ana Analyst",
        role_slugs: ["analyst"],
        is_owner: false,
        joined_at: "2026-03-10T00:00:00Z",
        last_active_at: null,
      },
    ],
    pending_invites: [
      {
        id: "inv-1",
        organization_id: "o1",
        email: "new@acme.com",
        role_slug: "viewer",
        status: "pending",
        invited_by_user_id: "u1",
        expires_at: future,
        accepted_at: null,
        revoked_at: null,
        created_at: "2026-06-01T00:00:00Z",
        is_expired: false,
      },
    ],
    roles: [
      {
        slug: "owner",
        display_name: "Owner",
        description: "Full access to everything.",
        capabilities: ["Manage billing"],
        can_be_invited_as: false,
        can_be_granted_by_admin: false,
        is_terminal_for_org: true,
      },
      {
        slug: "admin",
        display_name: "Admin",
        description: "Manage members and creative work.",
        capabilities: ["Invite teammates"],
        can_be_invited_as: true,
        can_be_granted_by_admin: true,
        is_terminal_for_org: false,
      },
      {
        slug: "viewer",
        display_name: "Viewer",
        description: "Read-only access.",
        capabilities: ["View insights"],
        can_be_invited_as: true,
        can_be_granted_by_admin: true,
        is_terminal_for_org: false,
      },
    ],
    member_count: 2,
    pending_invite_count: 1,
    can_invite: true,
    can_revoke_owner: false,
    ...overrides,
  };
}

describe("TeamSettingsPage", () => {
  beforeEach(() => {
    overviewMock.mockReset();
    createInviteMock.mockReset();
    revokeInviteMock.mockReset();
    overviewMock.mockResolvedValue(buildOverview());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the real roster, counts, and pending invitation", async () => {
    render(<TeamSettingsPage />);

    // Real members — both emails, not a single fabricated row.
    expect(await screen.findByText("Olivia Owner")).toBeInTheDocument();
    expect(screen.getByText("Ana Analyst")).toBeInTheDocument();

    // Real counts from the overview (2 members, 1 pending).
    expect(screen.getByText("2 active members")).toBeInTheDocument();
    expect(screen.getByText("1 pending invitation")).toBeInTheDocument();

    // Real pending invite row.
    const invites = screen.getByTestId("team-invitations");
    expect(within(invites).getByText("new@acme.com")).toBeInTheDocument();
    expect(within(invites).getByText("Pending")).toBeInTheDocument();
  });

  it("shows invite + revoke affordances when can_invite is true", async () => {
    render(<TeamSettingsPage />);
    expect(
      await screen.findByTestId("team-invite-button"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /revoke invitation for new@acme.com/i }),
    ).toBeInTheDocument();
  });

  it("hides invite + revoke affordances when can_invite is false", async () => {
    overviewMock.mockResolvedValue(buildOverview({ can_invite: false }));
    render(<TeamSettingsPage />);

    expect(await screen.findByText("Olivia Owner")).toBeInTheDocument();
    expect(screen.queryByTestId("team-invite-button")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /revoke invitation/i }),
    ).not.toBeInTheDocument();
  });

  it("creates an invite and surfaces the one-time accept link", async () => {
    const user = userEvent.setup();
    const response: InviteCreateResponse = {
      invite: {
        ...buildOverview().pending_invites[0],
        id: "inv-2",
        email: "fresh@acme.com",
      },
      accept_url: "https://app.example.com/invites/accept?token=abc123xyz",
    };
    createInviteMock.mockResolvedValue(response);

    render(<TeamSettingsPage />);

    await user.click(await screen.findByTestId("team-invite-button"));
    await user.type(
      screen.getByLabelText("Email address"),
      "fresh@acme.com",
    );
    await user.click(
      screen.getByRole("button", { name: /create invitation/i }),
    );

    await waitFor(() =>
      expect(createInviteMock).toHaveBeenCalledWith({
        email: "fresh@acme.com",
        role_slug: "viewer",
      }),
    );

    // The one-time accept URL is shown for the admin to share.
    expect(
      await screen.findByDisplayValue(response.accept_url),
    ).toBeInTheDocument();
    // And the page refetched the overview to reflect the new invite.
    expect(overviewMock).toHaveBeenCalledTimes(2);
  });

  it("revokes a pending invite by id", async () => {
    const user = userEvent.setup();
    revokeInviteMock.mockResolvedValue({});

    render(<TeamSettingsPage />);

    await user.click(
      await screen.findByRole("button", {
        name: /revoke invitation for new@acme.com/i,
      }),
    );

    await waitFor(() =>
      expect(revokeInviteMock).toHaveBeenCalledWith("inv-1"),
    );
  });
});
