"use client";

import {
  AlertCircle,
  Download,
  ImageIcon,
  Loader2,
  RefreshCw,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  type GeneratedVisual,
  type RenderedVisual,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * One-click "render an image for this thing" surface.
 *
 * Composes the two existing API calls:
 *   1. POST /api/v1/visuals/generate  → writes an ad_creative brief
 *   2. POST /api/v1/visuals/{id}/render → renders that brief via DALL-E
 *
 * Why a shared component: the Ads and Content studios both want to let
 * the user generate a matching image inline, without bouncing to a
 * different page. The Visuals studio already has its own dedicated
 * RenderPanel; this is the lighter-weight cousin that hides the brief
 * step from the user and just shows them a button → image.
 *
 * Failure modes are friendly:
 *   - Quota exhausted → button disables with the count.
 *   - Brief or render 4xx → inline AlertCircle with the server's reason.
 *   - Brief succeeds, render fails → we keep the brief and offer Retry.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function InlineImageRender({
  platform,
  goal,
  tone,
  landingPageId,
  // The 'hint' isn't sent over the wire — visuals/generate doesn't have
  // a hint param. But future iterations can use it to bias the strategy
  // prompt server-side. For now it's a no-op + a place to document the
  // calling context.
  hint: _hint,
}: {
  platform: string;
  goal: string;
  tone?: string | null;
  landingPageId?: string | null;
  hint?: string;
}) {
  const [brief, setBrief] = useState<GeneratedVisual | null>(null);
  const [latestRender, setLatestRender] = useState<RenderedVisual | null>(null);
  const [phase, setPhase] = useState<"idle" | "brief" | "render" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<{ remaining: number; cap: number } | null>(
    null,
  );
  // The caller may pass a display label ("Facebook / Instagram (Meta)") that
  // doesn't match the user's raw preferred_platforms ("instagram"). We resolve
  // once and reuse — visuals/generate validates strictly so an unresolved
  // platform always 400s.
  const [preferredPlatforms, setPreferredPlatforms] = useState<string[] | null>(
    null,
  );

  const loadQuota = useCallback(async () => {
    try {
      const q = await api.visuals.renderQuota();
      setQuota({ remaining: q.remaining, cap: q.daily_cap });
    } catch {
      // Non-fatal — the button stays usable, quota just doesn't show.
    }
  }, []);

  useEffect(() => {
    void loadQuota();
    void api.context
      .snapshot()
      .then((c) => setPreferredPlatforms(c.preferred_platforms ?? []))
      .catch(() => setPreferredPlatforms([]));
  }, [loadQuota]);

  const run = async ({ regenerateBrief = false } = {}) => {
    setError(null);
    try {
      const resolvedPlatform = resolvePlatform(platform, preferredPlatforms);
      if (!resolvedPlatform) {
        setError(
          "We couldn't match this ad's platform to one of your preferred " +
            "platforms. Open Onboarding and make sure the platform you want " +
            "this image for is selected.",
        );
        return;
      }

      // Reuse the existing brief unless the user asked to start over.
      let activeBrief = brief;
      if (regenerateBrief || activeBrief === null) {
        setPhase("brief");
        activeBrief = await api.visuals.generate({
          visual_type: "ad_creative",
          platform: resolvedPlatform,
          goal,
          ...(tone ? { tone } : {}),
          ...(landingPageId ? { landing_page_id: landingPageId } : {}),
        });
        setBrief(activeBrief);
      }
      setPhase("render");
      const rendered = await api.visuals.render(activeBrief.id, {
        quality: "standard",
      });
      setLatestRender(rendered);
      setPhase("done");
      void loadQuota();
    } catch (e) {
      setError(friendlyError(e));
      setPhase(brief ? "done" : "idle");
    }
  };

  const capReached = quota !== null && quota.remaining <= 0;
  const working = phase === "brief" || phase === "render";

  return (
    <div className="space-y-3 rounded-lg border border-dashed bg-card/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <Wand2 className="h-3.5 w-3.5" />
            Matching image
          </div>
          <p className="text-xs text-muted-foreground">
            One click — we&apos;ll write a creative brief from these dimensions
            and render it as a PNG you can post.
          </p>
        </div>
        {quota && (
          <span
            className={cn(
              "rounded bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
              capReached
                ? "bg-destructive/15 text-destructive"
                : "text-muted-foreground",
            )}
          >
            {quota.remaining}/{quota.cap} renders today
          </span>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2.5 text-xs text-destructive">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      {latestRender ? (
        <RenderPreview
          rendered={latestRender}
          regenerating={working}
          onRegenerate={() => void run({ regenerateBrief: false })}
          onStartOver={() => void run({ regenerateBrief: true })}
        />
      ) : (
        <div className="flex items-center gap-3">
          <Button
            onClick={() => void run()}
            disabled={working || capReached}
            size="sm"
          >
            {working ? (
              <>
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                {phase === "brief" ? "Writing brief…" : "Rendering…"}
              </>
            ) : (
              <>
                <ImageIcon className="mr-2 h-3.5 w-3.5" />
                Render matching image
              </>
            )}
          </Button>
          {capReached && (
            <span className="text-xs text-muted-foreground">
              Daily render cap reached — resets at midnight.
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function RenderPreview({
  rendered,
  regenerating,
  onRegenerate,
  onStartOver,
}: {
  rendered: RenderedVisual;
  regenerating: boolean;
  onRegenerate: () => void;
  onStartOver: () => void;
}) {
  const src = absoluteMediaUrl(rendered.signed_url);
  return (
    <div className="space-y-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="Rendered image"
        className="w-full rounded-md border bg-muted object-contain"
      />
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm">
          <a href={src} download target="_blank" rel="noreferrer">
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Download
          </a>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onRegenerate}
          disabled={regenerating}
        >
          {regenerating ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          )}
          Render again
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onStartOver}
          disabled={regenerating}
          title="Re-write the creative brief from scratch and render a fresh image"
        >
          <Wand2 className="mr-1.5 h-3.5 w-3.5" />
          New direction
        </Button>
      </div>
    </div>
  );
}

function absoluteMediaUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}

/**
 * Resolve whatever string the caller passed to one of the user's raw
 * preferred-platform keys. Handles the fact that /ads stores display
 * labels ("Facebook / Instagram (Meta)") while /content stores raw
 * lowercase keys ("instagram") that already match.
 *
 * Rules, in order:
 *   1. Exact case-insensitive match → use it.
 *   2. Substring match (caller's string contains a preferred key) → use
 *      that key. "Facebook / Instagram (Meta)" contains "instagram".
 *   3. preferredPlatforms not loaded yet → return the caller's string as
 *      a passthrough; the backend will still 400 but the loading state
 *      already prevented the click.
 *   4. No match → return null. The caller renders a clear error and
 *      the user fixes their preferred-platforms in Onboarding.
 */
function resolvePlatform(
  raw: string,
  preferred: string[] | null,
): string | null {
  if (preferred === null) return raw;
  if (preferred.length === 0) return null;
  const lower = raw.toLowerCase();
  const exact = preferred.find((p) => p.toLowerCase() === lower);
  if (exact) return exact;
  const contained = preferred.find((p) => lower.includes(p.toLowerCase()));
  if (contained) return contained;
  return null;
}

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 402)
      return "Daily render cap reached — try again tomorrow or upgrade the cap in settings.";
    if (err.status === 429)
      return "Too many requests — wait a moment and retry.";
    if (err.status === 400) return err.message || "Bad request.";
    if (err.status >= 500)
      return "Image service is having a moment. Try again shortly.";
    return err.message || "Couldn't render the image.";
  }
  return "Couldn't render the image. Check the network tab and try again.";
}
