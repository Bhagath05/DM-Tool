"use client";

/**
 * Command palette (⌘K / Ctrl+K) — navigation, actions, recents, and a direct
 * line to the Marketing Brain.
 *
 * It routes to existing pages and surfaces existing actions; it NEVER executes a
 * consequential action from here. "Ask the Brain" hands your text to the Brain
 * workspace (which runs through the same agent + approval boundary). Actions
 * like "View approvals" or "Create…" only navigate.
 *
 * Implementation: ⌘K/Ctrl+K toggles, Esc closes; substring match across label,
 * keywords, and href; recents persisted per-browser; arrow keys + Enter select.
 */

import { ArrowUpRight, Command, Search, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface CommandEntry {
  label: string;
  href: string;
  group: "Brain" | "Workspace" | "Growth" | "Creative" | "Action" | "Settings";
  keywords: string[];
  description?: string;
}

const ENTRIES: CommandEntry[] = [
  // Brain — the AI-native surface, listed first.
  { label: "Marketing Brain", href: "/ai", group: "Brain", keywords: ["brain", "ai", "ask", "chat", "assistant", "marketing brain"], description: "Ask anything about your marketing" },
  { label: "Marketing Board", href: "/ai/board", group: "Brain", keywords: ["board", "kanban", "workflow", "work", "pipeline", "needs me", "status"], description: "See what the Brain is working on" },
  { label: "Approvals", href: "/ai/approvals", group: "Brain", keywords: ["approvals", "approve", "pending", "review", "consequential", "publish"], description: "Review actions awaiting your decision" },
  // Workspace
  { label: "Overview", href: "/overview", group: "Workspace", keywords: ["home", "dashboard", "today", "start"] },
  { label: "Performance Intelligence", href: "/performance", group: "Workspace", keywords: ["performance", "diagnostics", "upload", "csv"] },
  { label: "AI Coach", href: "/ai-coach", group: "Workspace", keywords: ["coach", "weekly", "plan", "action"] },
  // Growth
  { label: "Campaigns", href: "/campaigns", group: "Growth", keywords: ["calendar", "campaigns"] },
  { label: "Leads", href: "/leads", group: "Growth", keywords: ["leads", "pipeline", "inbox"] },
  { label: "Opportunities", href: "/opportunities", group: "Growth", keywords: ["opportunities", "trends"] },
  { label: "Analytics", href: "/analytics", group: "Growth", keywords: ["analytics", "metrics", "data"] },
  // Creative
  { label: "Content", href: "/content", group: "Creative", keywords: ["content", "social", "posts", "create"] },
  { label: "Ads", href: "/ads", group: "Creative", keywords: ["ads", "meta", "google", "create"] },
  { label: "Visuals", href: "/visuals", group: "Creative", keywords: ["visuals", "images", "design"] },
  { label: "Library", href: "/library", group: "Creative", keywords: ["library", "history", "saved"] },
  // Actions (navigation to existing create/review surfaces — never executes).
  { label: "Create a social post", href: "/create/social-posts", group: "Action", keywords: ["create", "new", "post", "social", "write"] },
  { label: "Create an ad", href: "/create/ads", group: "Action", keywords: ["create", "new", "ad", "ads"] },
  { label: "Create a campaign", href: "/campaigns", group: "Action", keywords: ["create", "new", "campaign", "launch"] },
  { label: "Create a visual", href: "/create/creatives", group: "Action", keywords: ["create", "new", "visual", "image", "design"] },
  // Settings
  { label: "Organization", href: "/settings/organization", group: "Settings", keywords: ["organization", "workspace", "company", "profile", "industry", "timezone"] },
  { label: "Team", href: "/settings/team", group: "Settings", keywords: ["team", "members", "people", "invite", "roles", "permissions"] },
  { label: "Billing", href: "/settings/billing", group: "Settings", keywords: ["billing", "subscription", "invoice", "plan", "upgrade"] },
  { label: "Integrations", href: "/settings/integrations", group: "Settings", keywords: ["integrations", "connect", "meta", "google", "linkedin", "tiktok", "hubspot", "salesforce", "connectors"] },
  { label: "Notifications", href: "/settings/notifications", group: "Settings", keywords: ["notifications", "alerts", "email", "preferences", "digest"] },
  { label: "Security", href: "/settings/security", group: "Settings", keywords: ["security", "password", "mfa", "sessions", "login", "audit"] },
  { label: "Usage & Limits", href: "/settings/usage", group: "Settings", keywords: ["usage", "limits", "quota", "plan", "metrics"] },
];

const RECENTS_KEY = "aicmo.palette.recents.v1";
const MAX_RECENTS = 4;

function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform);
}

function useIsMac(): boolean | null {
  const [mac, setMac] = useState<boolean | null>(null);
  useEffect(() => {
    setMac(isMac());
  }, []);
  return mac;
}

function shortcutLabel(mac: boolean | null): string {
  return mac ? "⌘K" : "Ctrl K";
}

