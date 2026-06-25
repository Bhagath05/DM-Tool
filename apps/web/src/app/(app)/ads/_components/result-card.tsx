"use client";

import {
  Check,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
  Star,
  Target,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { ActionChips, chipsForAd } from "@/components/action-chips";
import { CreativeAssetPreview } from "@/components/creative-asset-preview";
import { WhyGeneratedCard } from "@/components/why-generated-card";
import { ShareUrlBlock } from "@/components/share-url-block";
import { AssetFooter } from "@/components/ui/asset-footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GeneratedAd } from "@/lib/api";
import { adFooterProps } from "@/lib/asset-meta";
import { AD_SUBTYPE_LABEL, humanizeObjective } from "@/lib/humanize";
import { cn } from "@/lib/utils";

import { AdRenderer, serializeForCopy } from "./ad-renderer";

export function ResultCard({
  item,
  regenerating,
  onRegenerate,
  onToggleSaved,
  onDelete,
}: {
  item: GeneratedAd;
  regenerating: boolean;
  onRegenerate: () => void;
  onToggleSaved: () => void;
  onDelete: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const imageUrl = item.primary_image_url;

  const onCopy = async () => {
    try {
      const body = serializeForCopy(item.ad_type, item.output);
      const text = item.share_url ? `${body}\n\nLink: ${item.share_url}` : body;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard API unavailable in some browsers */
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                {AD_SUBTYPE_LABEL[item.ad_type] ?? item.ad_type}
              </span>
              <span>·</span>
              <span>{item.platform}</span>
              <span>·</span>
              <span>{humanizeObjective(item.objective)}</span>
              <span>·</span>
              <span>{item.goal}</span>
            </div>
            <CardTitle className="mt-2 text-base">Your ad creative</CardTitle>
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
        <CardContent className="space-y-4">
          {imageUrl && (
            <CreativeAssetPreview
              images={[{ signed_url: imageUrl }]}
              alt="Generated ad"
            />
          )}
          <details className="rounded-md border bg-muted/20 px-3 py-2" open={!imageUrl}>
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              Ad copy
            </summary>
            <div className="mt-3">
              <AdRenderer adType={item.ad_type} output={item.output} />
            </div>
          </details>
          <ShareUrlBlock url={item.share_url} />
          <AssetFooter {...adFooterProps(item)} />
          <ActionChips
            label="Take action"
            chips={chipsForAd({
              adType: item.ad_type,
              goal: item.goal,
              objective: item.objective,
            })}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              Why this ad works
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <StrategyRow
              label="What's hot right now we're riding"
              value={item.strategy.trend_influence}
            />
            <StrategyRow
              label="Who this is for"
              value={item.strategy.audience_angle}
            />
            <StrategyRow
              label="What pulls them in"
              value={item.strategy.emotional_trigger}
              emphasize
            />
            <StrategyRow
              label="How it gets them to act"
              value={item.strategy.conversion_strategy}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Target className="h-4 w-4 text-muted-foreground" />
              Who we're showing it to
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <StrategyRow
              label="The person we're talking to"
              value={item.targeting.audience_description}
            />
            <ChipRow label="What they care about" items={item.targeting.interests} />
            <ChipRow
              label="Who they are"
              items={item.targeting.demographics}
            />
            <ChipRow label="What they do online" items={item.targeting.behaviors} />
          </CardContent>
        </Card>
      </div>

      <WhyGeneratedCard sourceAssetId={item.id} />
    </div>
  );
}

function StrategyRow({
  label,
  value,
  emphasize,
}: {
  label: string;
  value: string;
  emphasize?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <p
        className={cn(
          "mt-1 leading-relaxed",
          emphasize ? "text-foreground font-medium" : "text-foreground/90",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.map((i) => (
          <span key={i} className="rounded-md bg-muted px-2 py-0.5 text-xs">
            {i}
          </span>
        ))}
      </div>
    </div>
  );
}
