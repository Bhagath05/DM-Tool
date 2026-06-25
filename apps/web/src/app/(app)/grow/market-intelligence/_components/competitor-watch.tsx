"use client";

/**
 * Phase 10.3c — Competitor Watch.
 *
 *   XYZ Agency
 *   + New Lead Magnet
 *   + New Facebook Ad
 *   + Posting frequency increased
 *   Risk: Medium · [ Review → ]
 *
 * **Honest scope note**: the backend does NOT have a competitor-crawl
 * pipeline yet. The directive explicitly allows placeholders here.
 * This component:
 *
 *   1. Renders the structured shape a real competitor row will use
 *      (name + change list + risk pill + CTA), so when the backend
 *      ships a competitor endpoint the swap is mechanical.
 *
 *   2. Surfaces an honest empty state ("Connect a competitor to start
 *      tracking") with a single CTA — NOT fake competitor data.
 *
 *   3. If the backend ever returns competitor data via a future API
 *      (e.g. `api.social.competitors()`), drop the empty state and
 *      map the response into `CompetitorRow[]`. No re-design needed.
 */

import { ArrowRight, Eye, Plus } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { StatusPill } from "@/components/ui/status-pill";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------
//  Public shape — ready for a future backend
// ---------------------------------------------------------------------

export type CompetitorRiskLevel = "low" | "medium" | "high";

export interface CompetitorChange {
  /** Short slug for the change. */
  kind:
    | "new_ad"
    | "new_lead_magnet"
    | "new_landing_page"
    | "posting_increase"
    | "engagement_increase"
    | "new_offer";
  /** Founder-friendly label. */
  label: string;
}

export interface CompetitorRow {
  id: string;
  name: string;
  handle: string | null;
  changes: CompetitorChange[];
  risk: CompetitorRiskLevel;
}

export interface CompetitorWatchProps {
  /**
   * When `null` → honest empty state (the current default — no backend).
   * When `[]`  → "all clear" empty state (no changes in the window).
   * When `[...]` → row list rendered.
   */
  rows?: CompetitorRow[] | null;
  className?: string;
}

export function CompetitorWatch({
  rows = null,
  className,
}: CompetitorWatchProps) {
  return (
    <section
      data-testid="competitor-watch"
      className={cn("animate-fade-up flex flex-col gap-4", className)}
    >
      <SectionHeading
        eyebrow={
          <span className="inline-flex items-center gap-1.5">
            <Eye className="h-3 w-3" />
            Competitor watch
          </span>
        }
        heading="What your rivals shipped this week"
        description="New ads, lead magnets, and offers — so you can respond before they win mindshare."
      />

      {rows === null && (
        <div
          data-testid="competitor-watch-placeholder"
          className="rounded-2xl border border-dashed border-border bg-card/60 p-6"
        >
          <EmptyState
            icon={Eye}
            title="Competitor tracking coming soon"
            description="Connect a competitor handle to start receiving alerts when they ship a new ad, lead magnet, or offer."
            hint="Until then, we'll keep your other intelligence sources running."
            data-testid="competitor-watch-empty"
            action={
              <Link
                href={"/settings/integrations" as never}
                className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
              >
                <Plus className="h-3 w-3" />
                Connect a handle
              </Link>
            }
          />
        </div>
      )}

      {rows !== null && rows.length === 0 && (
        <EmptyState
          icon={Eye}
          title="All quiet on the competitor front"
          description="No new ads, lead magnets, or offers detected in the last 7 days."
          data-testid="competitor-watch-clear"
        />
      )}

      {rows !== null && rows.length > 0 && (
        <ul className="flex flex-col gap-3" data-testid="competitor-watch-list">
          {rows.map((row) => (
            <CompetitorRowCard key={row.id} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  Row card
// ---------------------------------------------------------------------

const RISK_TONE: Record<CompetitorRiskLevel, "good" | "watch" | "bad"> = {
  low: "good",
  medium: "watch",
  high: "bad",
};

function CompetitorRowCard({ row }: { row: CompetitorRow }) {
  return (
    <li>
      <article
        data-testid={`competitor-row-${row.id}`}
        className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4"
      >
        <header className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">{row.name}</h3>
          {row.handle && (
            <span className="text-xs text-muted-foreground">@{row.handle}</span>
          )}
          <StatusPill
            tone={RISK_TONE[row.risk]}
            size="sm"
            dot
            className="ml-auto"
          >
            {humanizeRisk(row.risk)} risk
          </StatusPill>
        </header>
        <ul className="flex flex-col gap-1">
          {row.changes.map((c, i) => (
            <li
              key={i}
              className="flex items-start gap-2 text-xs text-muted-foreground"
            >
              <span className="text-good-foreground">+</span>
              <span>{c.label}</span>
            </li>
          ))}
        </ul>
        <Link
          href={"/grow/market-intelligence" as never}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-foreground px-3 py-2 text-xs font-semibold text-background transition-colors hover:bg-foreground/90"
        >
          Review activity
          <ArrowRight className="h-3 w-3" />
        </Link>
      </article>
    </li>
  );
}

function humanizeRisk(r: CompetitorRiskLevel): string {
  return r[0].toUpperCase() + r.slice(1);
}
