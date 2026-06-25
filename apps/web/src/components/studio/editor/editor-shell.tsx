/**
 * EditorShell (CS5) — the visual editor: toolbar + page tabs + Konva canvas +
 * layer tree + properties. Loads a design into the editor store, lets the user
 * edit visually (every gesture is an EditOp), and on Save commits the pending
 * ops as ONE revision via apply_revision (Pro Mode). Undo/redo walk the local
 * op stack; cross-revision history lives in the revision panel.
 */

"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { selectDirty, useEditorStore } from "@/lib/studio-store";
import type { BrandAsset, DesignResponse } from "@/lib/studio-types";

import { AssetLibrary } from "./asset-library";

const EditorCanvas = dynamic(() => import("./canvas").then((m) => m.EditorCanvas), {
  ssr: false,
  loading: () => (
    <div className="grid h-[450px] w-[360px] place-items-center rounded-lg border border-[var(--border,#e2e8f0)] text-sm text-[var(--muted-foreground,#64748b)]">
      Loading editor…
    </div>
  ),
});

import { LayerTree } from "./layer-tree";
import { PropertiesPanel } from "./properties-panel";

export function EditorShell({
  design,
  onSaved,
}: {
  design: DesignResponse;
  onSaved: () => void;
}) {
  const load = useEditorStore((s) => s.load);
  const undo = useEditorStore((s) => s.undo);
  const redo = useEditorStore((s) => s.redo);
  const discard = useEditorStore((s) => s.discard);
  const pendingOps = useEditorStore((s) => s.pendingOps);
  const redoStack = useEditorStore((s) => s.redoStack);
  const pageIndex = useEditorStore((s) => s.pageIndex);
  const setPage = useEditorStore((s) => s.setPage);
  const doc = useEditorStore((s) => s.workingDoc);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const setAssetUrls = useEditorStore((s) => s.setAssetUrls);
  const replaceImage = useEditorStore((s) => s.replaceImage);
  const dirty = useEditorStore(selectDirty);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    load(design.id, design.doc, design.current_revision);
  }, [design.id, design.current_revision, design.doc, load]);

  // Load the brand asset library URLs so image layers render in the canvas.
  useEffect(() => {
    api.studio.brandAssets
      .list()
      .then((assets) => {
        const map: Record<string, string> = {};
        for (const a of assets) if (a.url) map[a.id] = a.url;
        setAssetUrls(map);
      })
      .catch(() => {});
  }, [design.id, setAssetUrls]);

  // Selecting an asset replaces the currently-selected image layer.
  const onSelectAsset = (asset: BrandAsset) => {
    const layerId = selectedIds[0];
    const layer = doc?.pages.flatMap((p) => p.layers).find((l) => l.id === layerId);
    if (layer && layer.type === "image") {
      replaceImage(layer.id, asset.id, asset.url ?? undefined);
    }
  };

  const save = async () => {
    const { designId, baseRevision, pendingOps: ops } = useEditorStore.getState();
    if (!designId || ops.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      await api.studio.proEdit(designId, { base_revision: baseRevision, ops });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your changes.");
    } finally {
      setSaving(false);
    }
  };

  const pageCount = doc?.pages.length ?? 1;

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <button type="button" onClick={undo} disabled={pendingOps.length === 0}
          className="rounded-md border border-[var(--border,#e2e8f0)] px-2.5 py-1.5 text-sm disabled:opacity-40">↶ Undo</button>
        <button type="button" onClick={redo} disabled={redoStack.length === 0}
          className="rounded-md border border-[var(--border,#e2e8f0)] px-2.5 py-1.5 text-sm disabled:opacity-40">↷ Redo</button>
        <span className="text-xs text-[var(--muted-foreground,#94a3b8)]">
          {pendingOps.length} pending edit{pendingOps.length === 1 ? "" : "s"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={discard} disabled={!dirty}
            className="rounded-md border border-[var(--border,#e2e8f0)] px-2.5 py-1.5 text-sm disabled:opacity-40">Discard</button>
          <button type="button" onClick={() => void save()} disabled={!dirty || saving}
            className="rounded-md bg-[var(--primary,#2563eb)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40">
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {/* Page tabs (poster=1, carousel/reel=N) */}
      {pageCount > 1 && (
        <div className="mb-2 flex gap-1">
          {Array.from({ length: pageCount }).map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setPage(i)}
              className="rounded-md px-2.5 py-1 text-xs"
              style={{
                background: i === pageIndex ? "var(--primary,#2563eb)" : "var(--muted,#f1f5f9)",
                color: i === pageIndex ? "#fff" : undefined,
              }}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

      <div className="flex flex-col gap-4 lg:flex-row">
        <EditorCanvas />
        <div className="flex-1 space-y-4">
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">Layers</h3>
            <LayerTree />
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">Properties</h3>
            <PropertiesPanel />
          </div>
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
              Brand assets
            </h3>
            <AssetLibrary onSelect={onSelectAsset} />
          </div>
        </div>
      </div>
    </div>
  );
}
