"use client";

import { Star } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CampaignPlan } from "@/lib/api";
import { CAMPAIGN_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

export function RecentList({
  items,
  activeId,
  onSelect,
}: {
  items: CampaignPlan[];
  activeId?: string;
  onSelect: (item: CampaignPlan) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-base">Recent</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Generated campaign plans will appear here.
          </p>
        )}
        {items.map((item) => {
          const active = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left transition-colors",
                active
                  ? "border-primary bg-accent"
                  : "border-transparent hover:bg-accent",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {CAMPAIGN_SUBTYPE_LABEL[item.campaign_type] ?? prettifyEnum(item.campaign_type)} · {item.duration_days}d
                </span>
                {item.is_saved && (
                  <Star className="h-3 w-3 fill-current text-foreground/70" />
                )}
              </div>
              <div className="mt-0.5 truncate text-sm font-medium">
                {item.strategy.strategy.campaign_theme}
              </div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                {new Date(item.created_at).toLocaleString()}
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}
