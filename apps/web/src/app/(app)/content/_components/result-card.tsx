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

import { ActionChips, chipsForContent } from "@/components/action-chips";
import { InlineImageRender } from "@/components/inline-image-render";
import { ShareUrlBlock } from "@/components/share-url-block";
import { WhyGeneratedCard } from "@/components/why-generated-card";
import { AssetFooter } from "@/components/ui/asset-footer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GeneratedContent } from "@/lib/api";
import { contentFooterProps } from "@/lib/asset-meta";
import { CONTENT_SUBTYPE_LABEL, prettifyEnum } from "@/lib/humanize";
import { cn } from "@/lib/utils";

import { ContentRenderer, serializeForCopy } from "./content-renderer";

export function ResultCard({
  item,
  regenerating,
  onRegenerate,
  onToggleSaved,
  onDelete,
}: {
  item: GeneratedContent;
  regenerating: boolean;
  onRegenerate: () => void;
  onToggleSaved: () => void;
  onDelete: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      const body = serializeForCopy(item.content_type, item.output);
      // Append the attributed share URL so paste-into-platform already
      // contains the link — saves the user a second copy step.
      const text = item.share_url ? `${body}\n\n${item.share_url}` : body;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* ignore — older browsers without clipboard API */
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                {CONTENT_SUBTYPE_LABEL[item.content_type] ??
                  prettifyEnum(item.content_type)}
              </span>
              <span>·</span>
              <span>{item.platform}</span>
              <span>·</span>
              <span>{item.goal}</span>
            </div>
            <CardTitle className="mt-2 text-base">Ready to post</CardTitle>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={onCopy}
              title="Copy plain text"
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
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
                className={cn(
                  "h-3.5 w-3.5",
                  item.is_saved && "fill-current",
                )}
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
          <ContentRenderer
            contentType={item.content_type}
            output={item.output}
          />
          <ShareUrlBlock url={item.share_url} />
          {/* Phase 10.5 Founder-Rule footer — Why / Expected / Best time / Effort.
              Sits directly under the asset so every generated post answers
              the four founder questions before any other detail. */}
          <AssetFooter {...contentFooterProps(item)} />
          <ActionChips
            label="Take action"
            chips={chipsForContent({
              contentType: item.content_type,
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
            Why this works
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              What's hot right now we're riding
            </div>
            <p className="mt-1">{item.strategy.trend_influence}</p>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Who this is for
            </div>
            <p className="mt-1">{item.strategy.audience_angle}</p>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              How it gets them to act
            </div>
            <p className="mt-1 leading-relaxed text-foreground/90">
              {item.strategy.strategy_note}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Reels are video — a still PNG doesn't fit the format. */}
      {item.content_type !== "reel" && (
        <InlineImageRender
          platform={item.platform}
          goal={item.goal}
          tone={item.tone}
          landingPageId={item.landing_page_id}
          hint={item.strategy.audience_angle}
        />
      )}

      <WhyGeneratedCard sourceAssetId={item.id} />
    </div>
  );
}
