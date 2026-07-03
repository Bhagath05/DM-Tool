"use client";

/**
 * Phase 6.2 Part 3 — Content Library (enterprise workspace).
 *
 * A real library over the EXISTING content API (list / setSaved / delete) — no
 * new services, no fabricated data. Delivers: search, content-type + favourites
 * filters, grid/list toggle, pagination, favourite, copy, download/export, delete,
 * and per-asset word/character counters + client-side SEO & readability scores,
 * with loading / empty / error states. Design system reused throughout.
 */

import {
  Copy,
  Download,
  FileText,
  FolderPlus,
  Grid2x2,
  List,
  Search,
  Settings2,
  Star,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, type PillTone } from "@/components/ui/status-pill";
import { Surface } from "@/components/ui/surface";
import {
  api,
  CONTENT_TYPES,
  REVIEW_STATUSES,
  type ContentFolder,
  type ContentType,
  type GeneratedContent,
  type ReviewStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { ContentOpsPanel } from "./content-ops-panel";

const PAGE_SIZE = 12;

const STATUS_TONE: Record<ReviewStatus, PillTone> = {
  draft: "neutral",
  in_review: "watch",
  changes_requested: "watch",
  approved: "good",
  rejected: "bad",
  published: "good",
  archived: "muted",
};

// ---- text + scoring helpers (client-side, over the real output dict) ----

function flattenText(v: unknown, out: string[] = []): string[] {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => flattenText(x, out));
  else if (v && typeof v === "object")
    Object.values(v as Record<string, unknown>).forEach((x) => flattenText(x, out));
  return out;
}

function assetText(c: GeneratedContent): string {
  return flattenText(c.output).join(" ").replace(/\s+/g, " ").trim();
}

function counts(text: string) {
  const words = text ? text.split(/\s+/).filter(Boolean).length : 0;
  return { words, chars: text.length };
}

// Flesch Reading Ease approximation → 0-100 (higher = easier).
function readabilityScore(text: string): number | null {
  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0).length;
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length < 20 || sentences === 0) return null;
  const syll = words.reduce(
    (n, w) => n + Math.max(1, (w.toLowerCase().match(/[aeiouy]+/g) || []).length),
    0,
  );
  const score = 206.835 - 1.015 * (words.length / sentences) - 84.6 * (syll / words.length);
  return Math.max(0, Math.min(100, Math.round(score)));
}

// Lightweight SEO heuristic over the output structure.
function seoScore(c: GeneratedContent, text: string): number {
  const o = c.output as Record<string, unknown>;
  let s = 0;
  if (o.title || o.headline || o.seo_title || o.cover_title) s += 25;
  const meta = String(o.meta_description ?? "");
  if (meta) s += meta.length <= 160 ? 25 : 12;
  if (o.primary_keyword || o.keywords || o.secondary_keywords) s += 25;
  if (o.cta || o.cta_text || o.cta_button) s += 10;
  const wc = text.split(/\s+/).filter(Boolean).length;
  if (wc >= 40) s += 15;
  return Math.min(100, s);
}

function tone(score: number): "good" | "watch" | "bad" {
  return score >= 70 ? "good" : score >= 45 ? "watch" : "bad";
}

