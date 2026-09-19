/**
 * Landing page (/) auth-routing contract.
 *
 * First-party auth: every entry requires an account. The public CTA routes to
 * /sign-up and /sign-in, and there is NO anonymous "Open dashboard" shortcut.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

import HomePage from "./page";

function hrefs() {
  return Array.from(document.querySelectorAll("a")).map((a) =>
    a.getAttribute("href"),
  );
}

describe("landing page — first-party auth (no anonymous access)", () => {
  it("routes the public CTA to sign-up and sign-in", () => {
    render(<HomePage />);
    expect(screen.getByRole("link", { name: /get started/i })).toHaveAttribute(
      "href",
      "/sign-up",
    );
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/sign-in",
    );
  });

  it("NEVER exposes an anonymous dashboard link", () => {
    render(<HomePage />);
    expect(hrefs()).not.toContain("/dashboard");
    expect(screen.queryByRole("link", { name: /open dashboard/i })).toBeNull();
  });
});
