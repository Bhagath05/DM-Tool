import { beforeEach, describe, expect, it } from "vitest";

import { applyOps, OpError, type EditOp } from "./design-ops";
import { selectDirty, useEditorStore } from "./studio-store";
import type { DesignDoc } from "./studio-types";

function doc(): DesignDoc {
  return {
    version: 1,
    aspect: "4:5",
    pages: [
      {
        background: { kind: "color", color: "#111" },
        layers: [
          { type: "text", id: "h", role: "headline", text: "Hi", x: 0.1, y: 0.1, w: 0.8, h: 0.2, color: "#fff" },
          { type: "shape", id: "box", x: 0, y: 0, w: 1, h: 1 },
        ],
      },
    ],
  };
}

describe("applyOps (mirror of backend grammar)", () => {
  it("set_text / move / resize / update", () => {
    const ops: EditOp[] = [
      { op: "set_text", layer_id: "h", text: "Hello" },
      { op: "move_layer", layer_id: "h", x: 0.2, y: 0.3 },
      { op: "resize_layer", layer_id: "h", w: 0.5, h: 0.1 },
      { op: "update_layer", layer_id: "h", props: { weight: "bold", rotation: 5 } },
    ];
    const out = applyOps(doc(), ops);
    const h = out.pages[0].layers[0];
    expect([h.text, h.x, h.y, h.w, h.h, h.weight, h.rotation]).toEqual([
      "Hello", 0.2, 0.3, 0.5, 0.1, "bold", 5,
    ]);
  });

  it("is pure (source untouched)", () => {
    const src = doc();
    applyOps(src, [{ op: "set_text", layer_id: "h", text: "X" }]);
    expect(src.pages[0].layers[0].text).toBe("Hi");
  });

  it("reorder requires a permutation", () => {
    const out = applyOps(doc(), [{ op: "reorder", page_index: 0, layer_ids: ["box", "h"] }]);
    expect(out.pages[0].layers.map((l) => l.id)).toEqual(["box", "h"]);
    expect(() => applyOps(doc(), [{ op: "reorder", page_index: 0, layer_ids: ["h"] }])).toThrow(OpError);
  });

  it("delete_layer + missing layer throws", () => {
    const out = applyOps(doc(), [{ op: "delete_layer", layer_id: "box" }]);
    expect(out.pages[0].layers.map((l) => l.id)).toEqual(["h"]);
    expect(() => applyOps(doc(), [{ op: "set_text", layer_id: "ghost", text: "x" }])).toThrow(OpError);
  });

  it("set_background", () => {
    const out = applyOps(doc(), [
      { op: "set_background", page_index: 0, background: { kind: "color", color: "#abc" } },
    ]);
    expect(out.pages[0].background.color).toBe("#abc");
  });

  it("replace_image swaps asset_id + clears crop (mirrors backend)", () => {
    const src: DesignDoc = {
      version: 1,
      pages: [{
        background: { kind: "color", color: "#111" },
        layers: [{ type: "image", id: "img", asset_id: "a1", w: 0.5, h: 0.5, crop: { x: 0.1, y: 0.1, w: 0.8, h: 0.8 } }],
      }],
    };
    const out = applyOps(src, [{ op: "replace_image", layer_id: "img", asset_id: "a2" }]);
    expect(out.pages[0].layers[0].asset_id).toBe("a2");
    expect(out.pages[0].layers[0].crop).toBeUndefined();
    expect(src.pages[0].layers[0].asset_id).toBe("a1"); // source untouched
  });
});

describe("editor store — every action emits an EditOp, no direct mutation", () => {
  beforeEach(() => useEditorStore.getState().load("d1", doc(), 1));

  it("load sets base == working, no pending", () => {
    const s = useEditorStore.getState();
    expect(s.pendingOps).toHaveLength(0);
    expect(s.workingDoc).toEqual(s.baseDoc);
    expect(selectDirty(s)).toBe(false);
  });

  it("moveLayer emits move_layer + updates working doc; base untouched", () => {
    useEditorStore.getState().moveLayer("h", 0.4, 0.5);
    const s = useEditorStore.getState();
    expect(s.pendingOps).toEqual([{ op: "move_layer", layer_id: "h", x: 0.4, y: 0.5 }]);
    expect(s.workingDoc!.pages[0].layers[0].x).toBe(0.4);
    expect(s.baseDoc!.pages[0].layers[0].x).toBe(0.1); // base never mutated
    expect(selectDirty(s)).toBe(true);
  });

  it("rotate + setText + updateProps emit ops", () => {
    const st = useEditorStore.getState();
    st.rotateLayer("h", 12);
    st.setText("h", "New");
    st.updateProps("h", { color: "#000" });
    const ops = useEditorStore.getState().pendingOps;
    expect(ops.map((o) => o.op)).toEqual(["update_layer", "set_text", "update_layer"]);
    expect(useEditorStore.getState().workingDoc!.pages[0].layers[0].text).toBe("New");
  });

  it("undo/redo walk the op stack", () => {
    const st = useEditorStore.getState();
    st.moveLayer("h", 0.2, 0.2);
    st.setText("h", "Z");
    expect(useEditorStore.getState().pendingOps).toHaveLength(2);
    st.undo();
    expect(useEditorStore.getState().pendingOps).toHaveLength(1);
    expect(useEditorStore.getState().workingDoc!.pages[0].layers[0].text).toBe("Hi"); // text undone
    st.redo();
    expect(useEditorStore.getState().pendingOps).toHaveLength(2);
    expect(useEditorStore.getState().workingDoc!.pages[0].layers[0].text).toBe("Z");
  });

  it("a new op clears the redo stack", () => {
    const st = useEditorStore.getState();
    st.moveLayer("h", 0.2, 0.2);
    st.undo();
    expect(useEditorStore.getState().redoStack).toHaveLength(1);
    st.setText("h", "fresh");
    expect(useEditorStore.getState().redoStack).toHaveLength(0);
  });

  it("toggleLock emits update_layer{locked}", () => {
    useEditorStore.getState().toggleLock("box");
    const ops = useEditorStore.getState().pendingOps;
    expect(ops).toEqual([{ op: "update_layer", layer_id: "box", props: { locked: true } }]);
  });

  it("toggleHidden is local (no op emitted)", () => {
    useEditorStore.getState().toggleHidden("box");
    expect(useEditorStore.getState().pendingOps).toHaveLength(0);
    expect(useEditorStore.getState().hiddenIds).toEqual(["box"]);
  });

  it("discard clears pending + restores base", () => {
    const st = useEditorStore.getState();
    st.moveLayer("h", 0.9, 0.9);
    st.discard();
    const s = useEditorStore.getState();
    expect(s.pendingOps).toHaveLength(0);
    expect(s.workingDoc).toEqual(s.baseDoc);
  });
});
