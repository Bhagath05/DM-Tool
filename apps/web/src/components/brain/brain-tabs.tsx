"use client";

/**
 * Marketing Brain sub-navigation — the one coherent AI workspace.
 *
 * The Brain has several capabilities that each live at their own route today;
 * this segmented nav is what makes them read as ONE product ("Marketing Brain →
 * Ask / Business / Knowledge / Decisions / Board") rather than separate AI
 * apps. Link-based (no router hook) so it renders cleanly everywhere, including
 * tests. Wraps on narrow screens — no horizontal overflow.
 *
 * Phase 6.3: tabs point at the real existing routes (no moved components, no new
 * routes). The labels communicate the IA; the URLs stay canonical.
 */

import { Brain, Compass, LayoutGrid, Lightbulb, MessageSquare } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type BrainTab = "ask" | "business" | "knowledge" | "decisions" | "board";

const TABS: { key: BrainTab; label: string; href: string; icon: typeof Brain }[] = [
  { key: "ask", label: "Ask", href: "/ai", icon: MessageSquare },
  { key: "business", label: "Business", href: "/brand-brain", icon: Brain },
  { key: "knowledge", label: "Knowledge", href: "/ai-employee/beliefs", icon: Lightbulb },
  { key: "decisions", label: "Decisions", href: "/ai-coach", icon: Compass },
  { key: "board", label: "Board", href: "/ai/board", icon: LayoutGrid },
];

export function BrainTabs({ active }: { active: BrainTab }) {
  return (
    <nav
      aria-label="Marketing Brain views"
      className="inline-flex max-w-full flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-0.5"
      data-testid="brain-tabs"
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
