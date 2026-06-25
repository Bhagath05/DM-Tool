/**
 * Editor state (Zustand) — the working copy + the pending EditOps.
 *
 * Every manual action (drag/resize/rotate/retype/recolor/reorder/lock) emits
 * an EditOp; the working doc is always `applyOps(baseDoc, pendingOps)` — there
 * is NO direct doc mutation. Undo/redo walk the pending-op stack. "Save"
 * commits `pendingOps` as ONE revision via apply_revision on the server, which
 * re-applies the identical ops (Law 3). Cross-revision undo is the revision
 * history's revert.
 *
 * `hidden` is a local view aid only (the schema has no hidden field, so it is
 * never committed). `locked` IS a layer field, so lock/unlock emits an op.
 */

import { create } from "zustand";

import { applyOps, type EditOp } from "./design-ops";
import type { DesignDoc, DesignLayer } from "./studio-types";

function recompute(base: DesignDoc | null, ops: EditOp[]): DesignDoc | null {
  if (!base) return null;
  try {
    return applyOps(base, ops);
  } catch {
    return base; // a bad op never corrupts the view; the server is the guard too
  }
}

function findLayer(doc: DesignDoc | null, id: string): DesignLayer | null {
  if (!doc) return null;
  for (const page of doc.pages) {
    for (const ly of page.layers) {
      if (ly.id === id) return ly;
    }
  }
  return null;
}

export interface EditorState {
  designId: string | null;
  baseDoc: DesignDoc | null;
  baseRevision: number;
  pendingOps: EditOp[];
  redoStack: EditOp[];
  workingDoc: DesignDoc | null;
  pageIndex: number;
  selectedIds: string[];
  hiddenIds: string[];
  assetUrls: Record<string, string>; // asset_id → signed url, for image rendering

  load: (designId: string, doc: DesignDoc, revision: number) => void;
  setAssetUrls: (map: Record<string, string>) => void;
  replaceImage: (layerId: string, assetId: string, url?: string) => void;
  setPage: (i: number) => void;
  select: (ids: string[]) => void;
  toggleSelect: (id: string) => void;

  pushOp: (op: EditOp) => void;
  moveLayer: (id: string, x: number, y: number) => void;
  resizeLayer: (id: string, w: number, h: number) => void;
  rotateLayer: (id: string, rotation: number) => void;
  setText: (id: string, text: string) => void;
  updateProps: (id: string, props: Record<string, unknown>) => void;
  reorder: (pageIndex: number, layerIds: string[]) => void;
  setBackground: (pageIndex: number, background: Record<string, unknown>) => void;
  deleteLayer: (id: string) => void;
  toggleLock: (id: string) => void;
  toggleHidden: (id: string) => void;

  undo: () => void;
  redo: () => void;
  discard: () => void;
}

/** Pending edits exist (use in components — Zustand getters don't survive set). */
export const selectDirty = (s: EditorState): boolean => s.pendingOps.length > 0;

export const useEditorStore = create<EditorState>((set, getState) => ({
  designId: null,
  baseDoc: null,
  baseRevision: 0,
  pendingOps: [],
  redoStack: [],
  workingDoc: null,
  pageIndex: 0,
  selectedIds: [],
  hiddenIds: [],
  assetUrls: {},

  load: (designId, doc, revision) =>
    set({
      designId, baseDoc: doc, baseRevision: revision, workingDoc: doc,
      pendingOps: [], redoStack: [], pageIndex: 0, selectedIds: [], hiddenIds: [],
    }),
  setAssetUrls: (map) => set((s) => ({ assetUrls: { ...s.assetUrls, ...map } })),
  replaceImage: (layerId, assetId, url) => {
    if (url) set((s) => ({ assetUrls: { ...s.assetUrls, [assetId]: url } }));
    getState().pushOp({ op: "replace_image", layer_id: layerId, asset_id: assetId });
  },

  setPage: (i) => set({ pageIndex: i, selectedIds: [] }),
  select: (ids) => set({ selectedIds: ids }),
  toggleSelect: (id) =>
    set((s) => ({
      selectedIds: s.selectedIds.includes(id)
        ? s.selectedIds.filter((x) => x !== id)
        : [...s.selectedIds, id],
    })),

  pushOp: (op) =>
    set((s) => {
      const pendingOps = [...s.pendingOps, op];
      return { pendingOps, redoStack: [], workingDoc: recompute(s.baseDoc, pendingOps) };
    }),

  moveLayer: (id, x, y) => getState().pushOp({ op: "move_layer", layer_id: id, x, y }),
  resizeLayer: (id, w, h) => getState().pushOp({ op: "resize_layer", layer_id: id, w, h }),
  rotateLayer: (id, rotation) =>
    getState().pushOp({ op: "update_layer", layer_id: id, props: { rotation } }),
  setText: (id, text) => getState().pushOp({ op: "set_text", layer_id: id, text }),
  updateProps: (id, props) => getState().pushOp({ op: "update_layer", layer_id: id, props }),
  reorder: (pageIndex, layerIds) =>
    getState().pushOp({ op: "reorder", page_index: pageIndex, layer_ids: layerIds }),
  setBackground: (pageIndex, background) =>
    getState().pushOp({ op: "set_background", page_index: pageIndex, background }),
  deleteLayer: (id) =>
    set((s) => {
      const pendingOps = [...s.pendingOps, { op: "delete_layer", layer_id: id } as EditOp];
      return {
        pendingOps, redoStack: [], workingDoc: recompute(s.baseDoc, pendingOps),
        selectedIds: s.selectedIds.filter((x) => x !== id),
      };
    }),

  toggleLock: (id) => {
    const ly = findLayer(getState().workingDoc, id);
    getState().updateProps(id, { locked: !(ly?.locked ?? false) });
  },
  toggleHidden: (id) =>
    set((s) => ({
      hiddenIds: s.hiddenIds.includes(id)
        ? s.hiddenIds.filter((x) => x !== id)
        : [...s.hiddenIds, id],
    })),

  undo: () =>
    set((s) => {
      if (s.pendingOps.length === 0) return {};
      const pendingOps = s.pendingOps.slice(0, -1);
      const undone = s.pendingOps[s.pendingOps.length - 1];
      return {
        pendingOps, redoStack: [...s.redoStack, undone],
        workingDoc: recompute(s.baseDoc, pendingOps),
      };
    }),
  redo: () =>
    set((s) => {
      if (s.redoStack.length === 0) return {};
      const op = s.redoStack[s.redoStack.length - 1];
      const pendingOps = [...s.pendingOps, op];
      return {
        pendingOps, redoStack: s.redoStack.slice(0, -1),
        workingDoc: recompute(s.baseDoc, pendingOps),
      };
    }),
  discard: () =>
    set((s) => ({ pendingOps: [], redoStack: [], workingDoc: s.baseDoc, selectedIds: [] })),
}));
