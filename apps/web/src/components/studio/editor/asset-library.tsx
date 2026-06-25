/**
 * AssetLibrary (CS5.1) — the brand asset library: upload, browse, search,
 * favorite, select. Selecting an asset replaces the currently-selected image
 * layer (via the editor store → replace_image EditOp → apply_revision).
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { BrandAsset } from "@/lib/studio-types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KINDS = ["all", "image", "logo", "icon", "color", "font"] as const;

export function assetSrc(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}

export function AssetLibrary({ onSelect }: { onSelect: (a: BrandAsset) => void }) {
  const [assets, setAssets] = useState<BrandAsset[]>([]);
  const [kind, setKind] = useState<string>("all");
  const [q, setQ] = useState("");
  const [favs, setFavs] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const items = await api.studio.brandAssets.list({
        kind: kind === "all" ? undefined : kind,
        q: q.trim() || undefined,
        favorites: favs,
      });
      setAssets(items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load assets.");
    }
  }, [kind, q, favs]);

  useEffect(() => {
    void load();
  }, [load]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      await api.studio.brandAssets.upload(file, "image", file.name);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search assets…"
          className="min-w-0 flex-1 rounded border border-[var(--border,#e2e8f0)] px-2 py-1 text-xs"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1 text-xs"
          aria-label="Asset kind"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setFavs((v) => !v)}
          className="rounded border border-[var(--border,#e2e8f0)] px-1.5 py-1 text-xs"
          style={{ background: favs ? "var(--muted,#fef3c7)" : undefined }}
          title="Favorites only"
        >
          ★
        </button>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="rounded bg-[var(--primary,#2563eb)] px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {busy ? "…" : "Upload"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
            e.target.value = "";
          }}
        />
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {assets.length === 0 ? (
        <p className="text-xs text-[var(--muted-foreground,#94a3b8)]">
          No assets yet — upload a logo or photo.
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-1.5">
          {assets.map((a) => (
            <div key={a.id} className="relative">
              <button
                type="button"
                onClick={() => onSelect(a)}
                className="block aspect-square w-full overflow-hidden rounded border border-[var(--border,#e2e8f0)] hover:border-[var(--primary,#2563eb)]"
                title={a.label ?? a.kind}
              >
                {a.url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={assetSrc(a.url)} alt={a.label ?? a.kind} className="h-full w-full object-cover" />
                ) : (
                  <span className="grid h-full w-full place-items-center text-[10px] text-[var(--muted-foreground,#94a3b8)]">
                    {a.kind}
                  </span>
                )}
              </button>
              <button
                type="button"
                onClick={() => void api.studio.brandAssets.favorite(a.id).then(load)}
                className="absolute right-0.5 top-0.5 text-xs"
                style={{ color: a.is_favorite ? "#f59e0b" : "#cbd5e1" }}
                title={a.is_favorite ? "Unfavorite" : "Favorite"}
              >
                ★
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
