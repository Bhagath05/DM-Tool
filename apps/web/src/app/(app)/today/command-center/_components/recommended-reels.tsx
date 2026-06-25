"use client";

/**
 * Phase 10.4 — AI Recommended Reels.
 *
 *   ┌──────────────────────────┐ ┌──────────────────────────┐
 *   │ "5 Payroll Mistakes..."  │ │ "Why Founders Underpay..."│
 *   │ Hook: ...                │ │ Hook: ...                │
 *   │ Scenes: ...              │ │ Scenes: ...              │
 *   │ CTA: ...                 │ │ CTA: ...                 │
 *   │ Best time · Reach        │ │ Best time · Reach        │
 *   │ [Create Reel]            │ │ [Create Reel]            │
 *   └──────────────────────────┘ └──────────────────────────┘
 *
 * Pulls reel-formatted opportunities from `api.opportunities.center()`
 * (both content + ad arrays). Up to 2 cards. Scene breakdown is
 * synthesised from `recommended_action` + `why_it_matters` since the
 * backend doesn't ship a structured scenes array yet — honest fall-
 * through to the generic action line when synthesis isn't possible.
 */

import { ArrowRight, Film, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { scoreOpportunity } from "@/lib/action-scoring";
import { api, ApiError, type Opportunity } from "@/lib/api";
import { topReels } from "@/lib/recommendation-engine";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; reels: Opportunity[] };

export function RecommendedReels({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const report = await api.opportunities.center();
      const reels = topReels(report, 2);
      if (reels.length === 0) {
        setState({ kind: "empty" });
        return;
      }
      setState({ kind: "ready", reels });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load recommended reels.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="recommended-reels"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Film className="h-3 w-3" />
            AI recommended reels
          </span>
        }
        heading="Short-form video ideas that should land"
        description="Each comes with a hook, scene beats, and a CTA so you can shoot it without a script doc."
      />

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Reels unavailable"
          description={state.message}
          data-testid="recommended-reels-error"
        />
      )}

      {state.kind === "empty" && (
        <EmptyState
          icon={Film}
          title="No reel ideas yet"
          description="When the engine spots a short-form opportunity that should outperform your current content, it'll appear here with a full scene breakdown."
          data-testid="recommended-reels-empty"
        />
      )}

      {state.kind === "ready" && (
        <div
          className="grid grid-cols-1 gap-3 lg:grid-cols-2"
          data-testid="recommended-reels-grid"
        >
          {state.reels.map((reel) => (
            <ReelCard key={reel.id} reel={reel} />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Reel card
// ---------------------------------------------------------------------

function ReelCard({ reel }: { reel: Opportunity }) {
  const score = scoreOpportunity(reel);
  const scenes = synthesizeScenes(reel);
  const href = generateReelHref(reel);

  return (
    <article
      data-testid={`recommended-reel-${reel.id}`}
      className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm"
    >
      <header className="flex flex-wrap items-center gap-2">
        <StatusPill tone="ai" size="sm" dot icon={Film}>
          Reel
        </StatusPill>
        <StatusPill tone="muted" size="sm">
          {score.confidence}% confidence
        </StatusPill>
        <span className="ml-auto text-xs text-muted-foreground">
          {score.timeRequired}
        </span>
      </header>

      <h3 className="text-sm font-semibold text-foreground">{reel.headline}</h3>

      {reel.recommended_action && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Hook: </span>
          {reel.recommended_action}
        </p>
      )}

      {scenes.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-meta">Scenes</span>
          <ol className="ml-4 list-decimal space-y-0.5 text-xs text-muted-foreground">
            {scenes.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      <ul className="mt-auto flex flex-col gap-1 text-xs text-muted-foreground">
        {score.expectedReach.band !== "unknown" && (
          <li>Expected reach: <span className="font-medium">{score.expectedReach.display}</span></li>
        )}
        {score.expectedLeads && (
          <li>Likely leads: <span className="font-medium">{score.expectedLeads}</span></li>
        )}
      </ul>

      <Link
        href={href as never}
        data-testid={`recommended-reel-${reel.id}-cta`}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
      >
        Create reel
        <ArrowRight className="h-3 w-3" />
      </Link>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Scene synthesis — derived, honest
// ---------------------------------------------------------------------

/**
 * Heuristic scene breakdown for a reel. We don't have a structured
 * `scenes[]` field on Opportunity yet, so we build 3 beats from the
 * available text:
 *
 *   1. Hook   — derived from headline or first sentence of why_it_matters
 *   2. Body   — what_is_happening (the substance)
 *   3. CTA    — recommended_action paraphrased as a call
 *
 * If a beat can't be honestly synthesised it's dropped — better
 * 2 scenes than 3 with one fake.
 */
function synthesizeScenes(reel: Opportunity): string[] {
  const out: string[] = [];
  if (reel.headline) out.push(`Open with: "${reel.headline}"`);
  if (reel.what_is_happening) out.push(reel.what_is_happening);
  if (reel.recommended_action) {
    out.push(`End with CTA: ${reel.recommended_action}`);
  }
  return out;
}

function generateReelHref(reel: Opportunity): string {
  const qs = new URLSearchParams();
  qs.set("content_type", "reel");
  if (reel.generator?.platform) qs.set("platform", reel.generator.platform);
  if (reel.generator?.goal) qs.set("goal", reel.generator.goal);
  qs.set("topic", reel.headline);
  qs.set("from", "command-center-reels");
  qs.set("opportunity_id", reel.id);
  return `/create/social-posts?${qs}`;
}
