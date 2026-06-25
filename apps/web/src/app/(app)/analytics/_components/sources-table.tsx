"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AssetType, SourceRow } from "@/lib/api";
import {
  ASSET_TYPE_LABEL,
  humanizeMedium,
  humanizeSource,
  prettifyEnum,
} from "@/lib/humanize";

export function SourcesTable({ rows }: { rows: SourceRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Where your customers came from</CardTitle>
        <p className="text-xs text-muted-foreground">
          Ranked by leads that came through each channel.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-muted-foreground">
            No customers yet. Once leads come in, you&apos;ll see which
            channels are working here.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_60px_50px] items-center gap-3 px-4 py-2.5 text-sm"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium">
                    {describeSource(r)}
                  </div>
                  <div className="truncate text-[11px] text-muted-foreground">
                    {describeSourceMeta(r)}
                  </div>
                </div>
                <div className="text-right font-mono text-sm font-semibold tabular-nums">
                  {r.leads}
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  {r.hot_leads > 0 ? `🔥 ${r.hot_leads}` : "—"}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function describeSource(r: SourceRow): string {
  if (r.utm_campaign) return r.utm_campaign;
  if (r.utm_source) return humanizeSource(r.utm_source) ?? r.utm_source;
  if (r.source_asset_type) {
    return (
      ASSET_TYPE_LABEL[r.source_asset_type as AssetType] ??
      prettifyEnum(r.source_asset_type)
    );
  }
  return "Direct visit";
}

function describeSourceMeta(r: SourceRow): string {
  const parts: string[] = [];

  // Asset-type label (only show when we have a campaign name as the primary line)
  if (r.source_asset_type && r.utm_campaign) {
    parts.push(
      ASSET_TYPE_LABEL[r.source_asset_type as AssetType] ?? r.source_asset_type,
    );
  }

  // Source — show humanised, but skip if it's already the main line
  const humanSource = humanizeSource(r.utm_source);
  if (humanSource && humanSource !== describeSource(r)) {
    parts.push(`via ${humanSource}`);
  }

  // Medium — show humanised
  const humanMedium = humanizeMedium(r.utm_medium);
  if (humanMedium) parts.push(humanMedium);

  return parts.join(" · ") || "Came in without tracking info";
}