function label(ct: string): string {
  return ct.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function download(name: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function ContentLibrary() {
  const [items, setItems] = useState<GeneratedContent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<ContentType | "">("");
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | "">("");
  const [folderFilter, setFolderFilter] = useState<string>("");
  const [savedOnly, setSavedOnly] = useState(false);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [sortNewest, setSortNewest] = useState(true);
  const [page, setPage] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [folders, setFolders] = useState<ContentFolder[]>([]);
  const [managing, setManaging] = useState<GeneratedContent | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await api.content.list({
        content_type: typeFilter || undefined,
        saved_only: savedOnly || undefined,
        limit: 200,
      });
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load content.");
    } finally {
      setLoading(false);
    }
  }, [typeFilter, savedOnly]);

  const loadFolders = useCallback(async () => {
    try {
      setFolders(await api.content.folders());
    } catch {
      /* folders are optional chrome — never block the library */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    setPage(0);
  }, [search, typeFilter, statusFilter, folderFilter, savedOnly, sortNewest]);

  const patchItem = useCallback((updated: GeneratedContent) => {
    setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    setManaging((m) => (m && m.id === updated.id ? updated : m));
  }, []);

  const newFolder = async () => {
    const name = prompt("New folder name")?.trim();
    if (!name) return;
    const folder = await api.content.createFolder(name);
    setFolders((prev) => [...prev, folder]);
  };

  const assignFolder = async (c: GeneratedContent, folderId: string) => {
    const target = folderId || null;
    setBusyId(c.id);
    try {
      await api.content.assignFolder([c.id], target);
      setItems((prev) =>
        prev.map((x) => (x.id === c.id ? { ...x, folder_id: target } : x)),
      );
    } finally {
      setBusyId(null);
    }
  };

  const toggleSaved = async (c: GeneratedContent) => {
    setBusyId(c.id);
    try {
      const updated = await api.content.setSaved(c.id, !c.is_saved);
      setItems((prev) => prev.map((x) => (x.id === c.id ? updated : x)));
    } catch {
      /* surfaced via reload if needed */
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (c: GeneratedContent) => {
    if (!confirm("Delete this asset? This cannot be undone.")) return;
    setBusyId(c.id);
    try {
      await api.content.delete(c.id);
      setItems((prev) => prev.filter((x) => x.id !== c.id));
    } finally {
      setBusyId(null);
    }
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = items;
    if (q) {
      rows = rows.filter(
        (c) =>
          c.goal.toLowerCase().includes(q) ||
          c.platform.toLowerCase().includes(q) ||
          c.content_type.toLowerCase().includes(q) ||
          assetText(c).toLowerCase().includes(q),
      );
    }
    if (statusFilter) rows = rows.filter((c) => c.review_status === statusFilter);
    if (folderFilter)
      rows = rows.filter((c) =>
        folderFilter === "__none__" ? !c.folder_id : c.folder_id === folderFilter,
      );
    return [...rows].sort((a, b) => {
      const cmp = a.created_at.localeCompare(b.created_at);
      return sortNewest ? -cmp : cmp;
    });
  }, [items, search, statusFilter, folderFilter, sortNewest]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const card = (c: GeneratedContent) => {
    const text = assetText(c);
    const { words, chars } = counts(text);
    const seo = seoScore(c, text);
    const read = readabilityScore(text);
    const preview = text.slice(0, view === "grid" ? 160 : 240);
    return (
      <Surface
        key={c.id}
        padding="compact"
        className={cn("flex flex-col gap-2", view === "list" && "sm:flex-row sm:items-start")}
        data-testid="content-library-item"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone="neutral" size="sm">
              {label(c.content_type)}
            </StatusPill>
            <StatusPill tone={STATUS_TONE[c.review_status]} size="sm">
              {label(c.review_status)}
            </StatusPill>
            <span className="text-xs text-muted-foreground">{c.platform}</span>
            {c.is_saved && <Star className="h-3.5 w-3.5 fill-watch text-watch" />}
            <span className="ml-auto text-xs text-muted-foreground">
              {new Date(c.created_at).toLocaleDateString()}
            </span>
          </div>
          <p className="text-sm font-medium">{c.goal}</p>
          <p className="line-clamp-3 text-xs text-muted-foreground">{preview || "—"}</p>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-muted-foreground">
              {words}w · {chars}c
            </span>
            <StatusPill tone={tone(seo)} size="sm">
              SEO {seo}
            </StatusPill>
            {read != null && (
              <StatusPill tone={tone(read)} size="sm">
                Read {read}
              </StatusPill>
            )}
            {folders.length > 0 && (
              <select
                value={c.folder_id ?? ""}
                onChange={(e) => void assignFolder(c, e.target.value)}
                disabled={busyId === c.id}
                className="h-6 rounded border border-input bg-background px-1 text-xs text-muted-foreground"
                title="Folder"
                aria-label="Assign to folder"
                data-testid="content-folder-select"
              >
                <option value="">No folder</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 sm:flex-col">
          <Button
            variant="ghost"
            size="icon"
            title="Manage — edit, versions, review, comments"
            onClick={() => setManaging(c)}
            data-testid="content-manage"
          >
            <Settings2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title={c.is_saved ? "Unfavourite" : "Favourite"}
            disabled={busyId === c.id}
            onClick={() => void toggleSaved(c)}
            data-testid="content-fav"
          >
            <Star className={cn("h-4 w-4", c.is_saved && "fill-watch text-watch")} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Copy text"
            onClick={() => void navigator.clipboard.writeText(text)}
          >
            <Copy className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Download"
            onClick={() => download(`${c.content_type}-${c.id.slice(0, 8)}.txt`, text)}
          >
            <Download className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Delete"
            disabled={busyId === c.id}
            onClick={() => void remove(c)}
          >
            <Trash2 className="h-4 w-4 text-bad" />
          </Button>
        </div>
      </Surface>
    );
  };

  return (
    <div className="space-y-4" data-testid="content-library">
      <SectionHeading
        eyebrow="Content library"
        heading="Every asset you've generated"
        description="Search, filter, favourite, score, and export across all content types."
        action={
          <div className="flex items-center gap-1">
            <Button
              variant={view === "grid" ? "default" : "ghost"}
              size="icon"
              onClick={() => setView("grid")}
              title="Grid"
            >
              <Grid2x2 className="h-4 w-4" />
            </Button>
            <Button
              variant={view === "list" ? "default" : "ghost"}
              size="icon"
              onClick={() => setView("list")}
              title="List"
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search content…"
            className="h-9 w-56 pl-8"
            data-testid="content-search"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as ContentType | "")}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          data-testid="content-type-filter"
        >
          <option value="">All types</option>
          {CONTENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {label(t)}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ReviewStatus | "")}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
          data-testid="content-status-filter"
        >
          <option value="">All statuses</option>
          {REVIEW_STATUSES.map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        {folders.length > 0 && (
          <select
            value={folderFilter}
            onChange={(e) => setFolderFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            data-testid="content-folder-filter"
          >
            <option value="">All folders</option>
            <option value="__none__">No folder</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        )}
        <Button
          variant={savedOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setSavedOnly((s) => !s)}
          data-testid="content-fav-filter"
        >
          <Star className={cn("h-4 w-4", savedOnly && "fill-current")} />
          Favourites
        </Button>
        <Button variant="outline" size="sm" onClick={() => void newFolder()} title="New folder">
          <FolderPlus className="h-4 w-4" />
          Folder
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSortNewest((s) => !s)}
        >
          {sortNewest ? "Newest" : "Oldest"}
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">
          {filtered.length} asset{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Body */}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : error ? (
        <Surface state="bad" padding="compact" className="text-sm text-bad">
          {error}{" "}
          <button className="underline" onClick={() => void load()}>
            Retry
          </button>
        </Surface>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No content yet"
          description="Generate content above — every asset lands here, searchable and scorable."
        />
      ) : (
        <>
          <div
            className={cn(
              view === "grid"
                ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
                : "flex flex-col gap-3",
            )}
          >
            {pageRows.map(card)}
          </div>
          {pageCount > 1 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Page {page + 1} of {pageCount}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {managing && (
        <ContentOpsPanel
          content={managing}
          open={managing != null}
          onOpenChange={(o) => !o && setManaging(null)}
          onChanged={patchItem}
        />
      )}
    </div>
  );
}
