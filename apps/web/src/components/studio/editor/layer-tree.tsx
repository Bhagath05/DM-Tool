/**
 * LayerTree (CS5) — select / hide / lock / reorder layers on the current page.
 * Reordering emits a `reorder` EditOp (full permutation); lock emits
 * `update_layer{locked}`; hide is a local view toggle.
 */

"use client";

import { useEditorStore } from "@/lib/studio-store";
import type { DesignLayer } from "@/lib/studio-types";

function label(l: DesignLayer): string {
  const base = l.role ?? l.type;
  if (l.type === "text" && l.text) return `${base} · "${l.text.slice(0, 18)}"`;
  return base;
}

export function LayerTree() {
  const doc = useEditorStore((s) => s.workingDoc);
  const pageIndex = useEditorStore((s) => s.pageIndex);
  const selectedIds = useEditorStore((s) => s.selectedIds);
  const hiddenIds = useEditorStore((s) => s.hiddenIds);
  const select = useEditorStore((s) => s.select);
  const toggleLock = useEditorStore((s) => s.toggleLock);
  const toggleHidden = useEditorStore((s) => s.toggleHidden);
  const reorder = useEditorStore((s) => s.reorder);

  const page = doc?.pages[pageIndex];
  if (!page) return null;

  // Show top layer first (reverse paint order).
  const rows = page.layers.map((l, i) => ({ l, i })).reverse();

  const swap = (i: number, j: number) => {
    if (j < 0 || j >= page.layers.length) return;
    const ids = page.layers.map((l) => l.id);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder(pageIndex, ids);
  };

  return (
    <ul className="space-y-0.5">
      {rows.map(({ l, i }) => {
        const selected = selectedIds.includes(l.id);
        const hidden = hiddenIds.includes(l.id);
        return (
          <li
            key={l.id}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-xs"
            style={{ background: selected ? "var(--muted,#eef2ff)" : undefined }}
          >
            <button
              type="button"
              onClick={() => select([l.id])}
              className="flex-1 truncate text-left"
              style={{ opacity: hidden ? 0.4 : 1 }}
              title={label(l)}
            >
              {label(l)}
            </button>
            <button type="button" onClick={() => swap(i, i + 1)} title="Bring forward" className="px-1 text-[var(--muted-foreground,#94a3b8)] hover:text-current">↑</button>
            <button type="button" onClick={() => swap(i, i - 1)} title="Send backward" className="px-1 text-[var(--muted-foreground,#94a3b8)] hover:text-current">↓</button>
            <button type="button" onClick={() => toggleHidden(l.id)} title={hidden ? "Show" : "Hide"} className="px-1">{hidden ? "🚫" : "👁"}</button>
            <button type="button" onClick={() => toggleLock(l.id)} title={l.locked ? "Unlock" : "Lock"} className="px-1">{l.locked ? "🔒" : "🔓"}</button>
          </li>
        );
      })}
    </ul>
  );
}
