"use client";

/**
 * Phase 10.3c — Opportunities Detected.
 *
 * Top-3 highest-confidence opportunities from the existing
 * `api.opportunities.center()` endpoint (Phase 6 backend, unchanged).
 *
 *   Opportunity Score 91 · "AI Payroll demand +38%"
 *   Expected: High · Format: Carousel · Reach: ~12k
 *   [ Create Content → ]
 *
 * Composition rules:
 *   - Sort by confidence DESC; tie-break by impact_category weight
 *     (revenue > customer > lead > cost > time).
 *   - Show max 3 — the rest live at /grow/opportunities.
 *   - Each card deep-links into the right studio via the existing
 *     `generator` hint with prefill URL params (matches the convention
 *     used by /grow/opportunities today).
 */

import { ArrowRight, Compass, Megaphone, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type Opportunity,
  type OpportunityCenterReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const IMPACT_WEIGHT: Record<string, number> = {
  revenue: 5,
  customer: 4,
  lead: 3,
  cost: 2,
  time: 1,
};

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | {
      kind: "ready";
      topThree: Opportunity[];
      report: OpportunityCenterReport;
    };

export interface OpportunitiesDetectedProps {
  /** Called once data has loaded so the parent can update its
   *  `signalsTracked` count. */
  onCountChange?: (n: number) => void;
  className?: string;
}

export function OpportunitiesDetected({
  onCountChange,
  className,
}: OpportunitiesDetectedProps) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report = await api.opportunities.center();
      const all = [
        ...(report.content_opportunities ?? []),
        ...(report.ad_opportunities ?? []),
      ];
      onCountChange?.(all.length);
      if (all.length === 0) {
        setState({ kind: "empty" });
        return;
      }
      const ranked = [...all].sort((a, b) => {
        if (b.confidence !== a.confidence) return b.confidence - a.confidence;
        return (
          (IMPACT_WEIGHT[b.impact_category] ?? 0) -
          (IMPACT_WEIGHT[a.impact_category] ?? 0)
        );
      });
      setState({ kind: "ready", topThree: ranked.slice(0, 3), report });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load opportunities. Refresh to retry.";
      setState({ kind: "error", message });
    }
  }, [onCountChange]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="opportunities-detected"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <div className="flex items-end justify-between">
        <SectionHeading
          eyebrow={
            <span className="inline-flex items-center gap-1.5">
              <Compass className="h-3 w-3" />
              Opportunities detected
            </span>
          }
          heading="Highest-confidence moves right now"
          description="The plays our engine surfaced from your data + your industry signals."
        />
        <Link
          href={"/grow/opportunities" as never}
          className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          data-testid="opportunities-detected-see-all"
        >
          See all →
        </Link>
      </div>

      {state.kind === "loading" && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          variant="ai"
          title="Opportunities unavailable"
          description={state.message}
          data-testid="opportunities-detected-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Compass}
          variant="ai"
          title="No opportunities surfaced yet"
          description="Once your business profile + ad / lead activity produce signal, the engine will start surfacing growth moves here."
          data-testid="opportunities-detected-empty"
        />
      )}

      {state.kind === "ready" && (
        <ul className="flex flex-col gap-3" data-testid="opportunities-detected-list">
          {state.topThree.map((opp) => (
            <OpportunityCard key={opp.id} opp={opp} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Card
// ---------------------------------------------------------------------

function OpportunityCard({ opp }: { opp: Opportunity }) {
  const isAd = opp.generator?.target === "ad";
  const Icon = isAd ? Megaphone : Sparkles;
  const ctaHref = generatorHref(opp);

  return (
    <li>
      <article
        data-testid={`opportunity-card-${opp.id}`}
        className={cn(
          "card-surface-ai relative overflow-hidden p-5",
          "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm",
        )}
      >
        <div className="flex flex-col gap-3">
          <header className="flex flex-wrap items-center gap-2">
            <StatusPill tone="ai" size="md" dot icon={Icon}>
              Opportunity Score {opp.confidence}
            </StatusPill>
            <StatusPill tone="neutral" size="md">
              {humanizeImpact(opp.impact_category)} impact
            </StatusPill>
            {opp.generator?.format && (
              <StatusPill tone="muted" size="md">
                {humanizeFormat(opp.generator.format)}
              </StatusPill>
            )}
            {opp.generator?.platform && (
              <StatusPill tone="muted" size="md">
                {humanizePlatform(opp.generator.platform)}
              </StatusPill>
            )}
          </header>

          <div className="flex flex-col gap-1.5">
            <h3 className="text-base font-semibold text-foreground">
              {opp.headline}
            </h3>
            <p className="text-sm text-muted-foreground">
              {opp.what_is_happening}
            </p>
          </div>

          <p className="text-sm font-medium text-foreground">
            <span className="text-muted-foreground">Do this: </span>
            {opp.recommended_action}
          </p>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Expected:</span>{" "}
            {opp.expected_result}
          </p>

          <div className="mt-1 flex items-center justify-between">
            <span className="text-meta">Why: {opp.reason}</span>
            <Link
              href={ctaHref as never}
              data-testid={`opportunity-cta-${opp.id}`}
              className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
            >
              {isAd ? "Create ad" : "Create content"}
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </article>
    </li>
  );
}

// ---------------------------------------------------------------------
//  Deep-link to studio with prefilled brief
// ---------------------------------------------------------------------

function generatorHref(opp: Opportunity): string {
  const g = opp.generator;
  if (!g) return "/grow/opportunities";

  const baseByTarget: Record<"content" | "ad", string> = {
    content: "/create/social-posts",
    ad: "/create/ads",
  };
  const base = baseByTarget[g.target];

  // Mirror the URL-prefill convention from Phase 3.3 action chips.
  // The studios pick these up via useSearchParams + the existing
  // prefill plumbing. Anything they don't recognise is ignored — safe.
  const qs = new URLSearchParams();
  if (g.format) qs.set("format", g.format);
  if (g.platform) qs.set("platform", g.platform);
  if (g.goal) qs.set("goal", g.goal);
  if (g.objective) qs.set("objective", g.objective);
  qs.set("from", "market-intel");
  qs.set("opportunity_id", opp.id);
  return `${base}?${qs}`;
}

// ---------------------------------------------------------------------
//  Humanizers (no jargon)
// ---------------------------------------------------------------------

function humanizeImpact(c: string): string {
  switch (c) {
    case "revenue": return "Revenue";
    case "customer": return "Customer";
    case "lead": return "Lead";
    case "cost": return "Cost";
    case "time": return "Time";
    default: return c;
  }
}

function humanizeFormat(f: string): string {
  return f
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

function humanizePlatform(p: string): string {
  if (p === "google_search") return "Google Search";
  return p[0]?.toUpperCase() + p.slice(1);
}
