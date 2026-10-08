/**
 * Phase 6.6 — ThemeToggle: a 3-way radiogroup that writes the choice to
 * <html data-theme> and marks the active option accessibly (aria-checked +
 * aria-label, never icon-only without a name).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "./theme-toggle";
import { __resetThemeForTests } from "@/lib/theme";

beforeEach(() => __resetThemeForTests());
afterEach(() => __resetThemeForTests());

describe("ThemeToggle", () => {
  it("exposes System / Light / Dark as named radios", () => {
    render(<ThemeToggle />);
    const group = screen.getByRole("radiogroup", { name: /color theme/i });
    expect(group).toBeInTheDocument();
    for (const name of ["System", "Light", "Dark"]) {
      expect(screen.getByRole("radio", { name })).toBeInTheDocument();
    }
  });

  it("defaults to System checked", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("radio", { name: "System" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("applies the chosen theme to <html> and moves aria-current", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "System" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});
