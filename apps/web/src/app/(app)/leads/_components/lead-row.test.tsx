/**
 * Phase 5 — LeadRow priority badge tests.
 *
 * Pins:
 *   - Without a `priority`, the row renders as before (no rank badge,
 *     no "Why now" line).
 *   - With a `priority`, the rank pill + "Why now" line appear, and
 *     the row has a priority-keyed data-testid so the test suite can
 *     assert on focus vs hot vs warm visually.
 *   - The focus row gets the highlighted background class.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Lead, LeadPriorityItem } from "@/lib/api";
import { LeadRow } from "./lead-row";

const BASE_LEAD: Lead = {
  id: "lead-1",
  user_id: "u1",
  business_profile_id: "bp1",
  email: "alex@acme.com",
  name: "Alex Founder",
  phone: null,
  company: "Acme",
  message: null,
  extra_data: {},
  landing_page_id: null,
  source_asset_type: null,
  source_asset_id: null,
  utm_source: "instagram",
  utm_medium: null,
  utm_campaign: "june-launch",
  utm_term: null,
  utm_content: null,
  status: "new",
  tags: [],
  notes: null,
  referrer: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const FOCUS_PRIORITY: LeadPriorityItem = {
  lead_id: "lead-1",
  email: "alex@acme.com",
  name: "Alex Founder",
  company: "Acme",
  rank: 1,
  priority: "focus",
  why_now: "Marked hot, came in 6h ago via june-launch, left a phone number.",
  recommended_action: "Call within 4 hours.",
  expected_result: "Conversation within 24h, 1-in-3 chance of converting.",
  confidence: 85,
  reason: "Hot status + recent + phone.",
  impact_category: "revenue",
  estimated_value_band: "high",
  cta_label: "Call now",
};

describe("LeadRow without priority", () => {
  it("renders email + status without the rank badge", () => {
    render(<LeadRow lead={BASE_LEAD} onSelect={vi.fn()} />);
    expect(screen.getByText("alex@acme.com")).toBeInTheDocument();
    expect(screen.queryByTestId("lead-row-why-now")).not.toBeInTheDocument();
    expect(screen.getByTestId("lead-row")).toBeInTheDocument();
  });

  it("invokes onSelect when clicked", () => {
    const onSelect = vi.fn();
    render(<LeadRow lead={BASE_LEAD} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("alex@acme.com"));
    expect(onSelect).toHaveBeenCalledWith(BASE_LEAD);
  });
});

describe("LeadRow with priority", () => {
  it("renders the rank badge + 'Why now' line", () => {
    render(
      <LeadRow lead={BASE_LEAD} onSelect={vi.fn()} priority={FOCUS_PRIORITY} />,
    );
    expect(screen.getByTestId("lead-row-focus")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    const whyNow = screen.getByTestId("lead-row-why-now");
    expect(whyNow).toHaveTextContent(/why now/i);
    expect(whyNow).toHaveTextContent(/left a phone number/i);
  });

  it("focus row has the highlighted background", () => {
    render(
      <LeadRow lead={BASE_LEAD} onSelect={vi.fn()} priority={FOCUS_PRIORITY} />,
    );
    const row = screen.getByTestId("lead-row-focus");
    expect(row.className).toMatch(/bg-primary\/5/);
  });

  it("hot row uses its own testid", () => {
    render(
      <LeadRow
        lead={BASE_LEAD}
        onSelect={vi.fn()}
        priority={{ ...FOCUS_PRIORITY, priority: "hot", rank: 2 }}
      />,
    );
    expect(screen.getByTestId("lead-row-hot")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
  });
});
