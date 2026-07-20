/**
 * Regression pin — the production CSP must allowlist Cloudflare Turnstile.
 *
 * Clerk's bot-protection CAPTCHA on <SignUp>/<SignIn> is Cloudflare Turnstile,
 * loaded from https://challenges.cloudflare.com. When the enforced production
 * CSP omitted it, the browser blocked the widget and every sign-up failed with
 * "The CAPTCHA failed to load." (production incident). This test fails the
 * build if the host is ever dropped from the directives that must contain it.
 *
 * We assert against the config source text because next.config.ts wraps
 * withSentryConfig() and can't be cleanly imported into vitest.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// vitest runs from the package root (apps/web), so the config sits alongside.
const source = readFileSync(join(process.cwd(), "next.config.ts"), "utf8");

/** The CSP directive line (e.g. `script-src ...`). Directives interpolate
 *  host variables (`${turnstileHost}`), so we check for the variable ref. */
function directive(name: string): string {
  const line = source.split("\n").find((l) => l.includes(`\`${name} `));
  if (!line) throw new Error(`CSP directive not found: ${name}`);
  return line;
}

describe("production CSP allows Cloudflare Turnstile (Clerk bot protection)", () => {
  it("defines the Turnstile host as challenges.cloudflare.com", () => {
    expect(source).toMatch(
      /const turnstileHost\s*=\s*["']https:\/\/challenges\.cloudflare\.com["']/,
    );
  });

  it("script-src interpolates the Turnstile host (widget JS)", () => {
    expect(directive("script-src")).toContain("${turnstileHost}");
  });

  it("frame-src interpolates the Turnstile host (challenge iframe)", () => {
    expect(directive("frame-src")).toContain("${turnstileHost}");
  });

  it("connect-src interpolates the Turnstile host (verification)", () => {
    expect(directive("connect-src")).toContain("${turnstileHost}");
  });

  it("still allows Clerk's own hosts (no regression)", () => {
    expect(directive("script-src")).toContain("${clerkHosts}");
    expect(directive("frame-src")).toContain("${clerkHosts}");
  });
});
