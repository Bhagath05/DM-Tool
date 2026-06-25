/**
 * NlEditPanel (CS4) — modify a creative entirely through natural language.
 *
 * Flow: type an instruction → Preview (the router plans it, with a confidence
 * score, and shows the proposed change without writing anything) → Apply
 * (commits via apply_revision; history is preserved). Restyle / transform /
 * variant produce new designs; edit / regenerate revise this one in place.
 */

"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type { DesignDoc, NlEditResponse } from "@/lib/studio-types";

const OP_LABEL: Record<string, string> = {
  edit: "Edit",
  regenerate: "Regenerate",
  transform: "Transform → new design",
  restyle: "Restyle → new design",
  variant: "Variants → new designs",
};

function confidenceTone(c: number): { label: string; color: string } {
  if (c >= 80) return { label: "High", color: "#047857" };
  if (c >= 60) return { label: "Medium", color: "#b45309" };
  if (c >= 40) return { label: "Low", color: "#b45309" };
  return { label: "Speculative", color: "#b91c1c" };
}

export function NlEditPanel({
  designId,
  baseRevision,
  onPreviewDoc,
  onCommitted,
}: {
  designId: string;
  baseRevision: number;
  onPreviewDoc: (doc: DesignDoc | null) => void;
  onCommitted: (result: NlEditResponse) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [preview, setPreview] = useState<NlEditResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setPreview(null);
    onPreviewDoc(null);
  }, [onPreviewDoc]);

  const doPreview = useCallback(async () => {
    if (!instruction.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.studio.nlEdit(designId, {
        instruction: instruction.trim(),
        base_revision: baseRevision,
        preview: true,
      });
      setPreview(res);
      onPreviewDoc(res.proposed_doc ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't plan that edit.");
    } finally {
      setBusy(false);
    }
  }, [instruction, designId, baseRevision, onPreviewDoc]);

  const apply = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.studio.nlEdit(designId, {
        instruction: instruction.trim(),
        base_revision: baseRevision,
        preview: false,
      });
      setInstruction("");
      reset();
      onCommitted(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't apply that edit.");
    } finally {
      setBusy(false);
    }
  }, [instruction, designId, baseRevision, reset, onCommitted]);

  const tone = preview ? confidenceTone(preview.confidence) : null;

  return (
    <div className="mt-4 rounded-md border border-[var(--border,#e2e8f0)] p-3">
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
        Edit with words
      </label>
      <div className="flex gap-2">
        <input
          value={instruction}
          onChange={(e) => {
            setInstruction(e.target.value);
            if (preview) reset();
          }}
          placeholder="Make the CTA stronger · use brand colors · make it for LinkedIn"
          className="flex-1 rounded-md border border-[var(--border,#e2e8f0)] px-3 py-2 text-sm"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !preview) void doPreview();
          }}
        />
        {!preview ? (
          <button
            type="button"
            onClick={() => void doPreview()}
            disabled={busy || !instruction.trim()}
            className="rounded-md border border-[var(--border,#e2e8f0)] px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy ? "Planning…" : "Preview"}
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void apply()}
              disabled={busy}
              className="rounded-md bg-[var(--primary,#2563eb)] px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? "Applying…" : "Apply"}
            </button>
            <button
              type="button"
              onClick={reset}
              disabled={busy}
              className="rounded-md border border-[var(--border,#e2e8f0)] px-3 py-2 text-sm"
            >
              Cancel
            </button>
          </>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {preview && tone && (
        <div className="mt-3 rounded-md bg-[var(--muted,#f8fafc)] p-3 text-sm">
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded bg-[var(--border,#e2e8f0)] px-1.5 py-0.5 text-[11px] font-medium">
              {OP_LABEL[preview.op_class] ?? preview.op_class}
            </span>
            <span
              className="text-[11px] font-semibold"
              style={{ color: tone.color }}
              title={`Confidence ${preview.confidence}/100`}
            >
              {tone.label} confidence · {preview.confidence}%
            </span>
          </div>
          <p>{preview.summary}</p>
          {preview.notes && (
            <p className="mt-1 text-[var(--muted-foreground,#64748b)]">{preview.notes}</p>
          )}
          {preview.proposed_doc ? (
            <p className="mt-1 text-[11px] text-[var(--muted-foreground,#94a3b8)]">
              Preview shown in the canvas — Apply to save as a new revision.
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-[var(--muted-foreground,#94a3b8)]">
              Apply to create the new design(s).
            </p>
          )}
        </div>
      )}
    </div>
  );
}
