/**
 * Phase 6.6 — page frame primitives: one max-width, one header shape, and
 * an accessible ErrorState.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ErrorState,
  PageHeader,
  PageShell,
} from "./page-shell";

describe("PageShell", () => {
  it("forwards data-testid and applies the default max-width", () => {
    render(<PageShell data-testid="shell">body</PageShell>);
    const el = screen.getByTestId("shell");
    expect(el).toHaveClass("max-w-6xl");
    expect(el).toHaveClass("mx-auto");
  });

  it("honours the width prop", () => {
    render(
      <PageShell data-testid="shell" width="wide">
        body
      </PageShell>,
    );
    expect(screen.getByTestId("shell")).toHaveClass("max-w-7xl");
  });
});

describe("PageHeader", () => {
  it("renders exactly one <h1> plus optional eyebrow, nav and actions", () => {
    render(
      <PageHeader
        eyebrow="Measure"
        title="How your business is growing"
        description="Plain-language signals."
        nav={<div data-testid="tabs">tabs</div>}
        actions={<button type="button">Upload</button>}
      />,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: /how your business is growing/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Measure")).toBeInTheDocument();
    expect(screen.getByText("Plain-language signals.")).toBeInTheDocument();
    expect(screen.getByTestId("tabs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("is announced as an alert and carries a heading + copy, not color alone", () => {
    render(<ErrorState title="Couldn't load" description="Try again." />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Couldn't load");
    expect(alert).toHaveTextContent("Try again.");
  });
});