function readRecents(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENTS_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function pushRecent(href: string) {
  try {
    const next = [href, ...readRecents().filter((h) => h !== href)].slice(0, MAX_RECENTS);
    window.localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
  } catch {
    /* best effort */
  }
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setRecents(readRecents());
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    setQuery("");
    setActiveIndex(0);
  }, [open]);

  const trimmed = query.trim();
  const filtered = useMemo(() => filterEntries(ENTRIES, query), [query]);

  // Memoized so arrow-key handlers don't re-create every render.
  const { results, askEntry, recentEntries } = useMemo(() => {
    // "Ask the Brain" — a dynamic first result that hands the query to the Brain.
    const ask: CommandEntry | null = trimmed
      ? {
          label: `Ask the Brain: “${trimmed}”`,
          href: `/ai?q=${encodeURIComponent(trimmed)}`,
          group: "Brain",
          keywords: [],
          description: "Open the Marketing Brain with this question",
        }
      : null;
    // Recents (only when not searching), resolved to known entries.
    const resolvedRecents: CommandEntry[] = trimmed
      ? []
      : recents
          .map((href) => ENTRIES.find((e) => e.href === href))
          .filter((e): e is CommandEntry => Boolean(e));
    return {
      askEntry: ask,
      recentEntries: resolvedRecents,
      results: [...(ask ? [ask] : []), ...resolvedRecents, ...filtered],
    };
  }, [trimmed, filtered, recents]);

  const onSelect = useCallback(
    (entry: CommandEntry) => {
      setOpen(false);
      // Persist a real destination as a recent (skip the dynamic ask entry).
      if (!entry.href.startsWith("/ai?q=")) pushRecent(entry.href);
      router.push(entry.href as never);
    },
    [router],
  );

  const onInputKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const entry = results[activeIndex];
        if (entry) onSelect(entry);
      }
    },
    [activeIndex, results, onSelect],
  );

  if (!open) return null;

  // Build grouped sections in a stable order; "Recent" is synthetic.
  const sections: { title: string; items: CommandEntry[] }[] = [];
  if (askEntry) sections.push({ title: "Marketing Brain", items: [askEntry] });
  if (recentEntries.length > 0) sections.push({ title: "Recent", items: recentEntries });
  const groupOrder: CommandEntry["group"][] = [
    "Brain",
    "Workspace",
    "Growth",
    "Creative",
    "Action",
    "Settings",
  ];
  for (const g of groupOrder) {
    const items = filtered.filter((e) => e.group === g);
    if (items.length > 0) sections.push({ title: g === "Brain" ? "Marketing Brain" : g, items });
  }

  return (
    <div
      data-testid="command-palette"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/40 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-card shadow-lg">
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onInputKey}
            placeholder="Search, jump to a page, or ask the Brain…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            data-testid="command-palette-input"
          />
          <span className="hidden items-center gap-0.5 rounded-md border border-border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline-flex">
            esc
          </span>
        </div>
        <div className="max-h-80 overflow-y-auto py-1" data-testid="command-palette-results">
          {results.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No matches. Try a different word.
            </div>
          ) : (
            sections.map(({ title, items }) => (
              <div key={title} className="py-1.5">
                <div className="px-4 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {title}
                </div>
                {items.map((entry) => {
                  const idx = results.indexOf(entry);
                  const active = idx === activeIndex;
                  const isAsk = entry.href.startsWith("/ai?q=");
                  return (
                    <button
                      key={`${title}-${entry.href}`}
                      type="button"
                      data-testid={
                        isAsk ? "command-ask-brain" : `command-result-${entry.href.slice(1) || "root"}`
                      }
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => onSelect(entry)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-4 py-2 text-sm transition-colors",
                        active
                          ? "bg-ai-soft text-foreground"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <span className="flex items-center gap-2 text-left">
                        {isAsk && <Sparkles className="h-3.5 w-3.5 shrink-0 text-ai" aria-hidden />}
                        <span className="flex flex-col">
                          <span className="font-medium text-foreground">{entry.label}</span>
                          {entry.description && (
                            <span className="text-xs text-muted-foreground">{entry.description}</span>
                          )}
                        </span>
                      </span>
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-border bg-muted/40 px-4 py-2 text-[10px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Command className="h-3 w-3" />
            <span>Tip: press </span>
            <kbd className="rounded border border-border bg-card px-1 py-0.5 font-mono">
              {isMac() ? "⌘K" : "Ctrl K"}
            </kbd>
            <span>anywhere.</span>
          </span>
          <span>↑↓ to move · ↵ to open</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Pure filter (exported for tests)
// ---------------------------------------------------------------------

export function filterEntries(
  entries: CommandEntry[],
  query: string,
): CommandEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return entries;
  return entries.filter((e) => {
    const hay = [e.label, e.group, ...e.keywords, e.href]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}

// Topbar trigger button — keeps the keyboard shortcut visible.
export function CommandPaletteTrigger() {
  const mac = useIsMac();
  const onClick = useCallback(() => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "k",
        metaKey: isMac(),
        ctrlKey: !isMac(),
      }),
    );
  }, []);

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="command-palette-trigger"
      className="hidden h-9 items-center gap-2 rounded-lg border border-border bg-card px-3 text-xs text-muted-foreground transition-colors hover:border-ai-border hover:text-foreground sm:inline-flex"
    >
      <Search className="h-3.5 w-3.5" />
      <span>Search…</span>
      <span
        suppressHydrationWarning
        className="ml-3 inline-flex items-center gap-0.5 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium"
      >
        {shortcutLabel(mac)}
      </span>
    </button>
  );
}
