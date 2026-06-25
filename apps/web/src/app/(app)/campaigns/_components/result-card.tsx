"use client";

import {
  CalendarDays,
  Check,
  Copy,
  Loader2,
  Palette,
  RefreshCw,
  Sparkles,
  Star,
  Trash2,
  Users,
  Waypoints,
} from "lucide-react";
import { useState } from "react";

import { ShareUrlBlock } from "@/components/share-url-block";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CampaignPlan } from "@/lib/api";
import { CAMPAIGN_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

import { CalendarRenderer } from "./calendar-renderer";

export function ResultCard({
  item,
  regenerating,
  onRegenerate,
  onToggleSaved,
  onDelete,
}: {
  item: CampaignPlan;
  regenerating: boolean;
  onRegenerate: () => void;
  onToggleSaved: () => void;
  onDelete: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const { strategy, calendar, share_urls: shareUrls } = item;
  const hasAttribution = Object.keys(shareUrls ?? {}).length > 0;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(serializeForCopy(item));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard API unavailable */
    }
  };

  return (
    <div className="space-y-4">
      {/* Header / actions */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                {CAMPAIGN_SUBTYPE_LABEL[item.campaign_type] ??
                  prettifyEnum(item.campaign_type)}
              </span>
              <span>·</span>
              <span>{item.duration_days} days</span>
              <span>·</span>
              <span>{item.goal}</span>
            </div>
            <CardTitle className="mt-2 text-base">
              {strategy.strategy.campaign_theme}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {strategy.strategy.audience_focus}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={onCopy} title="Copy plain text">
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onRegenerate}
              disabled={regenerating}
              title="Generate another with the same inputs"
            >
              {regenerating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Regenerate
            </Button>
            <Button
              variant={item.is_saved ? "default" : "outline"}
              size="sm"
              onClick={onToggleSaved}
              title={item.is_saved ? "Unsave" : "Save to favourites"}
            >
              <Star
                className={cn("h-3.5 w-3.5", item.is_saved && "fill-current")}
              />
              {item.is_saved ? "Saved" : "Save"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onDelete}
              title="Delete"
              className="text-muted-foreground"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardHeader>
      </Card>

      {/* Strategy + Posting rhythm */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              Funnel strategy
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>{strategy.strategy.funnel_strategy}</p>
            <Row label="CTA progression">
              {strategy.strategy.cta_progression}
            </Row>
            <Row label="Success signals to watch">
              <div className="flex flex-wrap gap-1.5">
                {strategy.strategy.success_signals.map((s) => (
                  <span
                    key={s}
                    className="rounded-md bg-muted px-2 py-0.5 text-xs"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </Row>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Waypoints className="h-4 w-4 text-muted-foreground" />
              Posting rhythm
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>{strategy.strategy.posting_cadence}</p>
            <div className="space-y-2">
              {strategy.sequence.map((s) => (
                <div
                  key={s.phase_name}
                  className="rounded-md border border-border p-2 text-xs"
                >
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-medium uppercase tracking-wide text-muted-foreground">
                      {s.day_range}
                    </span>
                    <span className="text-sm font-semibold">
                      {s.phase_name}
                    </span>
                  </div>
                  <p className="mt-0.5 text-muted-foreground">{s.objective}</p>
                  <p className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    Metric · {s.primary_metric}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Platforms + Visual direction */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Users className="h-4 w-4 text-muted-foreground" />
              Platform roles
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {strategy.platforms.map((p) => (
              <div key={p.platform} className="flex items-start gap-2">
                <span
                  className={cn(
                    "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                    p.role === "primary" && "bg-primary text-primary-foreground",
                    p.role === "secondary" && "bg-muted text-foreground",
                    p.role === "amplifier" && "bg-accent text-foreground",
                  )}
                >
                  {p.role}
                </span>
                <div className="text-xs">
                  <span className="font-medium">{p.platform}</span>{" "}
                  <span className="text-muted-foreground">— {p.rationale}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Palette className="h-4 w-4 text-muted-foreground" />
              Visual direction
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Aesthetic">
              {strategy.visual_direction.aesthetic}
            </Row>
            <Row label="Palette direction">
              {strategy.visual_direction.palette_direction}
            </Row>
            <Row label="Typography direction">
              {strategy.visual_direction.typography_direction}
            </Row>
            <p className="text-[11px] text-muted-foreground">
              Use the Visuals studio to turn this into hex palettes + concrete
              font choices per asset.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Calendar */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <CalendarDays className="h-4 w-4 text-muted-foreground" />
            Campaign calendar · {calendar.length} days
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Banner: either the warning (no LP) or a friendly hint that
              each day has its own link. The dedicated ShareUrlBlock renders
              the warning; a custom info note covers the per-day case. */}
          {!hasAttribution ? (
            <ShareUrlBlock url={null} />
          ) : (
            <div className="rounded-md border bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground">
              Every day below has its own unique link. When you publish a
              post for that day, use the link shown next to it — that&apos;s
              how each customer who clicks gets tracked back to the right day.
            </div>
          )}
          <CalendarRenderer
            days={calendar}
            sequence={strategy.sequence}
            shareUrls={shareUrls}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function serializeForCopy(item: CampaignPlan): string {
  const { strategy, calendar, share_urls: shareUrls } = item;
  const platforms = strategy.platforms
    .map((p) => `  - ${p.platform} (${p.role}) — ${p.rationale}`)
    .join("\n");
  const sequence = strategy.sequence
    .map(
      (s) =>
        `  - ${s.day_range}: ${s.phase_name} → ${s.objective} (metric: ${s.primary_metric})`,
    )
    .join("\n");
  const days = calendar
    .map((d) => {
      const ad =
        d.recommended_ad_support &&
        d.recommended_ad_support.toLowerCase() !== "none"
          ? `\n   AD SUPPORT: ${d.recommended_ad_support}`
          : "";
      const link = shareUrls?.[String(d.day)]
        ? `\n   LINK: ${shareUrls[String(d.day)]}`
        : "";
      return (
        `Day ${d.day} · ${d.platform} · ${d.content_type}\n` +
        `   OBJECTIVE: ${d.objective}\n` +
        `   HOOK: ${d.hook}\n` +
        `   CTA: ${d.cta}\n` +
        `   VISUAL: ${d.visual_direction_summary}\n` +
        `   WHY: ${d.rationale}${ad}${link}`
      );
    })
    .join("\n\n");

  return (
    `THEME: ${strategy.strategy.campaign_theme}\n` +
    `AUDIENCE: ${strategy.strategy.audience_focus}\n` +
    `FUNNEL: ${strategy.strategy.funnel_strategy}\n` +
    `CADENCE: ${strategy.strategy.posting_cadence}\n` +
    `CTA PROGRESSION: ${strategy.strategy.cta_progression}\n` +
    `SUCCESS SIGNALS: ${strategy.strategy.success_signals.join(", ")}\n\n` +
    `PLATFORMS:\n${platforms}\n\n` +
    `SEQUENCE:\n${sequence}\n\n` +
    `VISUAL DIRECTION\n` +
    `  aesthetic:  ${strategy.visual_direction.aesthetic}\n` +
    `  palette:    ${strategy.visual_direction.palette_direction}\n` +
    `  typography: ${strategy.visual_direction.typography_direction}\n\n` +
    `CALENDAR (${calendar.length} days):\n${days}`
  );
}
