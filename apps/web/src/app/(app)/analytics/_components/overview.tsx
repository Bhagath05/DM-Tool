"use client";

import {
  Eye,
  Flame,
  Inbox,
  MousePointerClick,
  Star,
  Target,
  TrendingUp,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { OverviewKpis } from "@/lib/api";
import { formatRateWithCaveat } from "@/lib/stats/confidence";
import { cn } from "@/lib/utils";

export function Overview({ kpis }: { kpis: OverviewKpis }) {
  // Trust upgrade T5 — never claim a percentage when the denominator is
  // tiny. The conversion KPI is the worst offender ("75%" off N=4 views
  // makes the platform look like a toy).
  const conversion = formatRateWithCaveat(
    kpis.total_submissions,
    kpis.total_views,
    { noun: "views" },
  );

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Kpi
        icon={Inbox}
        label="Total leads"
        value={kpis.total_leads.toLocaleString()}
        hint={`${kpis.leads_7d} in last 7d · ${kpis.leads_30d} in last 30d`}
      />
      <Kpi
        icon={Flame}
        label="Hot leads"
        value={kpis.hot_leads.toLocaleString()}
        hint="Marked hot in the inbox"
        accent={kpis.hot_leads > 0}
      />
      <Kpi
        icon={Target}
        label="Conversion"
        value={conversion.label}
        hint={conversion.caveat ?? `${kpis.total_submissions.toLocaleString()} submits / ${kpis.total_views.toLocaleString()} views`}
        mutedValue={conversion.muted}
      />
      <Kpi
        icon={TrendingUp}
        label="Top page"
        value={kpis.top_landing_page_title ?? "—"}
        hint={
          kpis.top_landing_page_slug
            ? `${kpis.top_landing_page_submissions} leads · /p/${kpis.top_landing_page_slug}`
            : "No leads yet"
        }
        truncateValue
      />
      <Kpi
        icon={Eye}
        label="Page views"
        value={kpis.total_views.toLocaleString()}
        hint="Across all published pages"
      />
      <Kpi
        icon={MousePointerClick}
        label="Submissions"
        value={kpis.total_submissions.toLocaleString()}
        hint="Forms completed"
      />
      <Kpi
        icon={Star}
        label="Live pages"
        value={kpis.landing_pages_published.toLocaleString()}
        hint="Published, not archived"
      />
      <Kpi
        icon={TrendingUp}
        label="Weekly velocity"
        value={
          kpis.leads_30d >= 5
            ? `${((kpis.leads_7d / Math.max(kpis.leads_30d / 4, 1)) * 100).toFixed(0)}%`
            : "—"
        }
        hint={
          kpis.leads_30d >= 5
            ? "Last 7d vs. 30d weekly avg"
            : "Not enough leads yet for a velocity read."
        }
        mutedValue={kpis.leads_30d < 5}
      />
    </div>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  accent,
  truncateValue,
  mutedValue,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint: string;
  accent?: boolean;
  truncateValue?: boolean;
  mutedValue?: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-1 pt-5">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <Icon className="h-3.5 w-3.5" />
          {label}
        </div>
        <div
          className={cn(
            "text-2xl font-semibold tabular-nums",
            truncateValue && "truncate",
            accent && "text-primary",
            // Trust upgrade: visibly mute headline values that come from
            // tiny samples so the number doesn't shout false confidence.
            mutedValue && "text-muted-foreground",
          )}
        >
          {value}
        </div>
        <div className="text-xs text-muted-foreground">{hint}</div>
      </CardContent>
    </Card>
  );
}
