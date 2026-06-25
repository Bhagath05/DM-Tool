/**
 * Pure helpers for the read-only design viewer (CS1). The layer doc stores
 * normalized (0..1) geometry; these convert a layer to absolute CSS and
 * resolve `brand:*` tokens to display colors. No React — trivially testable.
 *
 * This is the *render* of the editable design (an output view); the design
 * doc itself remains the source of truth. The CS5 editor will write back
 * through the same normalized coordinate space.
 */

import type { CSSProperties } from "react";

import type { DesignLayer } from "./studio-types";

const PCT = (n: number) => `${(n * 100).toFixed(3)}%`;

/** Absolute box for a layer, as a fraction of the canvas. */
export function layerBoxStyle(layer: DesignLayer): CSSProperties {
  return {
    position: "absolute",
    left: PCT(layer.x ?? 0),
    top: PCT(layer.y ?? 0),
    width: PCT(layer.w ?? 1),
    height: PCT(layer.h ?? 1),
    transform: layer.rotation ? `rotate(${layer.rotation}deg)` : undefined,
    opacity: layer.opacity ?? 1,
    zIndex: layer.z ?? 0,
  };
}

/** Fallback palette for brand tokens when no brand kit is supplied (viewer
 * is a preview, not the final render). */
const TOKEN_FALLBACKS: Record<string, string> = {
  "brand:primary": "#2563eb",
  "brand:secondary": "#7c3aed",
  "brand:accent": "#f59e0b",
  "brand:ink": "#0f172a",
  "brand:surface": "#ffffff",
  "brand:body": "#334155",
  "brand:heading": "#0f172a",
};

/** Resolve a color/token to a CSS color. Brand tokens use the supplied kit,
 * else a neutral fallback; raw hex passes through. */
export function resolveColor(
  value: string | null | undefined,
  tokens?: Record<string, string>,
): string | undefined {
  if (!value) return undefined;
  if (value.startsWith("brand:")) {
    return tokens?.[value] ?? TOKEN_FALLBACKS[value] ?? "#94a3b8";
  }
  return value;
}

/** CSS `aspect-ratio` value for a doc's aspect string. Defaults to 4/5. */
export function aspectRatioCss(aspect: string | null | undefined): string {
  switch (aspect) {
    case "1:1":
      return "1 / 1";
    case "9:16":
      return "9 / 16";
    case "16:9":
      return "16 / 9";
    case "4:5":
      return "4 / 5";
    default:
      return "4 / 5";
  }
}

/** Flatten a page's layer tree (groups inline) into render order (by z then
 * document order). Read-only: groups contribute their children. */
export function flattenLayers(layers: DesignLayer[]): DesignLayer[] {
  const out: DesignLayer[] = [];
  const walk = (ls: DesignLayer[]) => {
    for (const l of ls) {
      if (l.type === "group" && l.children) walk(l.children);
      else out.push(l);
    }
  };
  walk(layers);
  return out.sort((a, b) => (a.z ?? 0) - (b.z ?? 0));
}
