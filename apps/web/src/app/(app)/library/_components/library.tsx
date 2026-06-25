"use client";

import {
  FileText,
  Image as ImageIcon,
  Loader2,
  Megaphone,
  Package,
  Sparkles,
  Video,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ApiError,
  api,
  type CampaignBundle,
  type GeneratedAd,
  type GeneratedContent,
  type GeneratedVisual,
  type LandingPage,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Unified Library — every generated asset, one timeline.
 *
 * Why frontend-only aggregation: the platform already exposes per-type
 * list endpoints that paginate and authorise correctly. Re-merging them
 * server-side would force a new schema for marginal benefit. Five
 * parallel fetches + a sort gets us there in a single page load.
 *
 * Item shape is intentionally lossy — we don't try to render every
 * field of every type inline. The card shows enough to ID the piece;
 * clicking lands you on the studio that owns it where the full result-
 * card already exists.
 *
 * Visuals get a special path: we fetch their renders in parallel so the
 * thumbnail shows the actual PNG, not just a strategy blurb.
 */

type Kind = "content" | "ad" | "visual" | "landing_page" | "bundle";

type LibraryItem = {
  id: string;
  kind: Kind;
  subtype: string; // social_post | reel | ad_type | visual_type | …
  title: string;
  subtitle: string;
  platform: string | null;
  goal: string | null;
  createdAt: string;
  href: string;
  thumbnailUrl?: string;
  // Used for the type-filter chips. Reels are a sub-kind of content but
  // get their own chip because that's how users think about them.
  filterKey: Kind | "reel";
};

const FILTERS: {
  key: Kind | "reel" | "all";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { key: "all", label: "Everything", icon: Sparkles },
  { key: "content", label: "Posts", icon: FileText },
  { key: "reel", label: "Reels", icon: Video },
  { key: "ad", label: "Ads", icon: Megaphone },
  { key: "visual", label: "Visuals", icon: ImageIcon },
  { key: "landing_page", label: "Lead pages", icon: FileText },
  { key: "bundle", label: "Bundles", icon: Package },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; items: LibraryItem[] }
  | { kind: "error"; message: string };

export function Library() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [contentRes, adsRes, visualsRes, landingRes, bundlesRes] =
        await Promise.allSettled([
          api.content.list({ limit: 50 }),
          api.ads.list({ limit: 50 }),
          api.visuals.list({ limit: 50 }),
          api.landingPages.list(),
          api.bundles.list(50),
        ]);

      const items: LibraryItem[] = [];

      if (contentRes.status === "fulfilled") {
        for (const c of contentRes.value) items.push(contentToItem(c));
      }
      if (adsRes.status === "fulfilled") {
        for (const a of adsRes.value) items.push(adToItem(a));
      }
      if (landingRes.status === "fulfilled") {
        for (const p of landingRes.value) items.push(landingToItem(p));
      }
      if (bundlesRes.status === "fulfilled") {
        for (const b of bundlesRes.value) items.push(bundleToItem(b));
      }

      // Visuals + ads: list endpoints now include thumbnail URLs.
      if (visualsRes.status === "fulfilled") {
        for (const v of visualsRes.value) {
          items.push(visualToItem(v));
        }
      }

      items.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));
      setState({ kind: "ready", items });
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof ApiError
            ? e.message
            : "Couldn't load the library — try again in a moment.",
      });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredItems = useMemo(() => {
    if (state.kind !== "ready") return [];
    if (filter === "all") return state.items;
    return state.items.filter((i) => i.filterKey === filter);
  }, [filter, state]);

  const counts = useMemo(() => {
    if (state.kind !== "ready") return {} as Record<string, number>;
    const m: Record<string, number> = { all: state.items.length };
    for (const i of state.items) {
      m[i.filterKey] = (m[i.filterKey] ?? 0) + 1;
    }
    return m;
  }, [state]);

  if (state.kind === "loading") {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Pulling everything together…
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          {state.message}
          <Button
            variant="outline"
            size="sm"
            className="ml-3"
            onClick={() => void load()}
          >
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {/* Filter chips. Always visible — communicates the full taxonomy. */}
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => {
          const Icon = f.icon;
          const count = counts[f.key] ?? 0;
          const isActive = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
                isActive
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-card text-muted-foreground hover:bg-muted",
              )}
            >
              <Icon className="h-3 w-3" />
              {f.label}
              {count > 0 && (
                <span
                  className={cn(
                    "rounded px-1 font-mono text-[10px]",
                    isActive
                      ? "bg-background/20 text-background"
                      : "text-muted-foreground/70",
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {filteredItems.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Nothing here yet. Head to any studio and generate something — it&apos;ll
            show up here automatically.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filteredItems.map((item) => (
            <LibraryCard key={`${item.kind}:${item.id}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
//  Card
// ---------------------------------------------------------------------

function LibraryCard({ item }: { item: LibraryItem }) {
  const created = item.createdAt.slice(0, 10);
  return (
    <Link
      href={item.href as never}
      className="group block overflow-hidden rounded-lg border bg-card transition-colors hover:border-foreground/20 hover:bg-card/80"
    >
      <div className="relative aspect-video w-full overflow-hidden bg-muted">
        {item.thumbnailUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnailUrl}
            alt={item.title}
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
          />
        ) : (
          <PlaceholderArt kind={item.filterKey} />
        )}
        <span className="absolute left-2 top-2 rounded bg-background/85 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-foreground/80 backdrop-blur">
          {item.subtype.replace(/_/g, " ")}
        </span>
      </div>
      <div className="space-y-1.5 p-3">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
          {item.platform && <span>{item.platform}</span>}
          {item.platform && item.goal && <span>·</span>}
          {item.goal && <span className="truncate">{item.goal}</span>}
        </div>
        <p className="line-clamp-2 text-sm font-medium leading-snug">
          {item.title}
        </p>
        {item.subtitle && (
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {item.subtitle}
          </p>
        )}
        <p className="pt-1 font-mono text-[10px] text-muted-foreground/70">
          {created}
        </p>
      </div>
    </Link>
  );
}

function PlaceholderArt({ kind }: { kind: LibraryItem["filterKey"] }) {
  const Icon =
    kind === "content"
      ? FileText
      : kind === "reel"
        ? Video
        : kind === "ad"
          ? Megaphone
          : kind === "visual"
            ? ImageIcon
            : kind === "bundle"
              ? Package
              : FileText;
  return (
    <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-muted to-muted/40">
      <Icon className="h-8 w-8 text-muted-foreground/40" />
    </div>
  );
}

// ---------------------------------------------------------------------
//  Per-kind normalisers
// ---------------------------------------------------------------------

function contentToItem(c: GeneratedContent): LibraryItem {
  const out = c.output as Record<string, unknown>;
  const title =
    pickString(out, "hook") ??
    pickString(out, "headline") ??
    pickString(out, "body")?.slice(0, 80) ??
    `${c.content_type} for ${c.platform}`;
  const subtitle =
    pickString(out, "body")?.slice(0, 140) ??
    pickString(out, "hook") ??
    "";
  return {
    id: c.id,
    kind: "content",
    subtype: c.content_type,
    filterKey: c.content_type === "reel" ? "reel" : "content",
    title,
    subtitle,
    platform: c.platform,
    goal: c.goal,
    createdAt: c.created_at,
    href: "/content",
  };
}

function adToItem(a: GeneratedAd): LibraryItem {
  const out = a.output as Record<string, unknown>;
  const title =
    pickString(out, "primary_text")?.slice(0, 80) ??
    pickString(out, "headline") ??
    `${a.ad_type} ad on ${a.platform}`;
  const subtitle =
    pickString(out, "description") ??
    pickString(out, "headline") ??
    "";
  const thumbnailUrl = a.primary_image_url
    ? absoluteMediaUrl(a.primary_image_url)
    : undefined;
  return {
    id: a.id,
    kind: "ad",
    subtype: a.ad_type,
    filterKey: "ad",
    title,
    subtitle,
    platform: a.platform,
    goal: a.goal,
    createdAt: a.created_at,
    href: "/ads",
    thumbnailUrl,
  };
}

function visualToItem(v: GeneratedVisual): LibraryItem {
  const title =
    v.strategy?.visual_concept ?? `${v.visual_type} for ${v.platform}`;
  const subtitle = v.strategy?.audience_angle ?? "";
  const thumb = v.thumbnail_url ?? v.primary_signed_url;
  const thumbnailUrl = thumb ? absoluteMediaUrl(thumb) : undefined;
  return {
    id: v.id,
    kind: "visual",
    subtype: v.visual_type,
    filterKey: "visual",
    title,
    subtitle,
    platform: v.platform,
    goal: v.goal,
    createdAt: v.created_at,
    href: "/visuals",
    thumbnailUrl,
  };
}

function landingToItem(p: LandingPage): LibraryItem {
  return {
    id: p.id,
    kind: "landing_page",
    subtype: p.status,
    filterKey: "landing_page",
    title: p.title,
    subtitle: p.content?.headline ?? "",
    platform: null,
    goal: null,
    createdAt: p.created_at,
    href: `/landing-pages/${p.id}`,
  };
}

function bundleToItem(b: CampaignBundle): LibraryItem {
  return {
    id: b.id,
    kind: "bundle",
    subtype: b.objective,
    filterKey: "bundle",
    title: b.theme,
    subtitle: `${b.pieces.length} piece${b.pieces.length === 1 ? "" : "s"} · ${b.duration_days}-day plan`,
    platform: null,
    goal: b.objective,
    createdAt: b.created_at,
    href: "/bundles",
  };
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function pickString(obj: Record<string, unknown>, key: string): string | null {
  const v = obj?.[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

function absoluteMediaUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path}`;
}
