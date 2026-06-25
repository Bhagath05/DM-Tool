"use client";

import { Eye } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import type { PublicLandingPage } from "@/lib/api";

import { LeadForm } from "./lead-form";

type Attribution = {
  source_asset_type: string;
  source_asset_id: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
};

export function LandingPageView({
  slug,
  page,
  attribution,
  isPreview,
}: {
  slug: string;
  page: PublicLandingPage;
  attribution: Attribution;
  isPreview: boolean;
}) {
  // Beacon a view event when the page mounts. Fire-and-forget — failures
  // don't affect rendering. Skip the beacon for preview traffic so the
  // owner's own internal checks don't inflate view_count.
  useEffect(() => {
    if (isPreview) return;
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${base}/api/v1/public/landing-pages/${slug}/view`, {
      method: "POST",
      keepalive: true,
    }).catch(() => {});
  }, [slug, isPreview]);

  const { content } = page;

  return (
    <div className="min-h-screen bg-background text-foreground">
      {isPreview && <PreviewBanner />}
      <main className="mx-auto max-w-3xl px-6 py-16 sm:py-24">
        <header className="space-y-4 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            {content.headline}
          </h1>
          {content.subheadline && (
            <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
              {content.subheadline}
            </p>
          )}
        </header>

        {content.benefits.length > 0 && (
          <section className="mt-12 grid gap-4 sm:grid-cols-2">
            {content.benefits.map((b, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-5"
              >
                <h3 className="text-sm font-semibold tracking-tight">
                  {b.title}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">{b.body}</p>
              </div>
            ))}
          </section>
        )}

        <section className="mt-12 rounded-xl border border-border bg-card p-6 sm:p-8">
          <LeadForm
            slug={slug}
            content={content}
            attribution={attribution}
            turnstileSiteKey={page.turnstile_site_key}
            redirectUrl={page.redirect_url}
            isPreview={isPreview}
          />
        </section>

        {content.social_proof.length > 0 && (
          <section className="mt-16 space-y-4">
            <h2 className="text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
              What people are saying
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {content.social_proof.map((s, i) => (
                <blockquote
                  key={i}
                  className="rounded-lg border border-border bg-card p-5"
                >
                  <p className="text-sm leading-relaxed">“{s.quote}”</p>
                  <footer className="mt-3 text-xs text-muted-foreground">
                    — <span className="font-medium text-foreground">{s.author}</span>
                    {s.role && <span> · {s.role}</span>}
                  </footer>
                </blockquote>
              ))}
            </div>
          </section>
        )}

        {content.faq.length > 0 && (
          <section className="mt-16 space-y-3">
            <h2 className="text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
              FAQ
            </h2>
            <div className="divide-y divide-border rounded-lg border border-border bg-card">
              {content.faq.map((f, i) => (
                <details key={i} className="group p-4">
                  <summary className="cursor-pointer list-none text-sm font-medium">
                    {f.q}
                  </summary>
                  <p className="mt-2 text-sm text-muted-foreground">{f.a}</p>
                </details>
              ))}
            </div>
          </section>
        )}

        {content.footer_text && (
          <footer className="mt-16 text-center text-xs text-muted-foreground">
            {content.footer_text}
          </footer>
        )}
      </main>
    </div>
  );
}

/**
 * Shown at the top of the public landing page when the viewer reached it
 * via a preview token (draft page). Tells the owner clearly: this is a
 * preview, form submissions won't work, here's how to publish.
 *
 * Hidden for normal published-traffic viewers.
 */
function PreviewBanner() {
  return (
    <div className="sticky top-0 z-50 flex flex-wrap items-center justify-center gap-3 border-b border-amber-400/40 bg-amber-50 px-4 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
      <Eye className="h-3.5 w-3.5" />
      <span className="font-medium">Preview mode</span>
      <span className="opacity-80">
        Only you can see this. Publish the page to start collecting real
        signups.
      </span>
      <Link
        href={"/landing-pages" as never}
        className="rounded-md border border-amber-400/60 bg-white px-2 py-0.5 font-medium hover:bg-amber-100 dark:bg-amber-950/60 dark:hover:bg-amber-900/60"
      >
        Manage pages
      </Link>
    </div>
  );
}
