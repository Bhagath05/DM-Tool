/**
 * ObjectStorageNotice — admin-only warning when durable object storage
 * isn't configured. Shown ONLY when persistence is unavailable AND the
 * viewer is an admin; hidden otherwise (incl. errors / non-admins).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StorageStatus } from "@/lib/api";

const storageMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: { system: { storage: () => storageMock() } },
}));

let canValue = true;
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({ can: () => canValue }),
}));

import { ObjectStorageNotice } from "./object-storage-notice";

const UNAVAILABLE: StorageStatus = {
  media_backend: "local",
  environment: "production",
  media_persistence_available: false,
  image_generation_enabled: false,
  asset_exports_enabled: false,
};
const AVAILABLE: StorageStatus = {
  media_backend: "r2",
  environment: "production",
  media_persistence_available: true,
  image_generation_enabled: true,
  asset_exports_enabled: true,
};

describe("ObjectStorageNotice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    canValue = true;
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("warns an admin when persistence is unavailable", async () => {
    storageMock.mockResolvedValue(UNAVAILABLE);
    render(<ObjectStorageNotice />);
    expect(
      await screen.findByTestId("object-storage-notice"),
    ).toBeInTheDocument();
    expect(screen.getByText(/MEDIA_BACKEND/)).toBeInTheDocument();
  });

  it("renders nothing when persistence is available", async () => {
    storageMock.mockResolvedValue(AVAILABLE);
    render(<ObjectStorageNotice />);
    // give the effect a tick
    await waitFor(() => expect(storageMock).toHaveBeenCalled());
    expect(
      screen.queryByTestId("object-storage-notice"),
    ).not.toBeInTheDocument();
  });

  it("renders nothing for non-admins even when unavailable", async () => {
    canValue = false;
    storageMock.mockResolvedValue(UNAVAILABLE);
    render(<ObjectStorageNotice />);
    await waitFor(() => expect(storageMock).toHaveBeenCalled());
    expect(
      screen.queryByTestId("object-storage-notice"),
    ).not.toBeInTheDocument();
  });

  it("renders nothing if the capability check fails", async () => {
    storageMock.mockRejectedValue(new Error("network"));
    render(<ObjectStorageNotice />);
    await waitFor(() => expect(storageMock).toHaveBeenCalled());
    expect(
      screen.queryByTestId("object-storage-notice"),
    ).not.toBeInTheDocument();
  });
});
