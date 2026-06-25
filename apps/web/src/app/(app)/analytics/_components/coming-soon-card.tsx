"use client";

/**
 * Honest empty-state card for outcome sections we don't have data for
 * yet (Revenue Impact, Customer Growth, Time Savings, Cost Optimisation).
 *
 * Per the Constitution: "Ship questions, not numbers." We surface what
 * the user would need to do to unlock the section, instead of fabricating
 * a metric. This keeps the dashboard honest while signposting where the
 * product is headed.
 *
 * Same outer shape as <BusinessMetric> so they sit cleanly alongside
 * each other in the same grid.
 */

import { type LucideIcon } from "lucide-react";

import type { ImpactCategory } from "@/components/ui/business-metric";
import { cn } from "@/lib/utils";

import {
  Clock,
  DollarSign,
  PiggyBank,
  UserCheck,
  Users,
} from "lucide-react";

const IMPACT_META: Record<
  ImpactCategory,
  { icon: LucideIcon; label: string; accent: string }
> = {
  revenue: {
    icon: DollarSign,
    label: "Revenue",
    accent: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
  },
  lead: {
    icon: Users,
    label: "Leads",
    accent: "text-sky-500 bg-sky-500/10 border-sky-500/30",
  },
  customer: {
    icon: UserCheck,
    label: "Customers",
    accent: "text-violet-500 bg-violet-500/10 border-violet-500/30",
  },
  time: {
    icon: Clock,
    label: "Time",
    accent: "text-amber-500 bg-amber-500/10 border-amber-500/30",
  },
  cost: {
    icon: PiggyBank,
    label: "Cost",
    accent: "text-rose-500 bg-rose-500/10 border-rose-500/30",
  },
};

export interface ComingSoonCardProps {
  impactCategory: ImpactCategory;
  /** Headline — e.g. "Revenue impact". */
  title: string;
  /** Plain-language explanation of WHY there's no data yet. */
  reason: string;
  /** What the user can do to unlock this section. */
  unlockedBy: string;
  className?: string;
}

export function ComingSoonCard({
  impactCategory,
  title,
  reason,
  unlockedBy,
  className,
}: ComingSoonCardProps) {
  const impact = IMPACT_META[impactCategory];
  const Icon = impact.icon;

  return (
    <article
      data-testid={`coming-soon-${impactCategory}`}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-dashed border-border bg-card/40 p-5",
        className,
      )}
    >
      <header className="flex items-center gap-2">
        <span
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-md border opacity-60",
            impact.accent,
          )}
          aria-hidden
        >
          <Icon className="h-4 w-4" />
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {impact.label} impact
        </span>
        <span className="ml-auto rounded-md border border-border bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          Coming soon
        </span>
      </header>

      <div className="flex flex-col gap-2">
        <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
        <p className="text-sm text-muted-foreground leading-snug">{reason}</p>
        <p className="text-sm leading-snug">
          <span className="font-medium">Unlocked by:</span> {unlockedBy}
        </p>
      </div>
    </article>
  );
}
