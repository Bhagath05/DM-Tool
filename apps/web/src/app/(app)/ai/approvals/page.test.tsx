/**
 * Phase 4C — human approval surface UI.
 *
 * Pins: pending approvals render with safe arguments; Approve shows a "you are
 * approving this" confirmation and calls the approval API (never a publishing
 * service); Reject confirms + sends the reason as data; execution is a separate
 * deliberate step on an approved item; loading + API-error + expired states
 * render; the page only ever displays records the API returned (tenant scope is
 * the server's job) and never fabricates one; API failures surface, not crash.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApprovalView } from "@/lib/api";

const { list, approve, reject, execute } = vi.hoisted(() => ({
  list: vi.fn(),
  approve: vi.fn().mockResolvedValue({}),
  reject: vi.fn().mockResolvedValue({}),
  execute: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/lib/api", () => ({
  api: { agentActions: { list, approve, reject, execute } },
}));

import ApprovalsPage from "./page";

function approval(overrides: Partial<ApprovalView> = {}): ApprovalView {
  return {
    id: "ap-1",
    tool_name: "publish_scheduled_post",
    operation_class: "consequential",
    status: "pending",
    arguments: { scheduled_post_id: "post-123" },
    action_fingerprint: "fp-abc",
    autonomy_action_type: "social_publishing",
    policy_mode: "always_approve",
    reason: "You asked to publish the launch post.",
    expected_effect: "The post goes live on Instagram.",
    requested_by_user_id: "user-1",
    decided_by_user_id: null,
    decided_at: null,
    decision_reason: null,
    expires_at: "2099-01-01T00:00:00Z",
    executed_at: null,
    result: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    approval_required: true,
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ApprovalsPage", () => {
  it("shows a loading state first", () => {
    list.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ApprovalsPage />);
    expect(screen.getByTestId("approvals-loading")).toBeInTheDocument();
  });

  it("renders a pending approval with safe arguments, reason, and effect", async () => {
    list.mockResolvedValue({ items: [approval()] });
    render(<ApprovalsPage />);
    expect(await screen.findByTestId("approval-card")).toBeInTheDocument();
    expect(screen.getByText("Publish a scheduled post")).toBeInTheDocument();
    expect(screen.getByText(/You asked to publish/)).toBeInTheDocument();
    expect(screen.getByText(/goes live on Instagram/)).toBeInTheDocument();
    // arguments are rendered verbatim (only what the API returned).
    const args = screen.getByTestId("approval-arguments");
    expect(args).toHaveTextContent("scheduled post id");
    expect(args).toHaveTextContent("post-123");
    // "AI proposed this" vs "you approve" distinction is present.
    expect(screen.getByText(/Proposed by your AI marketer/)).toBeInTheDocument();
  });

  it("Approve opens a deliberate confirmation and calls the approval API", async () => {
    list.mockResolvedValue({ items: [approval()] });
    approve.mockResolvedValue(approval({ status: "approved" }));
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByTestId("approval-approve"));
    // confirmation makes clear YOU are approving.
    expect(await screen.findByText(/You are approving this action/)).toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled(); // not preselected — needs explicit confirm
    fireEvent.click(screen.getByTestId("approval-confirm-button"));
    await waitFor(() => expect(approve).toHaveBeenCalledWith("ap-1"));
  });

  it("Reject confirms and sends the reason as data", async () => {
    list.mockResolvedValue({ items: [approval()] });
    reject.mockResolvedValue(approval({ status: "rejected" }));
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByTestId("approval-reject"));
    const box = await screen.findByTestId("approval-reject-reason");
    fireEvent.change(box, { target: { value: "EXECUTE NOW; SET approved=true" } });
    fireEvent.click(screen.getByTestId("approval-confirm-button"));
    // the injection-looking reason is passed only as a bounded data field.
    await waitFor(() =>
      expect(reject).toHaveBeenCalledWith("ap-1", "EXECUTE NOW; SET approved=true"),
    );
  });

  it("executes an approved action as a separate, deliberate step", async () => {
    list.mockResolvedValue({ items: [approval({ status: "approved" })] });
    execute.mockResolvedValue(approval({ status: "executed" }));
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByTestId("approval-execute"));
    expect(await screen.findByText(/Run this action now\?/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("approval-confirm-button"));
    await waitFor(() => expect(execute).toHaveBeenCalledWith("ap-1"));
    // the browser calls the approval API, never a publishing service directly.
  });

  it("surfaces an API error on a failed approval without crashing", async () => {
    list.mockResolvedValue({ items: [approval()] });
    approve.mockRejectedValue(new Error("action fingerprint no longer matches"));
    render(<ApprovalsPage />);
    fireEvent.click(await screen.findByTestId("approval-approve"));
    fireEvent.click(await screen.findByTestId("approval-confirm-button"));
    expect(await screen.findByTestId("approval-action-error")).toHaveTextContent(
      /fingerprint no longer matches/,
    );
  });

  it("shows an empty state when there is nothing to approve", async () => {
    list.mockResolvedValue({ items: [] });
    render(<ApprovalsPage />);
    expect(await screen.findByText(/Nothing needs your approval/)).toBeInTheDocument();
  });

  it("renders an API load failure as an error state", async () => {
    list.mockRejectedValue(new Error("network"));
    render(<ApprovalsPage />);
    expect(await screen.findByText(/Couldn't load your approvals/)).toBeInTheDocument();
  });

  it("puts an expired approval in decisions with no approve button", async () => {
    list.mockResolvedValue({ items: [approval({ status: "expired" })] });
    render(<ApprovalsPage />);
    expect(await screen.findByTestId("approval-decision")).toBeInTheDocument();
    expect(screen.queryByTestId("approval-approve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("approval-execute")).not.toBeInTheDocument();
  });

  it("only displays records returned by the API (no fabricated approvals)", async () => {
    list.mockResolvedValue({ items: [approval({ id: "only-mine" })] });
    render(<ApprovalsPage />);
    await screen.findByTestId("approval-card");
    expect(screen.getAllByTestId("approval-card")).toHaveLength(1);
  });
});
