"use client";

/**
 * Phase 10.4 — AI Recommended Ads.
 *
 *   ┌────────────┐ ┌────────────┐ ┌────────────┐
 *   │ Meta Ad    │ │ Google Ad  │ │ LinkedIn Ad│
 *   │ Headline   │ │ Headline   │ │ Headline   │
 *   │ Primary    │ │ Primary    │ │ Primary    │
 *   │ Audience   │ │ Keywords   │ │ Audience   │
 *   │ Budget rec │ │ Budget rec │ │ Budget rec │
 *   │ CPL est    │ │ CPL est    │ │ CPL est    │
 *   │ [Create]   │ │ [Create]   │ │ [Create]   │
 *   └────────────┘ └────────────┘ └────────────┘
 *
 * Pulls from `api.opportunities.center().ad_opportunities`, picks one
 * per format (Meta · Google Search · LinkedIn). Empty slots render
 * "Awaiting signal" tiles so the 3-up grid stays stable.
 *
 * Generate CTA deep-links to /create/ads with prefill — same Phase-3.3
 * convention the studios already honour.
 */

import { ArrowRight, Megaphone, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { scoreOpportunity } from "@/lib/action-scoring";
import {
  api,
  ApiError,
  type Opportunity,
} from "@/lib/api";
import {
  adFormatLabel,
  topAdPerFormat,
  type AdFormat,
} from "@/lib/recommendation-engine";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; slots: ReturnType<typeof topAdPerFormat> };

export function RecommendedAds({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report = await api.opportunities.center();
      const slots = topAdPerFormat(report);
      setState({ kind: "ready", slots });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load recommended ads.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="recommended-ads"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Megaphone className="h-3 w-3" />
            AI recommended ads
          </span>
        }
        heading="Run these to acquire leads"
        description="One ranked ad per platform. Headline, copy, audience, and budget hint ready to launch."
      />

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Ads unavailable"
          description={state.message}
          data-testid="recommended-ads-error"
        />
      )}

      {state.kind === "ready" && (
        <div
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="recommended-ads-grid"
        >
          {state.slots.map((slot) => (
            <AdCard
              key={slot.format}
              format={slot.format}
              opportunity={slot.opportunity}
            />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Per-format card
// ---------------------------------------------------------------------

function AdCard({
  format,
  opportunity,
}: {
  format: AdFormat;
  opportunity: Opportunity | null;
}) {
  const label = adFormatLabel(format);

  if (!opportunity) {
    return (
      <article
        data-testid={`recommended-ad-${format}-empty`}
        className="flex h-full flex-col gap-2 rounded-2xl border border-dashed border-border bg-card/60 p-4"
      >
        <header className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">{label}</span>
          <StatusPill tone="muted" size="sm">Awaiting signal</StatusPill>
        </header>
        <p className="flex-1 text-xs text-muted-foreground">
          When the engine surfaces a {label} opportunity that beats your
          current performance, you'll see headline, audience hint, and
          budget recommendation here.
        </p>
      </article>
    );
  }

  const score = scoreOpportunity(opportunity);
  const href = generateAdHref(format, opportunity);
  const objective = opportunity.generator?.objective ?? null;

  return (
    <article
      data-testid={`recommended-ad-${format}`}
      className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm"
    >
      <header className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{label}</span>
        <StatusPill tone="ai" size="sm" dot>
          {score.confidence}%
        </StatusPill>
      </header>

      {/* Headline = backend opportunity headline */}
      <p className="text-sm font-medium text-foreground">
        {opportunity.headline}
      </p>

      {/* Primary text = recommended_action (the LLM's draft copy hint) */}
      {opportunity.recommended_action && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Primary: </span>
          {opportunity.recommended_action}
        </p>
      )}

      <ul className="mt-auto flex flex-col gap-1 text-xs text-muted-foreground">
        {objective && (
          <li className="inline-flex items-center gap-1.5">
            <Target className="h-3 w-3" />
            Goal: <span className="font-medium">{humaniseObjective(objective)}</span>
          </li>
        )}
        {/* Audience hint — pulled from why_it_matters which often
            contains the target descriptor. Honest fall-through. */}
        {opportunity.why_it_matters && (
          <li className="line-clamp-2">
            <span className="font-medium text-foreground">Audience: </span>
            {opportunity.why_it_matters}
          </li>
        )}
        {/* Expected CPL — best-effort from parsed expected_result. */}
        {score.expectedRevenue && (
          <li>Expected CPL: <span className="font-medium">{score.expectedRevenue}</span></li>
        )}
        <li>{score.timeRequired} to draft</li>
      </ul>

      <Link
        href={href as never}
        data-testid={`recommended-ad-${format}-cta`}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
      >
        Generate creative
        <ArrowRight className="h-3 w-3" />
      </Link>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function humaniseObjective(o: string): string {
  switch (o) {
    case "awareness": return "Awareness";
    case "traffic": return "Traffic";
    case "engagement": return "Engagement";
    case "leads": return "Lead generation";
    case "app_installs": return "App installs";
    case "conversions": return "Conversions";
    case "sales": return "Sales";
    default: return o;
  }
}

function generateAdHref(format: AdFormat, opp: Opportunity): string {
  const qs = new URLSearchParams();
  qs.set("ad_type", format);
  if (opp.generator?.objective) qs.set("objective", opp.generator.objective);
  if (opp.generator?.goal) qs.set("goal", opp.generator.goal);
  qs.set("topic", opp.headline);
  qs.set("from", "command-center-ads");
  qs.set("opportunity_id", opp.id);
  return `/create/ads?${qs}`;
}
