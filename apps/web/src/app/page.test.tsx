/**
 * Landing page (/) auth-routing contract.
 *
 * Production runs strict `clerk` mode: the public CTA routes to /sign-up
 * and /sign-in, and there is NO anonymous "Open dashboard" shortcut — an
 * unauthenticated visitor can never reach the dashboard from here. The
 * demo/hybrid dev modes keep the "Open dashboard" convenience.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

const ORIGINAL_ENV = { ...process.env };

beforeEach(() => {
  delete process.env.NEXT_PUBLIC_AUTH_MODE;
});

afterEach(() => {
  for (const k of Object.keys(process.env)) {
    if (k.startsWith("NEXT_PUBLIC_")) delete process.env[k];
  }
  Object.assign(process.env, ORIGINAL_ENV);
});

function hrefs() {
  return Array.from(document.querySelectorAll("a")).map((a) =>
    a.getAttribute("href"),
  );
}

describe("landing page — strict clerk mode (production)", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "clerk";
  });

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

describe("landing page — demo/hybrid dev modes", () => {
  it("keeps the Open dashboard shortcut in hybrid", () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
    render(<HomePage />);
    expect(
      screen.getByRole("link", { name: /open dashboard/i }),
    ).toHaveAttribute("href", "/dashboard");
    // Sign-in is still reachable.
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      "/sign-in",
    );
  });

  it("keeps the Open dashboard shortcut in demo (default)", () => {
    render(<HomePage />); // env unset → demo
    expect(hrefs()).toContain("/dashboard");
  });
});
