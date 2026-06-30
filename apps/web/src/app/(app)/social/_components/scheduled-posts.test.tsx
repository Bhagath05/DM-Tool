/**
 * ScheduledPosts — surfaces the publishing pipeline. Pins: live render with
 * status, empty + error states, publish-now / retry actions, RBAC gating,
 * and the audit-history expansion.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublishEvent, ScheduledPost } from "@/lib/api";

const calendarMock = vi.fn();
const publishNowMock = vi.fn();
const retryMock = vi.fn();
const eventsMock = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    publishing: {
      calendar: () => calendarMock(),
      publishNow: (id: string) => publishNowMock(id),
      retry: (id: string) => retryMock(id),
      events: (id: string) => eventsMock(id),
    },
  },
}));

let canValue = true;
vi.mock("@/components/tenant-provider", () => ({
  useTenant: () => ({ can: () => canValue }),
}));

import { ScheduledPosts } from "./scheduled-posts";

const SCHEDULED: ScheduledPost = {
  id: "p1",
  content_asset_id: "a1",
  recommendation_id: null,
  platform: "instagram",
  scheduled_at: new Date(Date.now() + 3 * 86_400_000).toISOString(),
  publish_status: "scheduled",
  platform_post_id: null,
  published_at: null,
  error_message: null,
  attempt_count: 0,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};
const FAILED: ScheduledPost = {
  ...SCHEDULED,
  id: "p2",
  publish_status: "failed",
  error_message: "Instagram token expired",
  attempt_count: 3,
};

describe("ScheduledPosts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    canValue = true;
    calendarMock.mockResolvedValue([SCHEDULED]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders live posts with platform + status", async () => {
    calendarMock.mockResolvedValue([SCHEDULED, FAILED]);
    render(<ScheduledPosts />);
    expect(await screen.findByTestId("scheduled-posts")).toBeInTheDocument();
    expect(screen.getAllByText("Instagram")).toHaveLength(2);
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Instagram token expired")).toBeInTheDocument();
  });

  it("shows an empty state when nothing is scheduled", async () => {
    calendarMock.mockResolvedValue([]);
    render(<ScheduledPosts />);
    expect(
      await screen.findByTestId("scheduled-posts-empty"),
    ).toBeInTheDocument();
  });

  it("shows an error + retry when the calendar fails to load", async () => {
    calendarMock.mockRejectedValue(new Error("boom"));
    render(<ScheduledPosts />);
    expect(
      await screen.findByTestId("scheduled-posts-error"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it("publishes now and reloads the calendar", async () => {
    const user = userEvent.setup();
    publishNowMock.mockResolvedValue(SCHEDULED);
    render(<ScheduledPosts />);
    await user.click(
      await screen.findByRole("button", { name: /publish now/i }),
    );
    await waitFor(() => expect(publishNowMock).toHaveBeenCalledWith("p1"));
    expect(calendarMock).toHaveBeenCalledTimes(2); // initial + reload
  });

  it("retries a failed post", async () => {
    const user = userEvent.setup();
    calendarMock.mockResolvedValue([FAILED]);
    retryMock.mockResolvedValue(FAILED);
    render(<ScheduledPosts />);
    await user.click(await screen.findByRole("button", { name: /retry/i }));
    await waitFor(() => expect(retryMock).toHaveBeenCalledWith("p2"));
  });

  it("hides publish/retry actions without content.create", async () => {
    canValue = false;
    calendarMock.mockResolvedValue([SCHEDULED, FAILED]);
    render(<ScheduledPosts />);
    expect(await screen.findByText("Scheduled")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /publish now/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^retry$/i }),
    ).not.toBeInTheDocument();
  });

  it("loads the audit history when expanded", async () => {
    const user = userEvent.setup();
    const events: PublishEvent[] = [
      { id: "e1", event_type: "scheduled", detail: {}, created_at: "2026-06-01T00:00:00Z" },
      { id: "e2", event_type: "published", detail: {}, created_at: "2026-06-02T00:00:00Z" },
    ];
    eventsMock.mockResolvedValue(events);
    render(<ScheduledPosts />);
    await user.click(await screen.findByRole("button", { name: /history/i }));
    await waitFor(() => expect(eventsMock).toHaveBeenCalledWith("p1"));
    const history = await screen.findByTestId("post-history");
    expect(within(history).getByText("Published")).toBeInTheDocument();
  });
});
