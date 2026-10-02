/**
 * Marketing Board — behavior + safety pins.
 *
 * The board is a view over real backend state (operations work + agent approval
 * requests). It must: render work in the right lifecycle columns; surface a
 * "Needs me" filter from real state; switch Board/List/Timeline over the same
 * data; open a detail panel; let a human make a SAFE workflow decision on AI
 * work (operations PATCH, not an external publish); and route a consequential
 * approval to /ai/approvals rather than acting on it.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApprovalView, WorkItem } from "@/lib/api";

const { work, updateWork, listApprovals } = vi.hoisted(() => ({
  work: vi.fn(),
  updateWork: vi.fn(),
  listApprovals: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    operations: { work, updateWork },
    agentActions: { list: listApprovals },
  },
}));

import MarketingBoardPage from "./page";

function workItem(overrides: Partial<WorkItem> = {}): WorkItem {
  return {
    id: "w1",
    kind: "campaign_update",
    action_type: "campaign_creation",
    title: "Summer sale campaign",
    description: "Prep the summer sale push.",
    rationale: "Sales dip in July; a promo should lift leads.",
    source_kind: "goal",
    priority: "high",
    requires_approval: true,
    auto_eligible: false,
    policy_mode: "always_approve",
    status: "awaiting_approval",
    scheduled_for: null,
    created_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

function approval(overrides: Partial<ApprovalView> = {}): ApprovalView {
  return {
    id: "ap1",
    tool_name: "publish_scheduled_post",
    operation_class: "consequential",
    status: "pending",
    arguments: { scheduled_post_id: "p1" },
    action_fingerprint: "fp",
    autonomy_action_type: "social_publishing",
    policy_mode: "always_approve",
    reason: "Publish the launch post",
    expected_effect: "Goes live on Instagram",
    requested_by_user_id: "u1",
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

afterEach(() => vi.clearAllMocks());

describe("MarketingBoardPage", () => {
  it("renders AI work and approvals in their lifecycle columns", async () => {
    work.mockResolvedValue({ items: [workItem()], awaiting_approval: 1 });
    listApprovals.mockResolvedValue({ items: [approval()] });
    render(<MarketingBoardPage />);
    // Scope to the desktop board (jsdom renders mobile + desktop subtrees).
    const board = await screen.findByTestId("board-columns");
    const needsYou = within(board).getByTestId("board-column-needs_you");
    // both the work item and the pending approval land in "Needs you"
    expect(within(needsYou).getByText("Summer sale campaign")).toBeInTheDocument();
    expect(within(needsYou).getByText("Publish the launch post")).toBeInTheDocument();
  });

  it("shows a 'Needs me' filter driven by real state", async () => {
    work.mockResolvedValue({ items: [workItem({ status: "executed", requires_approval: false })], awaiting_approval: 0 });
    listApprovals.mockResolvedValue({ items: [approval()] });
    render(<MarketingBoardPage />);
    await screen.findByTestId("board-columns");
    fireEvent.click(screen.getByTestId("board-needs-me"));
    const board = screen.getByTestId("board-columns");
    // only the pending approval remains; the executed work item is filtered out
    expect(within(board).getByText("Publish the launch post")).toBeInTheDocument();
    expect(within(board).queryByText("Summer sale campaign")).not.toBeInTheDocument();
  });

  it("switches to List and Timeline over the same data", async () => {
    work.mockResolvedValue({ items: [workItem({ scheduled_for: "2026-02-01T10:00:00Z", status: "queued" })], awaiting_approval: 0 });
    listApprovals.mockResolvedValue({ items: [] });
    render(<MarketingBoardPage />);
    await screen.findByTestId("board-columns");
    fireEvent.click(screen.getByTestId("board-view-list"));
    expect(await screen.findByTestId("board-list")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("board-view-timeline"));
    expect(await screen.findByTestId("board-timeline")).toBeInTheDocument();
  });

  it("opens a detail panel and lets a human make a SAFE workflow decision on AI work", async () => {
    work.mockResolvedValue({ items: [workItem()], awaiting_approval: 1 });
    listApprovals.mockResolvedValue({ items: [] });
    updateWork.mockResolvedValue({});
    render(<MarketingBoardPage />);
    await screen.findByTestId("board-columns");
    fireEvent.click(screen.getAllByTestId("board-card")[0]);
    const detail = await screen.findByTestId("board-detail");
    expect(detail).toHaveTextContent(/Why the Brain prepared this/);
    fireEvent.click(screen.getByTestId("board-approve"));
    // the safe operations PATCH — not an external publish
    await waitFor(() => expect(updateWork).toHaveBeenCalledWith("w1", "approved"));
  });

  it("routes a consequential approval to /ai/approvals instead of acting on it", async () => {
    work.mockResolvedValue({ items: [], awaiting_approval: 0 });
    listApprovals.mockResolvedValue({ items: [approval()] });
    render(<MarketingBoardPage />);
    await screen.findByTestId("board-columns");
    fireEvent.click(screen.getAllByTestId("board-card")[0]);
    const detail = await screen.findByTestId("board-detail");
    expect(detail).toHaveTextContent(/Nothing has run/);
    expect(within(detail).getByRole("link", { name: /review/i })).toHaveAttribute("href", "/ai/approvals");
    // no execute/approve button for a consequential action on the board
    expect(within(detail).queryByTestId("board-approve")).not.toBeInTheDocument();
  });

  it("shows an empty state when there is no work", async () => {
    work.mockResolvedValue({ items: [], awaiting_approval: 0 });
    listApprovals.mockResolvedValue({ items: [] });
    render(<MarketingBoardPage />);
    expect(await screen.findByText(/No work on the board yet/)).toBeInTheDocument();
  });

  it("degrades to empty (not crash) when a source is unavailable", async () => {
    work.mockRejectedValue(new Error("403"));
    listApprovals.mockRejectedValue(new Error("403"));
    render(<MarketingBoardPage />);
    expect(await screen.findByText(/No work on the board yet/)).toBeInTheDocument();
  });
});
