"use client";

/**
 * A single opportunity card.
 *
 * Carries the FULL Constitution contract — Simple Mode shows:
 *   - Headline + impact chip
 *   - "What's happening" + "Why it matters"
 *   - The single recommended action (verb-led)
 *   - Expected result + confidence pill
 *   - "Generate this" deep-link button
 *
 * Professional Mode adds:
 *   - `reason` citation (always visible too — citation is the trust
 *     surface, not a "details" extra)
 *   - The `evidence` list (channels, asset names, lead-message hits)
 *
 * The Generate button routes to /content or /ads with URL params those
 * studios already honour for chip-deep-links — no backend round trip.
 */

import {
  Clock,
  DollarSign,
  Megaphone,
  PiggyBank,
  Sparkles,
  Target,
  UserCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import {
  QuickGenerateButton,
  quickGenerateFromOpportunity,
} from "@/components/quick-generate";
import { RecommendationTaskStatus } from "@/components/recommendation-task-status";
import { Button } from "@/components/ui/button";
import type {
  Opportunity,
  OpportunityGeneratorHint,
  OpportunityImpactCategory,
} from "@/lib/api";
import { useViewMode } from "@/lib/use-view-mode";
import { cn } from "@/lib/utils";

const IMPACT_META: Record<
  OpportunityImpactCategory,
  { icon: LucideIcon; label: string; accent: string }
> = {
  revenue: {
    icon: DollarSign,
    label: "Revenue",
    accent: "text-emerald-600 bg-emerald-500/10 border-emerald-500/30",
  },
  lead: {
    icon: Users,
    label: "Leads",
    accent: "text-sky-600 bg-sky-500/10 border-sky-500/30",
  },
  customer: {
    icon: UserCheck,
    label: "Customers",
    accent: "text-violet-600 bg-violet-500/10 border-violet-500/30",
  },
  time: {
    icon: Clock,
    label: "Time",
    accent: "text-amber-600 bg-amber-500/10 border-amber-500/30",
  },
  cost: {
    icon: PiggyBank,
    label: "Cost",
    accent: "text-rose-600 bg-rose-500/10 border-rose-500/30",
  },
};

function confidenceBand(confidence: number): { label: string; cls: string } {
  if (confidence >= 80)
    return {
      label: "High confidence",
      cls: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
    };
  if (confidence >= 60)
    return {
      label: "Medium confidence",
      cls: "bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/30",
    };
  if (confidence >= 40)
    return {
      label: "Low confidence",
      cls: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30",
    };
  return {
    label: "Speculative",
    cls: "bg-muted text-muted-foreground border-border",
  };
}

export function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const impact = IMPACT_META[opportunity.impact_category];
  const ImpactIcon = impact.icon;
  const band = confidenceBand(opportunity.confidence);
  const { isProfessional } = useViewMode();

  const KindIcon = opportunity.kind === "ad" ? Megaphone : Sparkles;

  const href = buildGeneratorHref(opportunity.generator);
  // Phase 8 — Quick Generate. Returns null for ad opps + for content
  // formats the backend doesn't accept; in either case we fall back
  // to the deep-link "Generate this" CTA the founder already knows.
  const quickGenContext = quickGenerateFromOpportunity(opportunity);

  return (
    <article
      data-testid={`opportunity-card-${opportunity.kind}`}
      className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5 shadow-sm"
    >
      {/* Top stripe — kind chip + impact chip */}
      <header className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            opportunity.kind === "ad"
              ? "bg-rose-500/10 text-rose-700 dark:text-rose-300"
              : "bg-primary/15 text-primary",
          )}
        >
          <KindIcon className="h-3 w-3" />
          {opportunity.kind === "ad" ? "Ad" : "Content"}
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
            impact.accent,
          )}
          data-testid="opportunity-impact-chip"
        >
          <ImpactIcon className="h-3 w-3" />
          {impact.label} impact
        </span>
      </header>

      {/* Headline */}
      <h3 className="text-lg font-semibold leading-snug tracking-tight">
        {opportunity.headline}
      </h3>

      {/* Body — Constitution 4 questions */}
      <div className="flex flex-col gap-3">
        <Block label="What's happening" testId="opportunity-what-is-happening">
          {opportunity.what_is_happening}
        </Block>

        <Block label="Why it matters" testId="opportunity-why-it-matters">
          {opportunity.why_it_matters}
        </Block>

        <Block
          label="Do this"
          testId="opportunity-recommended-action"
          accent
        >
          <span className="font-medium">{opportunity.recommended_action}</span>
        </Block>

        <Block label="What to expect" testId="opportunity-expected-result">
          {opportunity.expected_result}
        </Block>
      </div>

      {/* Confidence + reason + CTA */}
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
            band.cls,
          )}
          data-testid="opportunity-confidence"
        >
          {band.label} ({opportunity.confidence}%)
        </span>
        <span
          className="text-[11px] italic text-muted-foreground"
          data-testid="opportunity-reason"
        >
          {opportunity.reason}
        </span>
        {/* Phase 8 — Quick Generate is the new primary CTA when we can
            satisfy it. The deep-link to the studio stays as a
            secondary "customize first" escape hatch so power users
            (and existing tests for `opportunity-generate-link`)
            still have the same path they always did. */}
        <div className="ml-auto flex items-center gap-2">
          {quickGenContext && (
            <QuickGenerateButton
              context={quickGenContext}
              label="Generate now"
              data-testid="opportunity-quick-generate"
            />
          )}
          <Button
            asChild
            size="sm"
            variant={quickGenContext ? "ghost" : "default"}
          >
            <Link
              href={href as never}
              data-testid="opportunity-generate-link"
              prefetch={false}
            >
              <Target className="h-3.5 w-3.5" />
              {quickGenContext ? "Customize first" : "Generate this"}
            </Link>
          </Button>
        </div>
      </div>

      {/* Professional Mode — supporting evidence */}
      {isProfessional && opportunity.evidence.length > 0 && (
        <div
          className="rounded-md border bg-muted/20 px-3 py-2 text-xs"
          data-testid="opportunity-evidence"
        >
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Supporting evidence
          </div>
          <ul className="mt-1 space-y-1 text-muted-foreground">
            {opportunity.evidence.map((e, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/60" />
                <span>{e}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <RecommendationTaskStatus
        recommendationId={opportunity.id}
        status={opportunity.task_status}
      />
    </article>
  );
}

function Block({
  label,
  children,
  testId,
  accent,
}: {
  label: string;
  children: React.ReactNode;
  testId: string;
  accent?: boolean;
}) {
  return (
    <div data-testid={testId} className="flex flex-col gap-1">
      <h4
        className={cn(
          "text-[10px] font-semibold uppercase tracking-wide",
          accent ? "text-primary" : "text-muted-foreground",
        )}
      >
        {label}
      </h4>
      <p className="text-sm leading-snug">{children}</p>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Generator deep-link
// ---------------------------------------------------------------------

/**
 * Build a /content or /ads URL the existing studios will pre-fill from.
 *
 * Content studio (`app/(app)/content/_components/studio.tsx`) honours:
 *   ?type=<ContentType>&goal=<string>&platform=<string>
 *
 * Ads studio (`app/(app)/ads/_components/studio.tsx`) honours:
 *   ?ad_type=<AdType>&objective=<AdObjective>&goal=<string>
 *
 * Both already silently ignore params they don't recognise, so we can
 * pass all five and let each studio cherry-pick the relevant ones.
 *
 * Pre-fill is intentionally lossy — the founder still wants to see +
 * tweak the form before generating. We're just removing the
 * "which dropdown?" friction.
 */
export function buildGeneratorHref(
  generator: OpportunityGeneratorHint,
): string {
  const params = new URLSearchParams();
  if (generator.target === "content") {
    params.set("type", generator.format);
    if (generator.platform) params.set("platform", generator.platform);
    if (generator.goal) params.set("goal", generator.goal);
    return `/content?${params.toString()}`;
  }
  // target === 'ad'
  params.set("ad_type", generator.format);
  if (generator.objective) params.set("objective", generator.objective);
  if (generator.goal) params.set("goal", generator.goal);
  return `/ads?${params.toString()}`;
}
