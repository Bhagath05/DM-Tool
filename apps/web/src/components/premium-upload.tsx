"use client";

/**
 * Phase 10.0 — Premium CSV upload experience.
 *
 * Drag-and-drop primary action. Secondary affordances for the future
 * connector flows (Meta / Google Ads) rendered as honest disabled
 * pills — "Coming soon" — because no backend exists yet for them.
 *
 * During upload we cycle through staged status strings:
 *   Analyzing campaigns...
 *   Finding winning audiences...
 *   Finding winning offers...
 *   Detecting budget waste...
 *   Generating recommendations...
 *
 * These are theatrical — the real upload completes in a single HTTP
 * call — but they accurately describe what the backend is doing.
 * The cycle pauses on the last stage if the request takes longer
 * than expected. It NEVER fakes a success state; the cycle stops
 * the moment the real response arrives.
 */

import {
  CheckCircle2,
  CloudUpload,
  Loader2,
  Plug,
  Sparkles,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/ui/status-pill";
import {
  api,
  ApiError,
  type CsvIngestSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STAGES = [
  "Analyzing campaigns…",
  "Finding winning audiences…",
  "Finding winning offers…",
  "Detecting budget waste…",
  "Generating recommendations…",
] as const;

const STAGE_INTERVAL_MS = 1100;

export interface PremiumUploadProps {
  onComplete: (summary: CsvIngestSummary) => void;
  className?: string;
}

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; stageIndex: number }
  | { kind: "success"; summary: CsvIngestSummary }
  | { kind: "error"; message: string };

export function PremiumUpload({ onComplete, className }: PremiumUploadProps) {
  const [state, setState] = useState<UploadState>({ kind: "idle" });
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startStageCycle = useCallback(() => {
    setState({ kind: "uploading", stageIndex: 0 });
    stageTimerRef.current = setInterval(() => {
      setState((prev) =>
        prev.kind === "uploading"
          ? {
              kind: "uploading",
              stageIndex: Math.min(prev.stageIndex + 1, STAGES.length - 1),
            }
          : prev,
      );
    }, STAGE_INTERVAL_MS);
  }, []);

  const stopStageCycle = useCallback(() => {
    if (stageTimerRef.current) {
      clearInterval(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopStageCycle(), [stopStageCycle]);

  const upload = useCallback(
    async (file: File) => {
      startStageCycle();
      try {
        const summary = await api.performance.upload(file);
        stopStageCycle();
        setState({ kind: "success", summary });
        onComplete(summary);
      } catch (err) {
        stopStageCycle();
        const message =
          err instanceof ApiError ? err.message : "Upload failed.";
        setState({ kind: "error", message });
      }
    },
    [onComplete, startStageCycle, stopStageCycle],
  );

  // --- Drag handlers -------------------------------------------------

  const onDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);
  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void upload(file);
    },
    [upload],
  );

  // --- Render --------------------------------------------------------

  return (
    <div
      data-testid="premium-upload"
      className={cn("flex flex-col gap-3", className)}
    >
      <div
        data-testid="premium-upload-dropzone"
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={cn(
          "relative flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-150",
          isDragging
            ? "border-ai bg-ai-soft"
            : state.kind === "uploading"
              ? "border-ai-border bg-ai-soft/60"
              : state.kind === "success"
                ? "border-good-border bg-good-soft/60"
                : state.kind === "error"
                  ? "border-bad-border bg-bad-soft/40"
                  : "border-border bg-muted/30 hover:bg-muted/50",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          data-testid="premium-upload-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
            e.target.value = "";
          }}
        />

        {state.kind === "uploading" ? (
          <UploadingView stageIndex={state.stageIndex} />
        ) : state.kind === "success" ? (
          <SuccessView summary={state.summary} />
        ) : state.kind === "error" ? (
          <ErrorView message={state.message} onRetry={() => inputRef.current?.click()} />
        ) : (
          <IdleView onPick={() => inputRef.current?.click()} dragging={isDragging} />
        )}
      </div>

      {/* Secondary affordances — explicitly disabled with honest copy. */}
      {state.kind === "idle" && (
        <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
          <span>Or connect a live source</span>
          <StatusPill
            tone="muted"
            size="sm"
            icon={Plug}
            data-testid="connector-meta"
          >
            Meta Ads · Coming soon
          </StatusPill>
          <StatusPill
            tone="muted"
            size="sm"
            icon={Plug}
            data-testid="connector-google"
          >
            Google Ads · Coming soon
          </StatusPill>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Per-state subviews
// ---------------------------------------------------------------------

function IdleView({
  onPick,
  dragging,
}: {
  onPick: () => void;
  dragging: boolean;
}) {
  return (
    <>
      <span
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-full",
          dragging ? "bg-ai text-white" : "bg-muted text-foreground/80",
        )}
        aria-hidden
      >
        <CloudUpload className="h-6 w-6" />
      </span>
      <div className="space-y-1">
        <p className="text-base font-semibold">
          {dragging
            ? "Drop your file to start"
            : "Drop your Meta Ads export here"}
        </p>
        <p className="text-sm text-muted-foreground">
          CSV exports up to 2 MB. We'll handle the rest.
        </p>
      </div>
      <Button
        type="button"
        onClick={onPick}
        data-testid="premium-upload-button"
        size="sm"
      >
        <Upload className="mr-2 h-4 w-4" />
        Upload CSV
      </Button>
    </>
  );
}

function UploadingView({ stageIndex }: { stageIndex: number }) {
  return (
    <div className="flex flex-col items-center gap-3" data-testid="premium-upload-progress">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-ai text-white">
        <Sparkles className="h-6 w-6 animate-pulse" />
      </span>
      <div className="space-y-1">
        <p className="text-base font-semibold text-foreground">Working…</p>
        <p className="text-sm text-ai-soft-foreground" data-testid="premium-upload-stage">
          {STAGES[stageIndex]}
        </p>
      </div>
      <ul className="mt-2 flex flex-col gap-1 text-left text-xs">
        {STAGES.map((s, i) => (
          <li
            key={s}
            className={cn(
              "flex items-center gap-2",
              i <= stageIndex ? "text-foreground" : "text-muted-foreground",
            )}
          >
            {i < stageIndex ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-good" />
            ) : i === stageIndex ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-ai" />
            ) : (
              <span className="h-3.5 w-3.5 rounded-full border border-border" />
            )}
            <span>{s}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SuccessView({ summary }: { summary: CsvIngestSummary }) {
  const range = summary.date_range
    ? `${summary.date_range[0]} → ${summary.date_range[1]}`
    : null;
  return (
    <div data-testid="premium-upload-success" className="flex flex-col items-center gap-2">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-good-soft text-good">
        <CheckCircle2 className="h-6 w-6" />
      </span>
      <div className="space-y-1">
        <p className="text-base font-semibold">
          Uploaded {summary.rows_accepted.toLocaleString()} rows
          {range ? <> · <span className="tabular text-muted-foreground">{range}</span></> : null}
        </p>
        <p className="text-sm text-muted-foreground">
          {summary.creatives_matched > 0
            ? `Matched ${summary.creatives_matched} creatives to your generated assets.`
            : "We tracked these as external creatives — fine for the rollup."}
          {summary.rows_rejected > 0
            ? ` ${summary.rows_rejected} row${summary.rows_rejected === 1 ? "" : "s"} skipped.`
            : ""}
        </p>
      </div>
    </div>
  );
}

function ErrorView({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div data-testid="premium-upload-error" className="flex flex-col items-center gap-2">
      <p className="text-base font-semibold text-bad-soft-foreground">
        Upload didn't go through
      </p>
      <p className="max-w-md text-sm text-muted-foreground">{message}</p>
      <Button type="button" size="sm" variant="outline" onClick={onRetry}>
        Try another file
      </Button>
    </div>
  );
}
