"use client";

/**
 * Cookie consent banner (GDPR/ePrivacy).
 *
 * Shows once until the user decides, then never again (choice persisted in
 * localStorage). Essential cookies run regardless; this banner governs only
 * non-essential (analytics) consent — the privacy-preserving default is
 * declined until "Accept" is clicked. Any future analytics integration must
 * gate on `hasAnalyticsConsent()` from `lib/cookie-consent`.
 *
 * Rendered globally from the root layout so it covers public + app pages.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  needsConsentDecision,
  readConsent,
  writeConsent,
} from "@/lib/cookie-consent";

export function CookieConsent() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    // Read on mount (client-only — SSR can't know localStorage).
    setShow(needsConsentDecision(readConsent()));
  }, []);

  if (!show) return null;

  const decide = (choice: "accepted" | "declined") => {
    writeConsent(choice);
    setShow(false);
  };

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      aria-live="polite"
      className="fixed inset-x-0 bottom-0 z-[100] border-t border-border bg-card/95 px-4 py-3 shadow-lg backdrop-blur"
      data-testid="cookie-consent"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-center">
        <p className="min-w-0 flex-1 text-sm text-muted-foreground">
          We use essential cookies to keep you signed in and run the app. We
          also want to use optional cookies to understand how the app is used —
          only if you say yes.{" "}
          <Link
            href={"/cookies" as never}
            className="font-medium text-foreground underline-offset-2 hover:underline"
          >
            Learn more
          </Link>
          .
        </p>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => decide("declined")}
            className="rounded-md border border-border px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Only essential
          </button>
          <button
            type="button"
            onClick={() => decide("accepted")}
            className="rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
            data-testid="cookie-accept"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  );
}
