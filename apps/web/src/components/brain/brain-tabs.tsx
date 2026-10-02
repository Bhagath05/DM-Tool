"use client";

/**
 * Segmented nav inside the Marketing Brain area: Chat ↔ Board.
 * Link-based (no router hook) so it renders cleanly everywhere, including tests.
 */

import { LayoutGrid, MessageSquare } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

const TABS = [
  { key: "chat", label: "Chat", href: "/ai", icon: MessageSquare },
  { key: "board", label: "Board", href: "/ai/board", icon: LayoutGrid },
] as const;

export function BrainTabs({ active }: { active: "chat" | "board" }) {
  return (
    <nav
      aria-label="Marketing Brain views"
      className="inline-flex items-center gap-1 rounded-lg border border-border bg-card p-0.5"
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
            <Icon className="h-3.5 w-3.5" />
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
