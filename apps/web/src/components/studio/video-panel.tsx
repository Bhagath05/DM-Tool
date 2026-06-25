/**
 * VideoPanel (CS6) — render a reel/storyboard design into an MP4 and publish.
 *
 * Shown for video designs. "Render to video" kicks off the async Veo pipeline
 * (the request returns immediately); the panel polls status until ready, then
 * plays the MP4 (with captions) and offers per-platform exports. The design
 * stays the source of truth; the MP4 is an output.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { VideoExport, VideoStatus } from "@/lib/studio-types";

import { assetSrc } from "./editor/asset-library";

const PLATFORMS: { id: string; label: string }[] = [
  { id: "instagram_reels", label: "Instagram Reels" },
  { id: "tiktok", label: "TikTok" },
  { id: "youtube_shorts", label: "YouTube Shorts" },
  { id: "facebook_reels", label: "Facebook Reels" },
  { id: "linkedin", label: "LinkedIn" },
];

const IN_PROGRESS = new Set(["scripting", "rendering", "post_processing", "queued", "draft"]);

export function VideoPanel({ designId }: { designId: string }) {
  const [status, setStatus] = useState<VideoStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exports, setExports] = useState<VideoExport[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const st = await api.studio.videoStatus(designId);
      setStatus(st);
      if (!IN_PROGRESS.has(st.status)) {
        stop();
        if (st.asset_id) api.studio.listExports(st.asset_id).then(setExports).catch(() => {});
      }
    } catch {
      /* keep last status */
    }
  }, [designId, stop]);

  useEffect(() => {
    setExports([]);
    void refresh();
    return stop;
  }, [designId, refresh, stop]);

  const render = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.studio.renderVideo(designId);
      void refresh();
      stop();
      timer.current = setInterval(() => void refresh(), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the render.");
    } finally {
      setBusy(false);
    }
  }, [designId, refresh, stop]);

  const addExports = useCallback(async () => {
    if (!status?.asset_id) return;
    const items = await api.studio.createExports(status.asset_id, PLATFORMS.map((p) => p.id));
    setExports(items);
  }, [status]);

  const rendering = status ? IN_PROGRESS.has(status.status) : false;
  const ready = status?.status === "ready" && status.video_url;

  return (
    <div className="mt-4 rounded-md border border-[var(--border,#e2e8f0)] p-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
          Video
        </h3>
        {status && status.status !== "none" && (
          <span className="text-[11px] text-[var(--muted-foreground,#94a3b8)]">{status.status}</span>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {ready ? (
        <div className="mt-2 space-y-2">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            controls
            src={assetSrc(status!.video_url)}
            className="w-full rounded-md border border-[var(--border,#e2e8f0)]"
            style={{ maxHeight: 420 }}
          >
            {status!.captions_url && (
              <track kind="captions" srcLang="en" src={assetSrc(status!.captions_url)} default />
            )}
          </video>
          <div>
            <button
              type="button"
              onClick={() => void addExports()}
              className="rounded-md border border-[var(--border,#e2e8f0)] px-2.5 py-1.5 text-xs"
            >
              Prepare publishing exports
            </button>
            {exports.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {exports.map((ex) => (
                  <li
                    key={ex.id}
                    className="rounded bg-[var(--muted,#f1f5f9)] px-2 py-0.5 text-[11px]"
                    title={`${ex.width}×${ex.height}`}
                  >
                    {PLATFORMS.find((p) => p.id === ex.target_platform)?.label ?? ex.target_platform} · {ex.status}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button
            type="button"
            onClick={() => void render()}
            disabled={busy}
            className="text-[11px] text-[var(--primary,#2563eb)] underline disabled:opacity-50"
          >
            Re-render
          </button>
        </div>
      ) : (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => void render()}
            disabled={busy || rendering}
            className="rounded-md bg-[var(--primary,#2563eb)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {rendering ? "Rendering…" : busy ? "Starting…" : "Render to video"}
          </button>
          {rendering && (
            <p className="mt-1 text-[11px] text-[var(--muted-foreground,#94a3b8)]">
              Generating scenes with Veo — this runs in the background.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
