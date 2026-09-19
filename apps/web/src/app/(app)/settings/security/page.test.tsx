/**
 * Settings → Security → Active Sessions now reads the first-party session store
 * and can revoke. Pins: it renders fetched sessions, the current device offers
 * "Sign out" (revokes the current session server-side), a non-current device
 * offers "Revoke" (calls the revoke endpoint), and "Revoke all others" works.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SecuritySession } from "@/lib/api";

const { sessions, revokeSession, revokeAllOtherSessions, signout, push } =
  vi.hoisted(() => ({
    sessions: vi.fn(),
    revokeSession: vi.fn().mockResolvedValue({}),
    revokeAllOtherSessions: vi.fn().mockResolvedValue({ revoked_count: 1, skipped_current: true }),
    signout: vi.fn().mockResolvedValue({ message: "Signed out." }),
    push: vi.fn(),
  }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({ user: { email: "ann@example.com", display_name: "Ann" } }),
}));
vi.mock("@/lib/api", () => ({
  api: {
    auth: { signout },
    security: { sessions, revokeSession, revokeAllOtherSessions },
  },
}));

import SecuritySettingsPage from "./page";

const CURRENT: SecuritySession = {
  id: "sess-current",
  user_agent: "Mozilla/5.0",
  ip: "10.0.0.1",
  last_seen_at: "2026-09-15T10:00:00Z",
  expires_at: "2026-09-29T10:00:00Z",
  revoked_at: null,
  is_current: true,
  is_active: true,
  created_at: "2026-09-15T09:00:00Z",
};
const OTHER: SecuritySession = { ...CURRENT, id: "sess-other", is_current: false };

beforeEach(() => {
  sessions.mockResolvedValue({ sessions: [CURRENT, OTHER] });
});
afterEach(() => vi.clearAllMocks());

describe("Security → Active Sessions (first-party)", () => {
  it("renders fetched sessions with the current device flagged", async () => {
    render(<SecuritySettingsPage />);
    expect(await screen.findByTestId("session-sess-current")).toBeInTheDocument();
    expect(screen.getByTestId("session-sess-other")).toBeInTheDocument();
    // Current device offers sign-out; other device offers revoke.
    expect(screen.getByTestId("session-sess-current-signout")).toBeInTheDocument();
    expect(screen.getByTestId("session-sess-other-revoke")).toBeInTheDocument();
  });

  it("revokes a non-current session", async () => {
    render(<SecuritySettingsPage />);
    fireEvent.click(await screen.findByTestId("session-sess-other-revoke"));
    await waitFor(() => expect(revokeSession).toHaveBeenCalledWith("sess-other"));
  });

  it("current device 'Sign out' revokes the current session and returns to /sign-in", async () => {
    render(<SecuritySettingsPage />);
    fireEvent.click(await screen.findByTestId("session-sess-current-signout"));
    await waitFor(() => expect(signout).toHaveBeenCalledTimes(1));
    expect(push).toHaveBeenCalledWith("/sign-in");
  });

  it("'Revoke all others' calls the revoke-all endpoint", async () => {
    render(<SecuritySettingsPage />);
    await screen.findByTestId("session-sess-current");
    fireEvent.click(screen.getByTestId("security-revoke-all"));
    await waitFor(() => expect(revokeAllOtherSessions).toHaveBeenCalledTimes(1));
  });
});
