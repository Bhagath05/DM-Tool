"use client";

/**
 * Phase 10.1 — Settings · Billing.
 *
 * Three honest sections:
 *   1. Current plan       — Early Access (the only real tier today).
 *   2. Usage this period  — derived from the real performance overview
 *                            so the number isn't fabricated.
 *   3. Invoices           — empty-state until real billing lands.
 *   4. Plan comparison    — preview of Starter / Growth / Scale,
 *                            clearly labelled "Coming soon" prices.
 *
 * No simulated charges, no fake invoice rows.
 */

import {
  Check,
  CreditCard,
  Download,
  FileText,
  Receipt,
  Sparkles,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill } from "@/components/ui/status-pill";
import { api, ApiError, type PerformanceOverview } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

interface UsageSnapshot {
  rowsIngested: number;
  creativesTracked: number;
  diagnosticsOpen: number;
  lastUploadAt: string | null;
}

const PLANS = [
  {
    slug: "starter",
    name: "Starter",
    tagline: "For solo founders running their first paid campaigns.",
    bullets: [
      "CSV uploads (up to 30 days)",
      "AI Coach weekly plan",
      "Performance Intelligence (baseline)",
      "1 workspace",
    ],
    accent: "neutral" as const,
  },
  {
    slug: "growth",
    name: "Growth",
    tagline: "For growing brands with multiple ad accounts.",
    bullets: [
      "Live Meta + Google connectors",
      "Creative DNA (full)",
      "Audience + Offer Intelligence",
      "3 workspaces",
      "Priority email support",
    ],
    accent: "ai" as const,
    recommended: true,
  },
  {
    slug: "scale",
    name: "Scale",
    tagline: "For agencies & multi-brand teams.",
    bullets: [
      "Everything in Growth",
      "Unlimited workspaces",
      "Industry benchmark data",
      "Team roles + audit log",
      "Dedicated success manager",
    ],
    accent: "neutral" as const,
  },
];

export default function BillingSettingsPage() {
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const overview: PerformanceOverview = await api.performance.overview();
      setUsage({
        rowsIngested: overview.rows_ingested,
        creativesTracked: overview.creatives_tracked,
        diagnosticsOpen: overview.diagnostics.length,
        lastUploadAt: overview.last_upload_at,
      });
    } catch (err) {
      if (!(err instanceof ApiError)) console.warn(err);
      setUsage(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex flex-col gap-8" data-testid="settings-billing">
      <SectionHeading
        eyebrow="Settings · Billing"
        heading="Plan, usage, and invoices"
        description="Everything about what you're paying for. You're on Early Access right now — no charges, no limits."
        size="lg"
      />

      {/* Current plan card — premium AI surface */}
      <article
        data-testid="billing-current-plan"
        className="card-surface-ai relative overflow-hidden p-6 sm:p-7"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -top-20 -right-20 h-56 w-56 rounded-full bg-ai/15 blur-3xl animate-pulse-soft"
        />
        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-3">
            <StatusPill tone="ai" size="md" dot icon={Sparkles}>
              Early Access
            </StatusPill>
            <h3 className="text-section font-semibold tracking-tight">
              You're an early customer.
            </h3>
            <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
              All features unlocked. No card on file. No hard caps. Your
              feedback shapes what we ship next — and you'll keep a
              founder-discount when paid plans land.
            </p>
            <div className="flex items-center gap-2 text-sm">
              <span className="font-semibold tabular text-foreground">$0</span>
              <span className="text-muted-foreground">/ month · billed never</span>
            </div>
          </div>
          <Button variant="outline" size="sm" disabled>
            Manage plan
          </Button>
        </div>
      </article>

      {/* Usage this period */}
      <article
        data-testid="billing-usage"
        className="card-surface flex flex-col gap-5 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Usage this period"
          description="What we've ingested from your workspace so far. All real data, no projections."
        />
        {loading ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <UsageTile
              label="CSV rows ingested"
              value={usage?.rowsIngested ?? 0}
              suffix="rows"
            />
            <UsageTile
              label="Creatives tracked"
              value={usage?.creativesTracked ?? 0}
              suffix="creatives"
            />
            <UsageTile
              label="Open recommendations"
              value={usage?.diagnosticsOpen ?? 0}
              suffix="cards"
            />
            <UsageTile
              label="Last refresh"
              value={
                usage?.lastUploadAt
                  ? relativeTime(usage.lastUploadAt)
                  : "—"
              }
              suffix={usage?.lastUploadAt ? "ago" : "no uploads yet"}
              numeric={false}
            />
          </div>
        )}
      </article>

      {/* Invoices */}
      <article
        data-testid="billing-invoices"
        className="card-surface flex flex-col gap-5 p-6 sm:p-7"
      >
        <SectionHeading
          heading="Invoices & receipts"
          description="Downloadable PDFs of every charge."
          action={
            <Button variant="outline" size="sm" disabled>
              <Download className="mr-2 h-3.5 w-3.5" />
              Export all
            </Button>
          }
        />
        <EmptyState
          icon={Receipt}
          title="No invoices yet"
          description="You haven't been charged. When paid plans land, every invoice will appear here as a PDF you can download."
          hint="Stripe-issued receipts · GST-compliant for India · USD for the US."
        />
      </article>

      {/* Plan comparison */}
      <article
        data-testid="billing-plans"
        className="flex flex-col gap-5"
      >
        <SectionHeading
          heading="Future plans"
          description="A preview of where pricing is headed. Final tiers + prices will be announced before Early Access ends."
        />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {PLANS.map((p) => (
            <PlanCard key={p.slug} plan={p} />
          ))}
        </div>
      </article>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function UsageTile({
  label,
  value,
  suffix,
  numeric = true,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  numeric?: boolean;
}) {
  return (
    <div
      data-testid="usage-tile"
      className="flex flex-col gap-1.5 rounded-xl border border-border/60 bg-muted/30 p-4"
    >
      <span className="text-meta">{label}</span>
      <span
        className={cn(
          "text-2xl font-semibold tracking-tight",
          numeric && "tabular",
        )}
      >
        {value}
      </span>
      {suffix && (
        <span className="text-xs text-muted-foreground">{suffix}</span>
      )}
    </div>
  );
}

function PlanCard({ plan }: { plan: (typeof PLANS)[number] }) {
  const isAi = plan.accent === "ai";
  return (
    <div
      data-testid={`plan-${plan.slug}`}
      className={cn(
        "card-surface card-surface-hover relative flex flex-col gap-4 p-5",
        isAi && "border-ai-border ring-1 ring-ai/20",
      )}
    >
      {plan.recommended && (
        <span className="absolute -top-2.5 left-5 inline-flex items-center gap-1 rounded-full border border-ai-border bg-ai-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ai-soft-foreground">
          <Sparkles className="h-3 w-3" />
          Most popular
        </span>
      )}
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-card-title">{plan.name}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{plan.tagline}</p>
        </div>
      </header>
      <div className="flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold tabular text-muted-foreground">
          —
        </span>
        <span className="text-xs text-muted-foreground">/ pricing TBD</span>
      </div>
      <ul className="space-y-2 text-sm">
        {plan.bullets.map((b) => (
          <li key={b} className="flex items-start gap-2">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-good" />
            <span className="text-foreground/90">{b}</span>
          </li>
        ))}
      </ul>
      <Button variant={isAi ? "default" : "outline"} size="sm" disabled>
        Coming soon
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Pure helper
// ---------------------------------------------------------------------

function relativeTime(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, now - then);
    const mins = Math.round(diff / 60_000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    const days = Math.round(hrs / 24);
    return `${days}d`;
  } catch {
    return "—";
  }
}
