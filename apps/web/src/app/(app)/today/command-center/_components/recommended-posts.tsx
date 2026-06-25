"use client";

/**
 * Phase 10.4 — AI Recommended Posts.
 *
 *   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
 *   │ Instagram│ │ LinkedIn │ │ Facebook │ │ Twitter/X│
 *   │ Hook ... │ │ Hook ... │ │ Hook ... │ │ Hook ... │
 *   │ Time ... │ │ Time ... │ │ Time ... │ │ Time ... │
 *   │ Reach ...│ │ Reach ...│ │ Reach ...│ │ Reach ...│
 *   │ [Generate]│ │ [Generate]│ │[Generate]│ │[Generate]│
 *   └──────────┘ └──────────┘ └──────────┘ └──────────┘
 *
 * One card per supported post platform. Each shows the top
 * opportunity for that platform from `api.opportunities.center()`
 * with action scoring + a Generate CTA that deep-links into
 * /create/social-posts with prefill params.
 *
 * Empty slots render an "Awaiting signal" tile so the grid stays
 * 4-up regardless of data availability.
 */

import { ArrowRight, Clock, Send, Sparkles } from "lucide-react";
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
  type OpportunityCenterReport,
  type WinningPattern,
} from "@/lib/api";
import { type CommandPlatform } from "@/lib/expected-reach";
import {
  formatWindow,
  planForDay,
  todayWeekday,
  type PlatformPostingPlan,
} from "@/lib/posting-time";
import {
  postPlatformLabel,
  topPostPerPlatform,
} from "@/lib/recommendation-engine";
import { cn } from "@/lib/utils";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      slots: ReturnType<typeof topPostPerPlatform>;
      plansByPlatform: Map<CommandPlatform, PlatformPostingPlan>;
    };

export function RecommendedPosts({ className }: { className?: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      // Pull opportunities + posting patterns in parallel — patterns
      // failing is non-fatal (we fall back to placeholder windows).
      const [report, patterns] = await Promise.all([
        api.opportunities.center().catch((err) => {
          if (!(err instanceof ApiError)) console.warn(err);
          return null as OpportunityCenterReport | null;
        }),
        api.social.patterns().catch(() => [] as WinningPattern[]),
      ]);

      const slots = topPostPerPlatform(report);
      const plans = planForDay(patterns, todayWeekday());
      const plansByPlatform = new Map<CommandPlatform, PlatformPostingPlan>();
      for (const plan of plans) {
        // Only post platforms (not tiktok/youtube) feature here.
        if (
          plan.platform === "instagram" ||
          plan.platform === "linkedin" ||
          plan.platform === "facebook" ||
          plan.platform === "twitter"
        ) {
          plansByPlatform.set(plan.platform, plan);
        }
      }
      setState({ kind: "ready", slots, plansByPlatform });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Couldn't load recommended posts.";
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section
      data-testid="recommended-posts"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Send className="h-3 w-3" />
            AI recommended posts
          </span>
        }
        heading="Publish these this week"
        description="One ranked post per platform. Time, reach, and hook already drafted."
      />

      {state.kind === "loading" && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-2xl" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <EmptyState
          icon={Sparkles}
          title="Posts unavailable"
          description={state.message}
          data-testid="recommended-posts-error"
        />
      )}

      {state.kind === "ready" && (
        <div
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
          data-testid="recommended-posts-grid"
        >
          {state.slots.map((slot) => (
            <PostCard
              key={slot.platform}
              platform={slot.platform}
              opportunity={slot.opportunity}
              plan={state.plansByPlatform.get(slot.platform) ?? null}
            />
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Per-platform card
// ---------------------------------------------------------------------

function PostCard({
  platform,
  opportunity,
  plan,
}: {
  platform: CommandPlatform;
  opportunity: Opportunity | null;
  plan: PlatformPostingPlan | null;
}) {
  const label = postPlatformLabel(platform);
  const bestWindow = plan && plan.windows.length > 0 ? plan.windows[0] : null;

  if (!opportunity) {
    return (
      <article
        data-testid={`recommended-post-${platform}-empty`}
        className="flex h-full flex-col gap-2 rounded-2xl border border-dashed border-border bg-card/60 p-4"
      >
        <header className="flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">{label}</span>
          <StatusPill tone="muted" size="sm">Awaiting signal</StatusPill>
        </header>
        <p className="flex-1 text-xs text-muted-foreground">
          Once your engine has signal for {label}, a ranked post will appear
          here with a draft hook and best time to publish.
        </p>
        {bestWindow && (
          <p className="text-xs text-muted-foreground">
            Industry-norm window today: <span className="tabular-nums">{formatWindow(bestWindow)}</span>
          </p>
        )}
      </article>
    );
  }

  const score = scoreOpportunity(opportunity);
  const href = generateHref(platform, opportunity);

  return (
    <article
      data-testid={`recommended-post-${platform}`}
      className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-ai-border hover:shadow-sm"
    >
      <header className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{label}</span>
        <StatusPill tone="ai" size="sm" dot>
          {score.confidence}%
        </StatusPill>
      </header>

      <p className="text-sm font-medium text-foreground">
        {opportunity.headline}
      </p>

      {opportunity.recommended_action && (
        <p className="text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Hook: </span>
          {opportunity.recommended_action}
        </p>
      )}

      <ul className="mt-auto flex flex-col gap-1 text-xs text-muted-foreground">
        {bestWindow && (
          <li className="inline-flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            Best time: <span className="tabular-nums">{formatWindow(bestWindow)}</span>
          </li>
        )}
        {score.expectedReach.band !== "unknown" && (
          <li>Reach: <span className="font-medium">{score.expectedReach.display}</span></li>
        )}
        {score.expectedLeads && (
          <li>Leads: <span className="font-medium">{score.expectedLeads}</span></li>
        )}
      </ul>

      <Link
        href={href as never}
        data-testid={`recommended-post-${platform}-cta`}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
      >
        Generate
        <ArrowRight className="h-3 w-3" />
      </Link>
    </article>
  );
}

// ---------------------------------------------------------------------
//  Deep-link to studio with prefill (Phase 3.3 convention)
// ---------------------------------------------------------------------

function generateHref(platform: CommandPlatform, opp: Opportunity): string {
  const qs = new URLSearchParams();
  qs.set("platform", platform);
  if (opp.generator?.format) qs.set("format", opp.generator.format);
  if (opp.generator?.goal) qs.set("goal", opp.generator.goal);
  qs.set("topic", opp.headline);
  qs.set("from", "command-center-posts");
  qs.set("opportunity_id", opp.id);
  return `/create/social-posts?${qs}`;
}
