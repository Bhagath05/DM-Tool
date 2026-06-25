"use client";

import { Check, Loader2 } from "lucide-react";
import Script from "next/script";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { LandingPageContent } from "@/lib/api";

declare global {
  interface Window {
    turnstile?: {
      reset: (id?: string) => void;
      getResponse: (id?: string) => string;
    };
  }
}

type Attribution = {
  source_asset_type: string;
  source_asset_id: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
};

const CANONICAL_FIELDS = new Set([
  "email",
  "name",
  "phone",
  "company",
  "message",
]);

/**
 * Translate the backend's capture-endpoint errors into copy a real visitor
 * (not a developer) can act on. The default branch keeps the detail so we
 * never silently swallow a useful provider message.
 */
function friendlyCaptureError(status: number, detail?: string): string {
  const d = (detail ?? "").toLowerCase();
  if (status === 404 || d.includes("not found")) {
    return "This page isn't accepting signups right now. The owner may have unpublished it — please try again later.";
  }
  if (status === 422 || d.includes("validation")) {
    return "Some of the details didn't look right — please double-check the fields and try again.";
  }
  if (status === 429 || d.includes("rate")) {
    return "Too many submissions in a short time. Please wait a minute and try again.";
  }
  if (d.includes("turnstile") || d.includes("captcha")) {
    return "We couldn't verify the security check. Refresh the page and try again.";
  }
  return detail ?? `Couldn't send your details (${status}). Please try again.`;
}

export function LeadForm({
  slug,
  content,
  attribution,
  turnstileSiteKey,
  redirectUrl,
  isPreview,
}: {
  slug: string;
  content: LandingPageContent;
  attribution: Attribution;
  turnstileSiteKey: string | null;
  redirectUrl: string | null;
  isPreview: boolean;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    // Don't even hit the backend in preview mode — the public capture
    // endpoint only accepts published pages and would 404. Show a clear
    // explanation instead of the misleading "Page not found".
    if (isPreview) {
      setError(
        "This page isn't published yet, so signups can't be saved. Publish it from the Lead pages screen to start collecting leads.",
      );
      return;
    }
    setError(null);
    setSubmitting(true);

    const formData = new FormData(e.currentTarget);
    const canonical: Record<string, string> = {};
    const extra_data: Record<string, string> = {};

    for (const [key, raw] of formData.entries()) {
      if (typeof raw !== "string") continue;
      const value = raw.trim();
      if (!value) continue;
      if (CANONICAL_FIELDS.has(key)) {
        canonical[key] = value;
      } else if (key !== "cf-turnstile-response") {
        extra_data[key] = value;
      }
    }

    const turnstile_token = turnstileSiteKey
      ? (window.turnstile?.getResponse() ??
        (formData.get("cf-turnstile-response") as string | null) ??
        null)
      : null;

    const payload = {
      ...canonical,
      extra_data,
      ...attribution,
      turnstile_token,
      referrer: typeof document !== "undefined" ? document.referrer : null,
    };

    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(
        `${base}/api/v1/public/leads/capture/${slug}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = (body as { detail?: string }).detail;
        throw new Error(friendlyCaptureError(res.status, detail));
      }
      const data = (await res.json()) as { redirect_url?: string };
      const target = data.redirect_url ?? redirectUrl;
      if (target) {
        window.location.href = target;
        return;
      }
      setDone(true);
      formRef.current?.reset();
      if (turnstileSiteKey && window.turnstile) {
        window.turnstile.reset();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-border bg-card p-4">
        <Check className="mt-0.5 h-5 w-5 text-green-600" />
        <div>
          <div className="font-medium">Thanks — we'll be in touch.</div>
          <p className="text-sm text-muted-foreground">
            Your submission was received.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      {turnstileSiteKey && (
        <Script
          src="https://challenges.cloudflare.com/turnstile/v0/api.js"
          strategy="afterInteractive"
          async
        />
      )}
      <form ref={formRef} onSubmit={onSubmit} className="space-y-4">
        {content.form_fields.map((field) => (
          <div key={field.name} className="space-y-1.5">
            <Label htmlFor={field.name}>
              {field.label}
              {field.required && (
                <span className="ml-0.5 text-destructive">*</span>
              )}
            </Label>
            {field.type === "textarea" ? (
              <Textarea
                id={field.name}
                name={field.name}
                required={field.required}
                placeholder={field.placeholder ?? undefined}
                rows={4}
              />
            ) : (
              <Input
                id={field.name}
                name={field.name}
                type={field.type}
                required={field.required}
                placeholder={field.placeholder ?? undefined}
                autoComplete={
                  field.type === "email"
                    ? "email"
                    : field.name === "name"
                      ? "name"
                      : field.name === "phone"
                        ? "tel"
                        : undefined
                }
              />
            )}
          </div>
        ))}

        {turnstileSiteKey && (
          <div
            className="cf-turnstile"
            data-sitekey={turnstileSiteKey}
            data-theme="auto"
          />
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button
          type="submit"
          disabled={submitting}
          className="w-full"
          size="lg"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            content.cta_text
          )}
        </Button>

        {content.privacy_blurb && (
          <p className="text-center text-xs text-muted-foreground">
            {content.privacy_blurb}
          </p>
        )}
      </form>
    </>
  );
}
