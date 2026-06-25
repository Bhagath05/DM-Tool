"use client";

import { ExternalLink } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LandingPagePerformanceRow } from "@/lib/api";
import { formatRateWithCaveat } from "@/lib/stats/confidence";
import { cn } from "@/lib/utils";

export function LandingPagesTable({
  rows,
}: {
  rows: LandingPagePerformanceRow[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Page performance</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-muted-foreground">
            No lead pages yet.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r) => {
              const cvr = formatRateWithCaveat(
                r.submission_count,
                r.view_count,
                { noun: "views" },
              );
              return (
                <div
                  key={r.id}
                  className="grid grid-cols-[1fr_60px_60px_70px] items-center gap-3 px-4 py-3 text-sm"
                >
                  <div className="min-w-0">
                    <a
                      href={`/p/${r.slug}`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex min-w-0 items-center gap-1.5 truncate font-medium hover:underline"
                    >
                      <span className="truncate">{r.title}</span>
                      <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                    </a>
                    <div className="truncate text-[11px] text-muted-foreground">
                      /p/{r.slug}
                      {r.status !== "published" && (
                        <span className="ml-1 rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide">
                          {r.status}
                        </span>
                      )}
                      {cvr.caveat && (
                        <span className="ml-2 italic">{cvr.caveat}</span>
                      )}
                    </div>
                  </div>
                  <Metric label="Views" value={r.view_count} />
                  <Metric label="Leads" value={r.submission_count} />
                  <Metric
                    label="CVR"
                    value={cvr.label}
                    emphasised={
                      cvr.confidence === "reliable" && r.conversion_rate >= 0.05
                    }
                    muted={cvr.muted}
                  />
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  emphasised,
  muted,
}: {
  label: string;
  value: number | string;
  emphasised?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="text-right">
      <div
        className={cn(
          "font-mono text-sm font-semibold tabular-nums",
          emphasised
            ? "text-primary"
            : muted
              ? "text-muted-foreground"
              : "text-foreground",
        )}
      >
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
    </div>
  );
}
