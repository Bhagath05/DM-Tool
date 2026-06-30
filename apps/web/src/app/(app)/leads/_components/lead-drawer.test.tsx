/**
 * LeadDrawer — tag editing (the CRM capability the backend supported via
 * LeadUpdate.tags but the UI never exposed). Pins: empty state, add tag
 * persists via api.leads.update, remove tag persists the filtered list.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Lead } from "@/lib/api";

const updateMock = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      leads: {
        ...actual.api.leads,
        update: (id: string, payload: unknown) => updateMock(id, payload),
      },
    },
  };
});

import { LeadDrawer } from "./lead-drawer";

function makeLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: "lead-1",
    user_id: "u1",
    business_profile_id: "bp1",
    email: "jane@example.com",
    name: "Jane",
    phone: null,
    company: null,
    message: null,
    extra_data: {},
    landing_page_id: null,
    source_asset_type: null,
    source_asset_id: null,
    utm_source: null,
    utm_medium: null,
    utm_campaign: null,
    utm_term: null,
    utm_content: null,
    status: "new",
    tags: [],
    notes: null,
    referrer: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function renderDrawer(lead: Lead) {
  const onUpdated = vi.fn();
  render(
    <LeadDrawer
      lead={lead}
      onClose={vi.fn()}
      onUpdated={onUpdated}
      onDeleted={vi.fn()}
    />,
  );
  return { onUpdated };
}

describe("LeadDrawer — tags", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMock.mockImplementation((_id, payload) =>
      Promise.resolve(makeLead({ tags: (payload as { tags?: string[] }).tags ?? [] })),
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows an empty state when the lead has no tags", () => {
    renderDrawer(makeLead({ tags: [] }));
    expect(screen.getByTestId("lead-tags-empty")).toBeInTheDocument();
  });

  it("adds a tag (lowercased) and persists via api.leads.update", async () => {
    const user = userEvent.setup();
    const { onUpdated } = renderDrawer(makeLead({ tags: [] }));

    await user.type(screen.getByLabelText("Tags"), "VIP");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledWith("lead-1", { tags: ["vip"] }),
    );
    expect(onUpdated).toHaveBeenCalled();
    expect(screen.getByTestId("lead-tags")).toHaveTextContent("vip");
  });

  it("removes a tag and persists the filtered list", async () => {
    const user = userEvent.setup();
    renderDrawer(makeLead({ tags: ["vip", "follow-up"] }));

    await user.click(
      screen.getByRole("button", { name: /remove tag vip/i }),
    );

    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledWith("lead-1", {
        tags: ["follow-up"],
      }),
    );
  });

  it("does not add a duplicate tag", async () => {
    const user = userEvent.setup();
    renderDrawer(makeLead({ tags: ["vip"] }));

    await user.type(screen.getByLabelText("Tags"), "vip");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    expect(updateMock).not.toHaveBeenCalled();
  });
});
