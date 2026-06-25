/**
 * EditorCanvas (CS5) — interactive Konva surface for Pro-Mode editing.
 *
 * Renders the working doc's current page. Drag → move_layer, transform →
 * resize_layer / rotate (update_layer), double-click text → inline edit →
 * set_text. Every gesture dispatches an EditOp to the store (no direct
 * mutation); the store commits the batch via apply_revision on Save. Locked
 * layers aren't draggable/transformable; hidden layers aren't drawn.
 *
 * Client-only (Konva needs a real canvas) — load via next/dynamic ssr:false.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Image as KonvaImage, Layer, Rect, Stage, Text, Transformer } from "react-konva";
import type Konva from "konva";

import { resolveColor } from "@/lib/design-layout";
import { useEditorStore } from "@/lib/studio-store";
import type { DesignLayer } from "@/lib/studio-types";

import { assetSrc } from "./asset-library";

/** Load a signed asset URL into an HTMLImageElement for Konva. */
function useHtmlImage(url: string | undefined): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!url) {
      setImg(null);
      return;
    }
    const el = new window.Image();
    el.src = url;
    el.onload = () => setImg(el);
    return () => {
      el.onload = null;
    };
  }, [url]);
  return img;
}

/** An image layer rendered from its asset URL, with mask → cornerRadius. */
function ImageNode({
  common,
  layer,
  url,
  w,
  h,
}: {
  common: Record<string, unknown>;
  layer: DesignLayer;
  url: string | undefined;
  w: number;
  h: number;
}) {
  const img = useHtmlImage(assetSrc(url));
  const min = Math.min(w, h);
  const radius =
    layer.mask?.kind === "circle"
      ? min / 2
      : layer.mask?.kind === "rounded_rect"
        ? (layer.mask.radius ?? 0) * min
        : (layer.radius ?? 0) * min;
  if (!img) {
    return (
      <Rect {...common} fill="#f1f5f9" stroke="#cbd5e1" dash={[6, 4]} cornerRadius={radius} />
    );
  }
  return <KonvaImage {...common} image={img} cornerRadius={radius} />;
}

const STAGE_W = 360;

function aspectDims(aspect: string | null | undefined): { w: number; h: number } {
  const map: Record<string, number> = { "1:1": 1, "4:5": 5 / 4, "9:16": 16 / 9, "16:9": 9 / 16 };
  const ratio = map[aspect ?? "4:5"] ?? 5 / 4;
  return { w: STAGE_W, h: Math.round(STAGE_W * ratio) };
}

