/**
 * Phase 10.0 — EmptyState rendering tests.
 *
 * Pin two contracts:
 *   - title + description always present.
 *   - When the AI variant is used, the icon container picks up the
 *     AI accent. We assert via `data-testid` for the AI variant.
 */

import { render, screen } from "@testing-library/react";
import { Sparkles } from "lucide-react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/ui/empty-state";

describe("EmptyState", () => {
  it("renders title + description + hint + action", () => {
    render(
      <EmptyState
        icon={Sparkles}
        title="Coming soon"
        description="More work to do here."
        hint="Why this threshold?"
        action={<button type="button">Do it</button>}
      />,
    );
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByText("More work to do here.")).toBeInTheDocument();
    expect(screen.getByText("Why this threshold?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Do it" })).toBeInTheDocument();
  });

  it("honours data-testid override", () => {
    render(
      <EmptyState
        data-testid="custom-empty"
        icon={Sparkles}
        title="x"
        description="y"
      />,
    );
    expect(screen.getByTestId("custom-empty")).toBeInTheDocument();
  });

  it("applies the ai variant when requested", () => {
    render(
      <EmptyState
        variant="ai"
        icon={Sparkles}
        title="x"
        description="y"
        data-testid="ai-empty"
      />,
    );
    const el = screen.getByTestId("ai-empty");
    expect(el.className).toMatch(/bg-ai-soft/);
  });
});
