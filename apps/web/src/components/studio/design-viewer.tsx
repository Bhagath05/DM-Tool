/**
 * DesignViewer (CS1) — read-only render of an editable design's layer doc.
 *
 * The design doc is the source of truth; this is one output view of it. CS5
 * turns this into the interactive Pro-Mode canvas (same normalized coordinate
 * space). For CS1 it faithfully positions text/shape/icon/image layers inside
 * an aspect-correct box so reviewers can see what the AI produced.
 */

"use client";

import {
  aspectRatioCss,
  flattenLayers,
  layerBoxStyle,
  resolveColor,
} from "@/lib/design-layout";
import type { DesignDoc, DesignLayer } from "@/lib/studio-types";

function LayerView({ layer }: { layer: DesignLayer }) {
  const box = layerBoxStyle(layer);

  if (layer.type === "text") {
    return (
      <div
        style={{
          ...box,
          color: resolveColor(layer.color),
          textAlign: layer.align ?? "left",
          fontWeight:
            layer.weight === "bold"
              ? 700
              : layer.weight === "semibold"
                ? 600
                : layer.weight === "medium"
                  ? 500
                  : 400,
          fontSize: layer.font_size ? `${(layer.font_size * 100).toFixed(1)}cqh` : undefined,
          overflow: "hidden",
          lineHeight: 1.1,
        }}
        data-role={layer.role ?? undefined}
      >
        {layer.text}
      </div>
    );
  }

  if (layer.type === "shape") {
    return (
      <div
        style={{
          ...box,
          background: resolveColor(layer.fill) ?? "transparent",
          borderRadius:
            layer.shape === "ellipse" ? "9999px" : `${(layer.radius ?? 0) * 100}%`,
        }}
        data-role={layer.role ?? undefined}
      />
    );
  }

  if (layer.type === "icon") {
    return (
      <div
        style={{ ...box, color: resolveColor(layer.color), display: "grid", placeItems: "center" }}
        data-role={layer.role ?? undefined}
        title={layer.icon_name}
      >
        <span aria-hidden style={{ fontSize: "min(2rem, 60cqh)" }}>◆</span>
      </div>
    );
  }

  // image / video / audio — show a labelled placeholder (real media lands in CS5).
  return (
    <div
      style={{
        ...box,
        display: "grid",
        placeItems: "center",
        background: "color-mix(in srgb, currentColor 8%, transparent)",
        border: "1px dashed color-mix(in srgb, currentColor 25%, transparent)",
        borderRadius: layer.type === "image" ? `${(layer.radius ?? 0) * 100}%` : 0,
        fontSize: "0.7rem",
        opacity: 0.7,
      }}
      data-role={layer.role ?? undefined}
    >
      {layer.type}
    </div>
  );
}

export function DesignViewer({ doc, pageIndex = 0 }: { doc: DesignDoc; pageIndex?: number }) {
  const page = doc.pages[pageIndex];
  if (!page) return null;
  const bg =
    page.background.kind === "color"
      ? resolveColor(page.background.color) ?? "#ffffff"
      : "#ffffff";

  return (
    <div
      className="relative mx-auto w-full max-w-sm overflow-hidden rounded-lg border border-[var(--border,#e2e8f0)]"
      style={{ aspectRatio: aspectRatioCss(doc.aspect), background: bg, containerType: "size" }}
      role="img"
      aria-label="Design preview"
    >
      {flattenLayers(page.layers).map((layer) => (
        <LayerView key={layer.id} layer={layer} />
      ))}
    </div>
  );
}
