"use client";

import {
  CalendarDays,
  FileText,
  ImageIcon,
  Megaphone,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { ActionChips, chipsForTopAsset } from "@/components/action-chips";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AssetType, TopAssetRow } from "@/lib/api";
import { ASSET_TYPE_LABEL, subtypeLabel } from "@/lib/humanize";
import { cn } from "@/lib/utils";

/**
 * "What's actually converting" — the one card that closes the loop between
 * "I generated this thing" and "it captured a lead". Each row joins back to
 * the asset that produced it, ranked by lead count.
 */
export function TopAssetsTable({ rows }: { rows: TopAssetRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">What&apos;s actually working</CardTitle>
        <p className="text-xs text-muted-foreground">
          The posts, ads, and campaigns that brought in the most customers.
          Click any of them to see — and re-run — the winners.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <p className="px-6 pb-6 text-sm text-muted-foreground">
            Nothing has driven customers yet. Tip: attach a lead page when
            you generate something — that&apos;s how we know which post
            brought which person in.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r) => (
              <AssetRow key={`${r.source_asset_type}-${r.source_asset_id}`} row={r} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AssetRow({ row }: { row: TopAssetRow }) {
  const Icon = ICON_BY_TYPE[row.source_asset_type] ?? Sparkles;
  return (
    <div>
      <Link
        href={hrefForAsset(row) as never}
        className="grid grid-cols-[28px_1fr_60px_50px] items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-accent/50"
      >
        <Icon className="h-4 w-4 text-muted-foreground" />
        <div className="min-w-0">
          <div className="truncate font-medium">{row.goal}</div>
          <div className="truncate text-[11px] text-muted-foreground">
            {describeMeta(row)}
          </div>
        </div>
        <div className="text-right font-mono text-sm font-semibold tabular-nums">
          {row.leads}
        </div>
        <div className="text-right text-xs text-muted-foreground">
          {row.hot_leads > 0 ? `🔥 ${row.hot_leads}` : "—"}
        </div>
      </Link>
      <div className="px-4 pb-2.5">
        <ActionChips
          chips={chipsForTopAsset({
            assetType: row.source_asset_type,
            subtype: row.subtype,
            platform: row.platform,
            goal: row.goal,
          })}
        />
      </div>
    </div>
  );
}

const ICON_BY_TYPE: Record<AssetType, React.ComponentType<{ className?: string }>> = {
  content: FileText,
  ad: Megaphone,
  visual: ImageIcon,
  campaign: CalendarDays,
};

function describeMeta(r: TopAssetRow): string {
  // Engineering enums → human labels. Avoid duplicates when the asset
  // type label and the subtype say the same thing (e.g. campaign series
  // + product launch don't need to read "Campaign series · Campaign series").
  const assetLabel = ASSET_TYPE_LABEL[r.source_asset_type];
  const subLabel = subtypeLabel(r.source_asset_type, r.subtype);
  const parts =
    assetLabel === subLabel ? [assetLabel] : [assetLabel, subLabel];
  if (r.platform) parts.push(r.platform);
  return parts.join(" · ");
}

function hrefForAsset(r: TopAssetRow): string {
  // Studios don't (yet) deep-link to a single item by id, so we route to the
  // studio index — recent-list will surface the asset. Future enhancement:
  // /content/{id}, /ads/{id}, etc.
  const studio = STUDIO_BY_TYPE[r.source_asset_type] ?? "/dashboard";
  return studio;
}

const STUDIO_BY_TYPE: Record<AssetType, string> = {
  content: "/content",
  ad: "/ads",
  visual: "/visuals",
  campaign: "/campaigns",
};
