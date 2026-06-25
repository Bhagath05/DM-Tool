"use client";

import {
  Check,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import { ActionChips, chipsForVisual } from "@/components/action-chips";
import {
  CreativeAssetPreview,
  rendersFromVisual,
} from "@/components/creative-asset-preview";
import { WhyGeneratedCard } from "@/components/why-generated-card";
import { ShareUrlBlock } from "@/components/share-url-block";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GeneratedVisual } from "@/lib/api";
import { VISUAL_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

import { VisualRenderer, serializeForCopy } from "./visual-renderer";

export function ResultCard({
  item,
  regenerating,
  onRegenerate,
  onToggleSaved,
  onDelete,
}: {
  item: GeneratedVisual;
  regenerating: boolean;
  onRegenerate: () => void;
  onToggleSaved: () => void;
  onDelete: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const renders = rendersFromVisual(item);
  const isImageType =
    item.visual_type === "ad_creative" ||
    item.visual_type === "carousel" ||
    item.visual_type === "thumbnail";

  const onCopy = async () => {
    try {
      const body = serializeForCopy(item.visual_type, item.output);
      const text = item.share_url ? `${body}\n\nLink: ${item.share_url}` : body;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard API unavailable */
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                {VISUAL_SUBTYPE_LABEL[item.visual_type] ??
                  prettifyEnum(item.visual_type)}
              </span>
              <span>·</span>
              <span>{item.platform}</span>
              <span>·</span>
              <span>{item.goal}</span>
            </div>
            <CardTitle className="mt-2 text-base">Your creative</CardTitle>
            {renders.length === 0 && (
              <p className="mt-1 text-sm text-muted-foreground">
                {item.strategy.visual_concept}
              </p>
            )}
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
          {isImageType && (
            <CreativeAssetPreview
              images={renders}
              alt={`${item.visual_type} creative`}
            />
          )}
          {isImageType && renders.length > 0 ? (
            <details className="rounded-md border bg-muted/20 px-3 py-2">
              <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                Creative direction
              </summary>
              <div className="mt-3">
                <VisualRenderer visualType={item.visual_type} output={item.output} />
              </div>
            </details>
          ) : (
            <VisualRenderer visualType={item.visual_type} output={item.output} />
          )}
          <ShareUrlBlock url={item.share_url} />
          <ActionChips
            label="Take action"
            chips={chipsForVisual({
              visualType: item.visual_type,
              goal: item.goal,
              platform: item.platform,
            })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="h-4 w-4 text-muted-foreground" />
            Why this image works
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <StrategyRow
            label="What pulls them in"
            value={item.strategy.emotional_trigger}
            emphasize
          />
          <StrategyRow
            label="Who this is for"
            value={item.strategy.audience_angle}
          />
          <StrategyRow
            label="How it's laid out"
            value={item.strategy.composition_principle}
          />
          <StrategyRow
            label="What's hot right now we're riding"
            value={item.strategy.trend_influence}
          />
          <div className="sm:col-span-2">
            <StrategyRow
              label="How it gets them to act"
              value={item.strategy.conversion_rationale}
            />
          </div>
        </CardContent>
      </Card>

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
