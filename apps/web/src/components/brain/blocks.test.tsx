/**
 * Generative-UI primitives — rendering + accessibility + safety pins.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ApprovalRequestBlock,
  DataTable,
  InsufficientEvidenceBlock,
  MetricCard,
  RecommendationBlock,
} from "./blocks";

describe("brain primitives", () => {
  it("ApprovalRequestBlock makes the proposed-vs-approve distinction and never implies execution", () => {
    render(
      <ApprovalRequestBlock
        tool="publish_scheduled_post"
        explanation='Prepared "publish_scheduled_post".'
        reason="You asked."
        expectedEffect="Goes live."
        status="pending"
      />,
    );
    const block = screen.getByTestId("brain-approval");
    expect(block).toHaveTextContent(/AI proposed this/);
    expect(block).toHaveTextContent(/A human must approve it/);
    expect(block).toHaveTextContent(/Nothing has run/);
    // links to the approval surface rather than executing
    const link = screen.getByRole("link", { name: /review/i });
    expect(link).toHaveAttribute("href", "/ai/approvals");
  });

  it("InsufficientEvidenceBlock refuses to guess", () => {
    render(<InsufficientEvidenceBlock detail="Only 3 days of data." />);
    expect(screen.getByTestId("brain-insufficient")).toHaveTextContent(/won't guess/i);
    expect(screen.getByText(/Only 3 days of data/)).toBeInTheDocument();
  });

  it("MetricCard conveys trend with text, not color alone", () => {
    render(<MetricCard label="CTR" value="3.2%" delta="23%" trend="down" goodWhen="up" />);
    // an accessible, non-color trend label is present
    expect(screen.getByText("down")).toBeInTheDocument();
    expect(screen.getByText("CTR")).toBeInTheDocument();
    expect(screen.getByText("3.2%")).toBeInTheDocument();
  });

  it("RecommendationBlock renders a next step and optional action link", () => {
    render(
      <RecommendationBlock
        recommendation="Run a creative experiment"
        reason="Creative fatigue is likely."
        expectedResult="+10 to +20 leads"
        confidence={78}
        action={{ label: "Review experiment", href: "/campaigns" }}
      />,
    );
    expect(screen.getByTestId("brain-recommendation")).toHaveTextContent("Run a creative experiment");
    expect(screen.getByRole("link", { name: /Review experiment/ })).toHaveAttribute("href", "/campaigns");
  });

  it("DataTable renders columns and rows", () => {
    render(<DataTable columns={["Channel", "Leads"]} rows={[["Instagram", 42]]} />);
    const table = screen.getByTestId("brain-table");
    expect(table).toHaveTextContent("Channel");
    expect(table).toHaveTextContent("Instagram");
    expect(table).toHaveTextContent("42");
  });
});