export function EditorCanvas() {
  const doc = useEditorStore((s) => s.workingDoc);
  const pageIndex = useEditorStore((s) => s.pageIndex);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const hiddenIds = useEditorStore((s) => s.hiddenIds);
  const assetUrls = useEditorStore((s) => s.assetUrls);
  const select = useEditorStore((s) => s.select);
  const moveLayer = useEditorStore((s) => s.moveLayer);
  const resizeLayer = useEditorStore((s) => s.resizeLayer);
  const rotateLayer = useEditorStore((s) => s.rotateLayer);
  const setText = useEditorStore((s) => s.setText);

  const trRef = useRef<Konva.Transformer>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);

  const page = doc?.pages[pageIndex];
  const { w: W, h: H } = aspectDims(doc?.aspect);
  const selectedId = selectedIds[0] ?? null;

  // Attach the transformer to the selected node.
  useEffect(() => {
    const tr = trRef.current;
    const stage = stageRef.current;
    if (!tr || !stage) return;
    const node = selectedId ? stage.findOne<Konva.Node>(`#${selectedId}`) : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedId, pageIndex, doc]);

  const bg = useMemo(
    () => (page?.background.kind === "color" ? resolveColor(page.background.color) ?? "#fff" : "#fff"),
    [page],
  );

  if (!doc || !page) return null;

  const editingLayer = editing ? page.layers.find((l) => l.id === editing.id) : null;

  return (
    <div className="relative" style={{ width: W, height: H }}>
      <Stage
        ref={stageRef}
        width={W}
        height={H}
        className="rounded-lg border border-[var(--border,#e2e8f0)]"
        onMouseDown={(e) => {
          if (e.target === e.target.getStage()) select([]); // click empty → deselect
        }}
      >
        <Layer>
          <Rect x={0} y={0} width={W} height={H} fill={bg} listening={false} />
          {page.layers.map((layer) => {
            if (hiddenIds.includes(layer.id)) return null;
            const x = (layer.x ?? 0) * W;
            const y = (layer.y ?? 0) * H;
            const w = (layer.w ?? 1) * W;
            const h = (layer.h ?? 1) * H;
            const locked = !!layer.locked;
            const common = {
              id: layer.id,
              name: "layer",
              x,
              y,
              width: w,
              height: h,
              rotation: layer.rotation ?? 0,
              opacity: layer.opacity ?? 1,
              draggable: !locked,
              onClick: () => select([layer.id]),
              onTap: () => select([layer.id]),
              onDragEnd: (e: Konva.KonvaEventObject<DragEvent>) =>
                moveLayer(layer.id, e.target.x() / W, e.target.y() / H),
              onTransformEnd: (e: Konva.KonvaEventObject<Event>) => {
                const node = e.target;
                const nw = Math.max(4, node.width() * node.scaleX());
                const nh = Math.max(4, node.height() * node.scaleY());
                node.scaleX(1);
                node.scaleY(1);
                resizeLayer(layer.id, nw / W, nh / H);
                moveLayer(layer.id, node.x() / W, node.y() / H);
                if (Math.abs((node.rotation() ?? 0) - (layer.rotation ?? 0)) > 0.01) {
                  rotateLayer(layer.id, Math.round(node.rotation()));
                }
              },
            };

            if (layer.type === "text") {
              return (
                <Text
                  key={layer.id}
                  {...common}
                  text={layer.text ?? ""}
                  fontSize={(layer.font_size ?? 0.05) * H}
                  fontStyle={layer.weight === "bold" || layer.weight === "semibold" ? "bold" : "normal"}
                  align={layer.align ?? "left"}
                  fill={resolveColor(layer.color) ?? "#111"}
                  onDblClick={() => setEditing({ id: layer.id, value: layer.text ?? "" })}
                  onDblTap={() => setEditing({ id: layer.id, value: layer.text ?? "" })}
                />
              );
            }
            if (layer.type === "shape") {
              return (
                <Rect
                  key={layer.id}
                  {...common}
                  fill={resolveColor(layer.fill) ?? "transparent"}
                  cornerRadius={layer.shape === "ellipse" ? Math.min(w, h) / 2 : (layer.radius ?? 0) * Math.min(w, h)}
                />
              );
            }
            if (layer.type === "image") {
              return (
                <ImageNode
                  key={layer.id}
                  common={common}
                  layer={layer}
                  url={layer.asset_id ? assetUrls[layer.asset_id] : undefined}
                  w={w}
                  h={h}
                />
              );
            }
            // icon / video / audio — placeholder box
            return (
              <Rect
                key={layer.id}
                {...common}
                fill="#f1f5f9"
                stroke="#cbd5e1"
                dash={[6, 4]}
                cornerRadius={(layer.radius ?? 0) * Math.min(w, h)}
              />
            );
          })}
          <Transformer
            ref={trRef}
            rotateEnabled
            keepRatio={false}
            boundBoxFunc={(oldBox, newBox) => (newBox.width < 8 || newBox.height < 8 ? oldBox : newBox)}
          />
        </Layer>
      </Stage>

      {/* Inline text editor overlay */}
      {editing && editingLayer && (
        <textarea
          autoFocus
          value={editing.value}
          onChange={(e) => setEditing({ ...editing, value: e.target.value })}
          onBlur={() => {
            setText(editing.id, editing.value);
            setEditing(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              setText(editing.id, editing.value);
              setEditing(null);
            }
            if (e.key === "Escape") setEditing(null);
          }}
          className="absolute z-10 resize-none rounded border border-[var(--primary,#2563eb)] bg-white/95 p-1 text-sm outline-none"
          style={{
            left: (editingLayer.x ?? 0) * W,
            top: (editingLayer.y ?? 0) * H,
            width: (editingLayer.w ?? 1) * W,
            height: (editingLayer.h ?? 1) * H,
            color: resolveColor(editingLayer.color) ?? "#111",
          }}
        />
      )}
    </div>
  );
}
