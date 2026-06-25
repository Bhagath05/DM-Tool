/**
 * ClerkTokenBridge — hybrid/demo must not call getToken() when anonymous.
 */

import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetAuthTokenForTests,
  getAuthToken,
} from "@/lib/auth-token";

const getTokenMock = vi.fn();
const useAuthMock = vi.fn();

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => useAuthMock(),
}));

import { ClerkTokenBridge } from "./clerk-token-bridge";

beforeEach(() => {
  __resetAuthTokenForTests();
  getTokenMock.mockReset();
  useAuthMock.mockReturnValue({
    getToken: getTokenMock,
    isLoaded: false,
    isSignedIn: false,
  });
});

afterEach(() => {
  __resetAuthTokenForTests();
});

describe("ClerkTokenBridge", () => {
  it("does not call Clerk getToken when session is not loaded", async () => {
    render(<ClerkTokenBridge />);
    expect(await getAuthToken()).toBeNull();
    expect(getTokenMock).not.toHaveBeenCalled();
  });

  it("does not call Clerk getToken for anonymous hybrid visitors", async () => {
    useAuthMock.mockReturnValue({
      getToken: getTokenMock,
      isLoaded: true,
      isSignedIn: false,
    });
    render(<ClerkTokenBridge />);
    expect(await getAuthToken()).toBeNull();
    expect(getTokenMock).not.toHaveBeenCalled();
  });

  it("calls Clerk getToken only when loaded and signed in", async () => {
    getTokenMock.mockResolvedValue("jwt-signed-in");
    useAuthMock.mockReturnValue({
      getToken: getTokenMock,
      isLoaded: true,
      isSignedIn: true,
    });
    render(<ClerkTokenBridge />);
    expect(await getAuthToken()).toBe("jwt-signed-in");
    expect(getTokenMock).toHaveBeenCalledTimes(1);
  });
});
