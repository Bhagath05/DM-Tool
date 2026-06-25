import { describe, expect, it } from "vitest";

import { flattenLayers, layerBoxStyle, resolveColor } from "./design-layout";
import type { DesignLayer } from "./studio-types";

describe("layerBoxStyle", () => {
  it("converts normalized geometry to percent positioning", () => {
    const s = layerBoxStyle({ type: "text", id: "h", x: 0.1, y: 0.2, w: 0.8, h: 0.3 });
    expect(s.position).toBe("absolute");
    expect(s.left).toBe("10.000%");
    expect(s.top).toBe("20.000%");
    expect(s.width).toBe("80.000%");
    expect(s.height).toBe("30.000%");
  });

  it("applies rotation + opacity + z", () => {
    const s = layerBoxStyle({ type: "shape", id: "s", rotation: 45, opacity: 0.5, z: 3 });
    expect(s.transform).toBe("rotate(45deg)");
    expect(s.opacity).toBe(0.5);
    expect(s.zIndex).toBe(3);
  });

  it("defaults missing geometry to full canvas", () => {
    const s = layerBoxStyle({ type: "shape", id: "bg" });
    expect(s.left).toBe("0.000%");
    expect(s.width).toBe("100.000%");
  });
});

describe("resolveColor", () => {
  it("passes raw hex through", () => {
    expect(resolveColor("#ff0000")).toBe("#ff0000");
  });
  it("resolves brand token from supplied kit", () => {
    expect(resolveColor("brand:primary", { "brand:primary": "#123456" })).toBe("#123456");
  });
  it("falls back for known brand tokens without a kit", () => {
    expect(resolveColor("brand:ink")).toBe("#0f172a");
  });
  it("returns undefined for empty", () => {
    expect(resolveColor(undefined)).toBeUndefined();
  });
});

describe("flattenLayers", () => {
  it("inlines group children and sorts by z", () => {
    const layers: DesignLayer[] = [
      { type: "text", id: "a", z: 2 },
      { type: "group", id: "g", children: [{ type: "shape", id: "b", z: 0 }] },
    ];
    const flat = flattenLayers(layers);
    expect(flat.map((l) => l.id)).toEqual(["b", "a"]); // z 0 before z 2, group inlined
  });
});
