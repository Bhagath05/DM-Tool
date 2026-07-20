/**
 * Cookie-consent state (GDPR/ePrivacy).
 *
 * Essential cookies (auth/session) need no consent and always run. This
 * module tracks the user's choice for NON-ESSENTIAL categories (analytics)
 * so any future analytics integration must gate on `hasAnalyticsConsent()`
 * before loading. Privacy-preserving default: until the user actively
 * accepts, non-essential is treated as DECLINED.
 *
 * Pure + framework-free so it's unit-testable and callable from anywhere.
 */

export type ConsentChoice = "accepted" | "declined";

export interface ConsentState {
  /** Non-essential (analytics) categories. */
  analytics: ConsentChoice;
  /** ISO timestamp of the decision — proof-of-consent record. */
  decidedAt: string;
  /** Policy version this choice was made against; bump to re-prompt. */
  version: number;
}

export const CONSENT_STORAGE_KEY = "aicmo.cookie.consent.v1";
export const CONSENT_VERSION = 1;

export function readConsent(): ConsentState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CONSENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ConsentState>;
    if (
      (parsed.analytics === "accepted" || parsed.analytics === "declined") &&
      typeof parsed.version === "number"
    ) {
      return {
        analytics: parsed.analytics,
        decidedAt: parsed.decidedAt ?? "",
        version: parsed.version,
      };
    }
    return null;
  } catch {
    return null;
  }
}

export function writeConsent(analytics: ConsentChoice): ConsentState {
  const state: ConsentState = {
    analytics,
    decidedAt: new Date().toISOString(),
    version: CONSENT_VERSION,
  };
  try {
    window.localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable (private mode) — banner will simply re-show */
  }
  return state;
}

/** Whether the banner should be shown: no decision yet, or an outdated one. */
export function needsConsentDecision(state: ConsentState | null): boolean {
  return !state || state.version !== CONSENT_VERSION;
}

/** The gate every non-essential integration (analytics) must check. Defaults
 *  to false until the user actively accepts. */
export function hasAnalyticsConsent(state: ConsentState | null): boolean {
  return !!state && state.version === CONSENT_VERSION && state.analytics === "accepted";
}
