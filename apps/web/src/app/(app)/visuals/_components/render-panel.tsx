"use client";

import {
  AlertCircle,
  Download,
  ImageOff,
  Loader2,
  RefreshCw,
  Sparkles,
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
 * Phase 4-A — the "render this brief into a real image" surface.
 *
 * Lives inline on the visual result card (ad_creative only for now). Shows:
 *   - existing renders for this brief (load on mount)
 *   - a single "Render with AI" button
 *   - a daily-quota indicator
 *   - the most recent render as a large preview with Download + Regenerate
 *
 * No new pages, no new flows. The button does one thing.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function RenderPanel({ visual }: { visual: GeneratedVisual }) {
  // Only show for ad_creative briefs — the backend rejects other types
  // with a 400 anyway, but it's a better UX to hide the affordance.
  if (visual.visual_type !== "ad_creative") return null;

  return <RenderPanelInner visual={visual} />;
}

function RenderPanelInner({ visual }: { visual: GeneratedVisual }) {
  const [renders, setRenders] = useState<RenderedVisual[]>([]);
  const [loading, setLoading] = useState(true);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<{
    used: number;
    cap: number;
    remaining: number;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, q] = await Promise.all([
        api.visuals.listRenders(visual.id),
        api.visuals.renderQuota(),
      ]);
      setRenders(list);
      setQuota({ used: q.used_today, cap: q.daily_cap, remaining: q.remaining });
    } catch {
      // Non-fatal — empty state is fine.
    } finally {
      setLoading(false);
    }
  }, [visual.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRender = async () => {
    setRendering(true);
    setError(null);
    try {
      const rendered = await api.visuals.render(visual.id, { quality: "standard" });
      setRenders((current) => [rendered, ...current]);
      // Refresh quota silently.
      try {
        const q = await api.visuals.renderQuota();
        setQuota({ used: q.used_today, cap: q.daily_cap, remaining: q.remaining });
      } catch {
        /* ignore */
      }
    } catch (e) {
      setError(friendlyRenderError(e));
    } finally {
      setRendering(false);
    }
  };

  const latest = renders[0];
  const capReached = quota !== null && quota.remaining <= 0;
  const disabled = rendering || capReached;

  return (
    <div className="space-y-4 rounded-lg border bg-card/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <Wand2 className="h-3.5 w-3.5" />
            Generate the real creative
          </div>
          <p className="text-xs text-muted-foreground">
            One click → AI renders your brief as a real PNG you can post.
            Text overlays added in post (Canva/CapCut) using the brief.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {quota && (
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                quota.remaining <= 2
                  ? "border-amber-300/50 bg-amber-50 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200"
                  : "border-input text-muted-foreground",
              )}
              title="Daily render cap — refreshes every 24 hours."
            >
              {quota.used} / {quota.cap} today
            </span>
          )}
          <Button
            onClick={handleRender}
            disabled={disabled}
            size="sm"
            title={
              capReached
                ? "Daily render limit reached"
                : "Render this brief into a real image"
            }
          >
            {rendering ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Rendering (~10s)…
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                {latest ? "Render again" : "Render with AI"}
              </>
            )}
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !latest && (
        <div className="flex h-32 items-center justify-center rounded-md border border-dashed text-xs text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          Loading renders…
        </div>
      )}

      {!loading && !latest && (
        <EmptyRenderState rendering={rendering} />
      )}

      {latest && <LatestRender rendered={latest} />}

      {renders.length > 1 && (
        <details className="rounded-md border bg-muted/20 px-3 py-2">
          <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Earlier renders ({renders.length - 1})
          </summary>
          <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {renders.slice(1).map((r) => (
              <RenderThumb key={r.id} rendered={r} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

// ---------------- subcomponents ----------------

function EmptyRenderState({ rendering }: { rendering: boolean }) {
  return (
    <div className="flex h-32 flex-col items-center justify-center gap-2 rounded-md border border-dashed text-xs text-muted-foreground">
      <ImageOff className="h-5 w-5" />
      {rendering ? "Working on the first render…" : "No renders yet — click ‘Render with AI’ to make one."}
    </div>
  );
}

function LatestRender({ rendered }: { rendered: RenderedVisual }) {
  const src = absoluteUrl(rendered.signed_url);
  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-md border bg-black/5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt="AI-rendered ad creative"
          className="w-full"
          loading="lazy"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span>
          {rendered.width}×{rendered.height} · {rendered.provider} · ~$
          {(rendered.cost_cents / 100).toFixed(2)} ·{" "}
          {(rendered.latency_ms / 1000).toFixed(1)}s
        </span>
        <div className="flex items-center gap-1.5">
          <Button asChild size="sm" variant="outline">
            <a href={src} download>
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        </div>
      </div>
    </div>
  );
}

function RenderThumb({ rendered }: { rendered: RenderedVisual }) {
  const src = absoluteUrl(rendered.signed_url);
  return (
    <a
      href={src}
      target="_blank"
      rel="noreferrer"
      className="block overflow-hidden rounded-md border bg-black/5 transition-opacity hover:opacity-80"
      title={`${rendered.width}×${rendered.height} · ${new Date(rendered.created_at).toLocaleString()}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt="earlier render"
        className="aspect-square w-full object-cover"
        loading="lazy"
      />
    </a>
  );
}

// ---------------- helpers ----------------

function absoluteUrl(signedPath: string): string {
  return signedPath.startsWith("http")
    ? signedPath
    : `${API_BASE}${signedPath}`;
}

function friendlyRenderError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429) return e.message;
    if (e.status === 502)
      return "The image provider hiccupped. Try again — most errors here are transient.";
    if (e.status === 400) return e.message;
    if (e.status === 401 || e.status === 403)
      return "Image rendering isn’t configured — your OpenAI key is missing or invalid.";
    return e.message;
  }
  return e instanceof Error ? e.message : "Render failed — please try again.";
}

// Restore the named export referenced in result-card.tsx.
export { RenderPanel as default };

void RefreshCw;
