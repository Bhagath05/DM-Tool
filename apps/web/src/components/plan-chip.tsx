"use client";

/**
 * Phase 10.0 polish — Plan chip.
 *
 * Shows the founder's current subscription tier. We're in early-access
 * so the chip reads "Early Access" — honest, no fabricated tier.
 * When real billing lands (Phase 10.x), this reads from the user/org
 * billing state via a future endpoint and renders the real plan.
 *
 * Visual: AI-tinted soft pill. Becomes a button linking to /billing
 * so the founder can navigate to plan settings.
 */

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function PlanChip({ className }: { className?: string }) {
  return (
    <Link
      href="/billing"
      data-testid="plan-chip"
      className={cn(
        "hidden h-9 items-center gap-1.5 rounded-lg border border-ai-border bg-ai-soft px-2.5 text-xs font-medium text-ai-soft-foreground transition-all duration-200 hover:border-ai/40 hover:bg-ai/10 sm:inline-flex",
        className,
      )}
    >
      <Sparkles className="h-3.5 w-3.5" />
      Early Access
    </Link>
  );
}
