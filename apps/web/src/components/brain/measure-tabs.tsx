"use client";

/**
 * Measure sub-navigation — the one coherent "how is my marketing performing"
 * area. Each capability lives at its own route today; this segmented nav makes
 * them read as ONE Measure area ("Measure → Analytics / Performance / Social /
 * Learning Lab / History") instead of separate analytics pages.
 *
 * Phase 6.5: tabs point at the real existing routes (no moved components, no new
 * routes). Link-based (no router hook) so it renders cleanly everywhere,
 * including tests. Wraps on narrow screens — no horizontal overflow. Scope is
 * "what happened / what changed / why / what worked" — external market trends
 * and the Marketing Brain's "what to decide" deliberately live elsewhere.
 */

import { BarChart3, FlaskConical, History, LineChart, Share2 } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type MeasureTab = "analytics" | "performance" | "social" | "lab" | "history";

const TABS: { key: MeasureTab; label: string; href: string; icon: typeof BarChart3 }[] = [
  { key: "analytics", label: "Analytics", href: "/analytics", icon: BarChart3 },
  { key: "performance", label: "Performance", href: "/performance", icon: LineChart },
  { key: "social", label: "Social", href: "/social", icon: Share2 },
  { key: "lab", label: "Learning Lab", href: "/campaign-lab", icon: FlaskConical },
  { key: "history", label: "History", href: "/history", icon: History },
];

export function MeasureTabs({ active }: { active: MeasureTab }) {
  return (
    <nav
      aria-label="Measure views"
      className="inline-flex max-w-full flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-0.5"
      data-testid="measure-tabs"
    >
      {TABS.map((t) => {
        const Icon = t.icon;
        const isActive = t.key === active;
        return (
          <Link
            key={t.key}
            href={t.href as never}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              isActive
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
