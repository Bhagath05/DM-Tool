"use client";

import { Download, Star } from "lucide-react";

import { absoluteMediaUrl } from "@/components/creative-asset-preview";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GeneratedAd } from "@/lib/api";
import { AD_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

export function RecentList({
  items,
  activeId,
  onSelect,
}: {
  items: GeneratedAd[];
  activeId?: string;
  onSelect: (item: GeneratedAd) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-base">Recent</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {items.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Generated ad creatives will appear here.
          </p>
        )}
        {items.map((item) => {
          const active = item.id === activeId;
          const thumb = item.primary_image_url;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className={cn(
                "w-full rounded-md border px-2 py-2 text-left transition-colors",
                active
                  ? "border-primary bg-accent"
                  : "border-transparent hover:bg-accent",
              )}
            >
              <div className="flex gap-2">
                <div className="h-12 w-12 shrink-0 overflow-hidden rounded border bg-muted">
                  {thumb ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={absoluteMediaUrl(thumb)}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-[9px] text-muted-foreground">
                      …
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {AD_SUBTYPE_LABEL[item.ad_type] ?? prettifyEnum(item.ad_type)}
                    </span>
                    {item.is_saved && (
                      <Star className="h-3 w-3 fill-current text-foreground/70" />
                    )}
                  </div>
                  <div className="mt-0.5 truncate text-sm font-medium">
                    {item.objective} · {item.goal}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">
                    {new Date(item.created_at).toLocaleString()}
                  </div>
                </div>
                {thumb && (
                  <Button
                    asChild
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 shrink-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <a href={absoluteMediaUrl(thumb)} download title="Download">
                      <Download className="h-3.5 w-3.5" />
                    </a>
                  </Button>
                )}
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}
