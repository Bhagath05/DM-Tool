/**
 * Phase 10.0 — StatusPill smoke tests.
 *
 * Three things matter:
 *   - All 6 tones render with the right `data-tone` attribute.
 *   - The dot variant adds an aria-hidden marker.
 *   - Icon prop renders the icon component.
 */

import { render, screen } from "@testing-library/react";
import { CheckCircle2 } from "lucide-react";
import { describe, expect, it } from "vitest";

import { StatusPill, type PillTone } from "@/components/ui/status-pill";

describe("StatusPill", () => {
  it.each<PillTone>(["good", "watch", "bad", "ai", "neutral", "muted"])(
    "renders tone=%s",
    (tone) => {
      render(<StatusPill tone={tone}>label</StatusPill>);
      const el = screen.getByTestId("status-pill");
      expect(el).toHaveAttribute("data-tone", tone);
    },
  );

  it("renders a dot when dot=true", () => {
    const { container } = render(
      <StatusPill tone="good" dot>
        live
      </StatusPill>,
    );
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });

  it("renders an icon when provided", () => {
    const { container } = render(
      <StatusPill tone="ai" icon={CheckCircle2}>
        ai
      </StatusPill>,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });
});
