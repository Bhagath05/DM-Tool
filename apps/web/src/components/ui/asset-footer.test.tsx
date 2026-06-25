/**
 * Phase 10.5 — AssetFooter tests.
 *
 * Pin three behaviours:
 *   1. Renders all four founder-rule fields when all are present
 *   2. Returns null when ANY required field is empty (Constitution gate)
 *   3. Confidence bar appears only when a confidence number is passed
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetFooter } from "./asset-footer";


function makeProps(over: Partial<React.ComponentProps<typeof AssetFooter>> = {}) {
  return {
    whyItWorks: "Trend momentum +42% with low competition.",
    expectedOutcome: "Reach 12k+, ~15 leads",
    bestTimeToPublish: "11:00 AM IST",
    estimatedEffort: "Quick win · 10 mins",
    ...over,
  };
}


describe("AssetFooter — happy path", () => {
  it("renders all four founder-rule fields", () => {
    render(<AssetFooter {...makeProps()} />);
    expect(screen.getByText(/Why this works/i)).toBeInTheDocument();
    expect(screen.getByText(/Trend momentum/i)).toBeInTheDocument();
    expect(screen.getByText(/Expected outcome/i)).toBeInTheDocument();
    expect(screen.getByText(/Reach 12k/i)).toBeInTheDocument();
    expect(screen.getByText(/Best time/i)).toBeInTheDocument();
    expect(screen.getByText(/11:00 AM IST/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated effort/i)).toBeInTheDocument();
    expect(screen.getByText(/Quick win/i)).toBeInTheDocument();
  });

  it("uses the default test-id when none provided", () => {
    render(<AssetFooter {...makeProps()} />);
    expect(screen.getByTestId("asset-footer")).toBeInTheDocument();
  });

  it("honours a custom test-id", () => {
    render(<AssetFooter {...makeProps()} data-testid="my-footer" />);
    expect(screen.getByTestId("my-footer")).toBeInTheDocument();
  });
});


describe("AssetFooter — Constitution gate", () => {
  it("returns null when whyItWorks is empty (suppresses incomplete card)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(<AssetFooter {...makeProps({ whyItWorks: "" })} />);
    expect(container).toBeEmptyDOMElement();
    warn.mockRestore();
  });

  it("returns null when expectedOutcome is whitespace-only", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(
      <AssetFooter {...makeProps({ expectedOutcome: "   " })} />,
    );
    expect(container).toBeEmptyDOMElement();
    warn.mockRestore();
  });

  it("returns null when bestTimeToPublish is empty", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(
      <AssetFooter {...makeProps({ bestTimeToPublish: "" })} />,
    );
    expect(container).toBeEmptyDOMElement();
    warn.mockRestore();
  });

  it("returns null when estimatedEffort is empty", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(
      <AssetFooter {...makeProps({ estimatedEffort: "" })} />,
    );
    expect(container).toBeEmptyDOMElement();
    warn.mockRestore();
  });

  it("logs a dev-mode console warning when suppressed (catches silent gaps)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<AssetFooter {...makeProps({ whyItWorks: "" })} />);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});


describe("AssetFooter — confidence bar", () => {
  it("does NOT render the confidence section when confidence is undefined", () => {
    // ConfidenceBar (when mounted) emits its own label/percentage, so
    // any /Confidence/ text in the document implies the bar mounted.
    render(<AssetFooter {...makeProps()} />);
    expect(screen.queryByText(/Confidence/i)).toBeNull();
  });

  it("mounts the confidence section when a number is provided", () => {
    // ConfidenceBar renders its own "Confidence" label + percentage,
    // so we get multiple matches when the bar IS present. Use
    // getAllBy* to assert at-least-one rather than exactly-one.
    render(<AssetFooter {...makeProps()} confidence={87} />);
    expect(screen.getAllByText(/Confidence/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/87\s*%/).length).toBeGreaterThan(0);
  });

  it("renders 0% confidence (edge case — 0 is a valid number)", () => {
    render(<AssetFooter {...makeProps()} confidence={0} />);
    expect(screen.getAllByText(/0\s*%/).length).toBeGreaterThan(0);
  });
});
