import { beforeEach, describe, expect, it } from "vitest";

import {
  CONSENT_VERSION,
  hasAnalyticsConsent,
  needsConsentDecision,
  readConsent,
  writeConsent,
} from "./cookie-consent";

describe("cookie-consent", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("no decision yet → needs decision, no analytics consent (privacy default)", () => {
    const state = readConsent();
    expect(state).toBeNull();
    expect(needsConsentDecision(state)).toBe(true);
    expect(hasAnalyticsConsent(state)).toBe(false);
  });

  it("accepting persists consent and stops prompting", () => {
    const state = writeConsent("accepted");
    expect(state.analytics).toBe("accepted");
    expect(state.version).toBe(CONSENT_VERSION);
    expect(state.decidedAt).not.toBe("");

    const read = readConsent();
    expect(read?.analytics).toBe("accepted");
    expect(needsConsentDecision(read)).toBe(false);
    expect(hasAnalyticsConsent(read)).toBe(true);
  });

  it("declining is remembered and blocks analytics", () => {
    writeConsent("declined");
    const read = readConsent();
    expect(read?.analytics).toBe("declined");
    expect(needsConsentDecision(read)).toBe(false);
    expect(hasAnalyticsConsent(read)).toBe(false); // essential-only
  });

  it("an outdated policy version re-prompts", () => {
    window.localStorage.setItem(
      "aicmo.cookie.consent.v1",
      JSON.stringify({ analytics: "accepted", decidedAt: "x", version: 0 }),
    );
    const read = readConsent();
    expect(needsConsentDecision(read)).toBe(true);
    expect(hasAnalyticsConsent(read)).toBe(false); // stale consent never counts
  });

  it("corrupt storage degrades to 'needs decision' without throwing", () => {
    window.localStorage.setItem("aicmo.cookie.consent.v1", "{not json");
    const read = readConsent();
    expect(read).toBeNull();
    expect(needsConsentDecision(read)).toBe(true);
  });
});
