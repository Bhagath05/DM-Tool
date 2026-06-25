/**
 * Editor-side EditOps — the SAME grammar the backend (`ops.py`) and the AI
 * emit (Law 3). A human drag/resize/retype produces an EditOp here; the
 * editor applies it locally for instant feedback (`applyOps`) and commits the
 * batch through `apply_revision` on the server, which re-applies the identical
 * ops. There is no direct doc mutation — every change is an op.
 *
 * Pure functions, no React — trivially unit-testable, and faithful to the
 * server so the local preview matches the committed result.
 */

import type { DesignDoc, DesignLayer } from "./studio-types";

export type EditOp =
  | { op: "set_text"; layer_id: string; text: string }
  | { op: "replace_image"; layer_id: string; asset_id: string }
  | { op: "move_layer"; layer_id: string; x: number; y: number }
  | { op: "resize_layer"; layer_id: string; w: number; h: number }
  | { op: "update_layer"; layer_id: string; props: Record<string, unknown> }
  | { op: "reorder"; page_index: number; layer_ids: string[] }
  | { op: "set_background"; page_index: number; background: Record<string, unknown> }
  | { op: "add_layer"; page_index: number; layer: Record<string, unknown> }
  | { op: "delete_layer"; layer_id: string };

export class OpError extends Error {}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v));
}

function findLayer(layers: DesignLayer[], id: string): DesignLayer | null {
  for (const ly of layers) {
    if (ly.id === id) return ly;
    if (ly.type === "group" && ly.children) {
      const f = findLayer(ly.children, id);
      if (f) return f;
    }
  }
  return null;
}

function removeLayer(layers: DesignLayer[], id: string): boolean {
  for (let i = 0; i < layers.length; i++) {
    if (layers[i].id === id) {
      layers.splice(i, 1);
      return true;
    }
    const ly = layers[i];
    if (ly.type === "group" && ly.children && removeLayer(ly.children, id)) return true;
  }
  return false;
}

function requireLayer(doc: DesignDoc, id: string): DesignLayer {
  for (const page of doc.pages) {
    const ly = findLayer(page.layers, id);
    if (ly) return ly;
  }
  throw new OpError(`layer ${id} not found`);
}

function page(doc: DesignDoc, idx: number) {
  if (idx < 0 || idx >= doc.pages.length) throw new OpError(`page_index ${idx} out of range`);
  return doc.pages[idx];
}

/** Apply one op to a (mutable) doc in place. Internal — callers use applyOps. */
function applyOne(doc: DesignDoc, op: EditOp): void {
  switch (op.op) {
    case "set_text":
      (requireLayer(doc, op.layer_id) as DesignLayer).text = op.text;
      break;
    case "replace_image": {
      const ly = requireLayer(doc, op.layer_id);
      ly.asset_id = op.asset_id;
      delete ly.crop; // a new image invalidates the old crop region
      break;
    }
    case "move_layer": {
      const ly = requireLayer(doc, op.layer_id);
      ly.x = op.x;
      ly.y = op.y;
      break;
    }
    case "resize_layer": {
      const ly = requireLayer(doc, op.layer_id);
      ly.w = op.w;
      ly.h = op.h;
      break;
    }
    case "update_layer":
      Object.assign(requireLayer(doc, op.layer_id) as unknown as Record<string, unknown>, clone(op.props));
      break;
    case "reorder": {
      const p = page(doc, op.page_index);
      const byId = new Map(p.layers.map((l) => [l.id, l]));
      if (op.layer_ids.length !== p.layers.length || op.layer_ids.some((id) => !byId.has(id))) {
        throw new OpError("reorder ids must be a permutation of the page's layers");
      }
      p.layers = op.layer_ids.map((id) => byId.get(id)!);
      break;
    }
    case "set_background":
      page(doc, op.page_index).background = clone(
        op.background,
      ) as unknown as DesignDoc["pages"][number]["background"];
      break;
    case "add_layer":
      page(doc, op.page_index).layers.push(clone(op.layer) as unknown as DesignLayer);
      break;
    case "delete_layer":
      if (!doc.pages.some((p) => removeLayer(p.layers, op.layer_id))) {
        throw new OpError(`layer ${op.layer_id} not found`);
      }
      break;
    default: {
      const _exhaustive: never = op;
      throw new OpError(`unknown op ${JSON.stringify(_exhaustive)}`);
    }
  }
}

/** Pure: returns a NEW doc with the ops applied. */
export function applyOps(doc: DesignDoc, ops: EditOp[]): DesignDoc {
  const next = clone(doc);
  for (const op of ops) applyOne(next, op);
  return next;
}
