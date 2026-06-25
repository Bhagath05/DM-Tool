"use client";

/**
 * Phase 10.3c — Content Gaps.
 *
 *   You're missing: Social proof content
 *   Competitors post: Case Studies · Testimonials · Product Demos
 *   You post:        Educational
 *   Priority: High · [ Generate Testimonial Carousel → ]
 *
 * No dedicated "content gap" backend endpoint exists. We derive gaps
 * by intersecting two existing sources:
 *
 *   1. `api.social.patterns()` → the format/concept patterns you HAVE
 *      already produced (your strengths). `WinningPattern.format_pattern`
 *      + `caption_pattern` give us your content shape.
 *
 *   2. `api.opportunities.center()` → opportunities the engine surfaced
 *      that suggest a NEW format. `OpportunityGeneratorHint.format`
 *      gives us suggested formats not yet in your repertoire.
 *
 * The "gap" is: `(formats the engine recommends) - (formats you've
 * already produced)`. Honest empty when the comparison is unavailable.
 */

import { ArrowRight, LayoutGrid, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export type GapPriority = "high" | "medium" | "low";

export interface ContentGap {
  id: string;
  missingFormat: string; // e.g. "Carousel"
  priority: GapPriority;
  yourPosts: string[]; // formats you've used
  recommendedPosts: string[]; // formats engine suggests
  ctaLabel: string;
  ctaHref: string;
}

type State =
  | { kind: "loading" }
  | { kind: "ready"; gaps: ContentGap[] };

const PRIORITY_TONE: Record<GapPriority, "good" | "watch" | "bad"> = {
  low: "good",
  medium: "watch",
  high: "bad",
};

const MAX_GAPS = 2;

export function ContentGaps({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const [patterns, opps] = await Promise.all([
        api.social.patterns().catch(() => []),
        api.opportunities.center().catch(() => null),
      ]);

      // Your formats — extract from pattern.format_pattern strings.
      const yourFormats = new Set<string>();
      for (const p of patterns ?? []) {
        const f = normalizeFormat(p.format_pattern);
        if (f) yourFormats.add(f);
      }

      // Recommended formats from opportunities.
      const recommendedFormats = new Map<string, { rec: string; id: string }>();
      if (opps) {
        const all = [
          ...(opps.content_opportunities ?? []),
          ...(opps.ad_opportunities ?? []),
        ];
        for (const o of all) {
          const f = normalizeFormat(o.generator?.format ?? null);
          if (!f) continue;
          if (!recommendedFormats.has(f)) {
            recommendedFormats.set(f, { rec: o.recommended_action, id: o.id });
          }
        }
      }

      // Gap = recommended - yours.
      const gaps: ContentGap[] = [];
      for (const [format, info] of recommendedFormats) {
        if (yourFormats.has(format)) continue;
        gaps.push({
          id: `gap-${info.id}`,
          missingFormat: format,
          priority: gaps.length === 0 ? "high" : "medium",
          yourPosts: Array.from(yourFormats).slice(0, 3),
          recommendedPosts: Array.from(recommendedFormats.keys()).slice(0, 3),
          ctaLabel: info.rec || `Generate ${format}`,
          ctaHref: `/create/social-posts?format=${encodeURIComponent(
            format.toLowerCase().replace(/\s+/g, "_"),
          )}&from=market-intel-gaps`,
        });
        if (gaps.length >= MAX_GAPS) break;
      }

      setState({ kind: "ready", gaps });
    } catch (err) {
      if (!(err instanceof ApiError)) console.warn(err);
      setState({ kind: "ready", gaps: [] });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="content-gaps"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <LayoutGrid className="h-3 w-3" />
            Content gaps
          </span>
        }
        heading="Formats you haven't tried yet"
        description="What your audience consumes that you aren't producing — ranked by potential impact."
      />

      {state.kind === "loading" && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "ready" && state.gaps.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title="No gaps detected"
          description="You've produced content across every format our engine surfaced. Keep going."
          data-testid="content-gaps-empty"
        />
      )}

      {state.kind === "ready" && state.gaps.length > 0 && (
        <ul className="flex flex-col gap-3" data-testid="content-gaps-list">
          {state.gaps.map((gap) => (
            <GapCard key={gap.id} gap={gap} />
          ))}
        </ul>
      )}
    </section>
  );
}

function GapCard({ gap }: { gap: ContentGap }) {
  return (
    <li>
      <article
        data-testid={`content-gap-${gap.id}`}
        className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4"
      >
        <header className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">
            You're missing: {gap.missingFormat}
          </h3>
          <StatusPill
            tone={PRIORITY_TONE[gap.priority]}
            size="sm"
            dot
            className="ml-auto"
          >
            {humanize(gap.priority)} priority
          </StatusPill>
        </header>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <span className="text-meta">Audience consumes</span>
            <ul className="flex flex-wrap gap-1.5">
              {gap.recommendedPosts.map((f, i) => (
                <li
                  key={i}
                  className="rounded-md bg-ai-soft px-2 py-0.5 text-[11px] text-ai-soft-foreground"
                >
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-meta">You've produced</span>
            <ul className="flex flex-wrap gap-1.5">
              {gap.yourPosts.length === 0 ? (
                <li className="text-[11px] italic text-muted-foreground">
                  None yet
                </li>
              ) : (
                gap.yourPosts.map((f, i) => (
                  <li
                    key={i}
                    className="rounded-md bg-muted px-2 py-0.5 text-[11px] text-foreground"
                  >
                    {f}
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>

        <Link
          href={gap.ctaHref as never}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
        >
          {gap.ctaLabel}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </article>
    </li>
  );
}

// ---------------------------------------------------------------------
//  Helpers (exported for testing)
// ---------------------------------------------------------------------

/**
 * Normalise a free-text format string into a comparable, founder-
 * friendly label. Returns null when the input has no recognisable
 * format token.
 */
export function normalizeFormat(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const lower = raw.toLowerCase();
  const map: { needle: string; label: string }[] = [
    { needle: "carousel", label: "Carousel" },
    { needle: "reel", label: "Reel" },
    { needle: "short_video", label: "Short Video" },
    { needle: "short video", label: "Short Video" },
    { needle: "blog", label: "Blog" },
    { needle: "testimonial", label: "Testimonial" },
    { needle: "case stud", label: "Case Study" },
    { needle: "demo", label: "Product Demo" },
    { needle: "social_post", label: "Social Post" },
    { needle: "social post", label: "Social Post" },
    { needle: "ad_copy", label: "Ad Copy" },
    { needle: "ad copy", label: "Ad Copy" },
    { needle: "video", label: "Video" },
    { needle: "image", label: "Image" },
  ];
  for (const m of map) {
    if (lower.includes(m.needle)) return m.label;
  }
  return null;
}

function humanize(p: GapPriority): string {
  return p[0].toUpperCase() + p.slice(1);
}
