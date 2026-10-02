/**
 * Marketing Brain workspace — behavior + safety pins.
 *
 * The workspace drives the real agent API and renders structured responses. It
 * must: show prompt suggestions when empty; render a Brain answer with evidence
 * status; surface a PROPOSED consequential action as "approval required" and
 * NEVER as executed; render the insufficient-evidence state honestly; and
 * surface API errors without crashing.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentResponse } from "@/lib/api";

const { listConversations, createConversation, listMessages, sendMessage } = vi.hoisted(() => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: { agent: { listConversations, createConversation, listMessages, sendMessage } },
}));

import MarketingBrainPage from "./page";

function response(overrides: Partial<AgentResponse> = {}): AgentResponse {
  return {
    conversation_id: "c1",
    message_id: `m-${Math.random()}`,
    answer: "Your Instagram reels drove most of this week's leads.",
    evidence_status: "ok",
    confidence: 72,
    tools_consulted: ["get_campaign_performance"],
    evidence: [{ label: "get_campaign_performance", source: "analytics", confidence: 72, status: "ok" }],
    actions_blocked: [],
    approval_required: false,
    proposed_actions: [],
    reasoning_summary: {
      intent: "diagnose performance",
      tools_consulted: ["get_campaign_performance"],
      evidence_used: ["get_campaign_performance"],
      key_observations: ["Reels CTR was 2x static posts."],
      uncertainty: "Only 7 days of data.",
      conclusion: "Reels led.",
    },
    ...overrides,
  };
}

afterEach(() => vi.clearAllMocks());

describe("MarketingBrainPage", () => {
  it("shows prompt suggestions when there is no conversation", async () => {
    listConversations.mockResolvedValue({ items: [] });
    render(<MarketingBrainPage />);
    expect(await screen.findByTestId("brain-empty")).toBeInTheDocument();
    expect(screen.getAllByTestId("brain-suggestion").length).toBeGreaterThan(0);
  });

  it("sends a question and renders a structured Brain answer", async () => {
    listConversations.mockResolvedValue({ items: [] });
    createConversation.mockResolvedValue({ id: "c1", title: "q", status: "active", created_at: "", updated_at: "" });
    sendMessage.mockResolvedValue(response());
    render(<MarketingBrainPage />);
    await screen.findByTestId("brain-empty");
    fireEvent.change(screen.getByTestId("brain-input"), { target: { value: "Why did leads rise?" } });
    fireEvent.click(screen.getByTestId("brain-send"));
    expect(await screen.findByTestId("brain-answer")).toBeInTheDocument();
    expect(screen.getByText(/Instagram reels drove most/)).toBeInTheDocument();
    expect(screen.getByText(/Evidence-backed/)).toBeInTheDocument();
    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith("c1", "Why did leads rise?"));
    // no consequential action implied as done
    expect(screen.queryByTestId("brain-approval")).not.toBeInTheDocument();
  });

  it("surfaces a proposed consequential action as approval-required, never done", async () => {
    listConversations.mockResolvedValue({ items: [] });
    createConversation.mockResolvedValue({ id: "c1", title: "q", status: "active", created_at: "", updated_at: "" });
    sendMessage.mockResolvedValue(
      response({
        approval_required: true,
        proposed_actions: [
          {
            tool_name: "publish_scheduled_post",
            operation_class: "consequential",
            approval_id: "ap-1",
            status: "pending",
            action_fingerprint: "fp",
            reason: "You asked to publish it.",
            expected_effect: "Goes live on Instagram.",
            explanation: 'Prepared "publish_scheduled_post".',
          },
        ],
      }),
    );
    render(<MarketingBrainPage />);
    await screen.findByTestId("brain-empty");
    fireEvent.change(screen.getByTestId("brain-input"), { target: { value: "Publish it" } });
    fireEvent.click(screen.getByTestId("brain-send"));
    const block = await screen.findByTestId("brain-approval");
    expect(block).toHaveTextContent(/AI proposed this/);
    expect(block).toHaveTextContent(/A human must approve it/);
    expect(block).toHaveTextContent(/Nothing has run/);
    expect(block.textContent?.toLowerCase()).not.toContain("executed");
    expect(block.textContent?.toLowerCase()).not.toContain("published successfully");
  });

  it("renders the insufficient-evidence state honestly", async () => {
    listConversations.mockResolvedValue({ items: [] });
    createConversation.mockResolvedValue({ id: "c1", title: "q", status: "active", created_at: "", updated_at: "" });
    sendMessage.mockResolvedValue(response({ evidence_status: "INSUFFICIENT_EVIDENCE", confidence: 0 }));
    render(<MarketingBrainPage />);
    await screen.findByTestId("brain-empty");
    fireEvent.change(screen.getByTestId("brain-input"), { target: { value: "Which channel is best?" } });
    fireEvent.click(screen.getByTestId("brain-send"));
    expect(await screen.findByTestId("brain-insufficient")).toBeInTheDocument();
  });

  it("surfaces an API error without crashing", async () => {
    listConversations.mockResolvedValue({ items: [] });
    createConversation.mockResolvedValue({ id: "c1", title: "q", status: "active", created_at: "", updated_at: "" });
    sendMessage.mockRejectedValue(new Error("Brain unavailable"));
    render(<MarketingBrainPage />);
    await screen.findByTestId("brain-empty");
    fireEvent.change(screen.getByTestId("brain-input"), { target: { value: "hi" } });
    fireEvent.click(screen.getByTestId("brain-send"));
    expect(await screen.findByTestId("brain-error")).toHaveTextContent(/Brain unavailable/);
  });

  it("clicking a suggestion asks the Brain", async () => {
    listConversations.mockResolvedValue({ items: [] });
    createConversation.mockResolvedValue({ id: "c1", title: "q", status: "active", created_at: "", updated_at: "" });
    sendMessage.mockResolvedValue(response());
    render(<MarketingBrainPage />);
    const suggestion = (await screen.findAllByTestId("brain-suggestion"))[0];
    fireEvent.click(suggestion);
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
  });
});
