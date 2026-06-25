/**
 * PropertiesPanel (CS5) — edit the selected layer's properties. Every change
 * emits an EditOp (update_layer / move_layer / resize_layer). Text layers get
 * font controls; all layers get position/size. (Letter-spacing / line-height
 * and crop/mask are deferred — noted in the CS5 completion.)
 */

"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { useEditorStore } from "@/lib/studio-store";
import type { DesignLayer } from "@/lib/studio-types";

function Num({
  label,
  value,
  step = 0.01,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-[var(--muted-foreground,#64748b)]">{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? Math.round(value * 1000) / 1000 : 0}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-20 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
      />
    </label>
  );
}

export function PropertiesPanel() {
  const doc = useEditorStore((s) => s.workingDoc);
  const pageIndex = useEditorStore((s) => s.pageIndex);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const moveLayer = useEditorStore((s) => s.moveLayer);
  const resizeLayer = useEditorStore((s) => s.resizeLayer);
  const updateProps = useEditorStore((s) => s.updateProps);
  const replaceImage = useEditorStore((s) => s.replaceImage);
  const [bgBusy, setBgBusy] = useState(false);

  const id = selectedIds[0];
  const layer: DesignLayer | undefined = doc?.pages[pageIndex]?.layers.find((l) => l.id === id);
  if (!layer) {
    return <p className="text-xs text-[var(--muted-foreground,#64748b)]">Select a layer to edit its properties.</p>;
  }

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground,#64748b)]">
        {layer.role ?? layer.type}
      </p>

      <div className="space-y-1.5">
        <Num label="X" value={layer.x ?? 0} onChange={(v) => moveLayer(layer.id, v, layer.y ?? 0)} />
        <Num label="Y" value={layer.y ?? 0} onChange={(v) => moveLayer(layer.id, layer.x ?? 0, v)} />
        <Num label="W" value={layer.w ?? 1} onChange={(v) => resizeLayer(layer.id, v, layer.h ?? 1)} />
        <Num label="H" value={layer.h ?? 1} onChange={(v) => resizeLayer(layer.id, layer.w ?? 1, v)} />
        <Num label="Rotation" value={layer.rotation ?? 0} step={1} onChange={(v) => updateProps(layer.id, { rotation: v })} />
        <Num label="Opacity" value={layer.opacity ?? 1} onChange={(v) => updateProps(layer.id, { opacity: Math.max(0, Math.min(1, v)) })} />
      </div>

      {layer.type === "text" && (
        <div className="space-y-1.5 border-t border-[var(--border,#e2e8f0)] pt-2">
          <Num
            label="Font size"
            value={layer.font_size ?? 0.05}
            onChange={(v) => updateProps(layer.id, { font_size: Math.max(0.005, v) })}
          />
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--muted-foreground,#64748b)]">Weight</span>
            <select
              value={layer.weight ?? "regular"}
              onChange={(e) => updateProps(layer.id, { weight: e.target.value })}
              className="w-24 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
            >
              {["regular", "medium", "semibold", "bold"].map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--muted-foreground,#64748b)]">Align</span>
            <select
              value={layer.align ?? "left"}
              onChange={(e) => updateProps(layer.id, { align: e.target.value })}
              className="w-24 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
            >
              {["left", "center", "right", "justify"].map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--muted-foreground,#64748b)]">Color</span>
            <input
              value={layer.color ?? ""}
              onChange={(e) => updateProps(layer.id, { color: e.target.value })}
              placeholder="#hex or brand:primary"
              className="w-32 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
            />
          </label>
        </div>
      )}

      {layer.type === "shape" && (
        <label className="flex items-center justify-between gap-2 border-t border-[var(--border,#e2e8f0)] pt-2 text-xs">
          <span className="text-[var(--muted-foreground,#64748b)]">Fill</span>
          <input
            value={layer.fill ?? ""}
            onChange={(e) => updateProps(layer.id, { fill: e.target.value })}
            placeholder="#hex or brand:primary"
            className="w-32 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
          />
        </label>
      )}

      {layer.type === "image" && (
        <div className="space-y-1.5 border-t border-[var(--border,#e2e8f0)] pt-2">
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--muted-foreground,#64748b)]">Fit</span>
            <select
              value={layer.fit ?? "cover"}
              onChange={(e) => updateProps(layer.id, { fit: e.target.value })}
              className="w-24 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
            >
              {["cover", "contain", "fill", "stretch"].map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--muted-foreground,#64748b)]">Mask</span>
            <select
              value={layer.mask?.kind ?? "none"}
              onChange={(e) =>
                updateProps(layer.id, {
                  mask: { kind: e.target.value, radius: layer.mask?.radius ?? 0.15 },
                })
              }
              className="w-24 rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1"
            >
              {["none", "circle", "rounded_rect"].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>
          {layer.mask?.kind === "rounded_rect" && (
            <Num
              label="Corner"
              value={layer.mask.radius ?? 0.15}
              onChange={(v) =>
                updateProps(layer.id, { mask: { kind: "rounded_rect", radius: v } })
              }
            />
          )}
          <p className="pt-1 text-[10px] text-[var(--muted-foreground,#94a3b8)]">
            Pick an asset from the library to replace this image.
          </p>
          <button
            type="button"
            disabled={bgBusy || !layer.asset_id}
            onClick={async () => {
              if (!layer.asset_id) return;
              setBgBusy(true);
              try {
                const a = await api.studio.brandAssets.removeBg(layer.asset_id);
                replaceImage(layer.id, a.id, a.url ?? undefined);
              } finally {
                setBgBusy(false);
              }
            }}
            className="w-full rounded-md border border-[var(--border,#e2e8f0)] px-2 py-1.5 text-xs disabled:opacity-50"
          >
            {bgBusy ? "Removing…" : "Remove background"}
          </button>
        </div>
      )}
    </div>
  );
}
