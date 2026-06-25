"use client";

/**
 * Phase 10.0 — Command palette (⌘K / Ctrl+K).
 *
 * Lightweight nav-only search. Indexes the static route map below.
 * No backend search yet — this is purely a "jump to anything" surface,
 * which is the table-stakes premium-SaaS expectation.
 *
 * Implementation choices:
 *   - Keyboard trigger: ⌘K (mac) / Ctrl+K (everyone else). Esc to close.
 *   - Fuzzy-ish match: substring (case-insensitive) across label,
 *     keywords, and href. Cheap and predictable; a real fuzzy library
 *     would be over-engineered for ~20 routes.
 *   - Focus trap is implicit via `<dialog>` semantics — the input
 *     receives focus on open.
 *   - Built on browser primitives, no headless-ui dependency.
 */

import { ArrowUpRight, Command, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface CommandEntry {
  label: string;
  href: string;
  group: "Workspace" | "Growth" | "Creative" | "Settings" | "Action";
  keywords: string[];
  description?: string;
}

const ENTRIES: CommandEntry[] = [
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
  // Settings
  { label: "Organization", href: "/settings/organization", group: "Settings", keywords: ["organization", "workspace", "company", "profile", "industry", "timezone"] },
  { label: "Team", href: "/settings/team", group: "Settings", keywords: ["team", "members", "people", "invite", "roles", "permissions"] },
  { label: "Billing", href: "/settings/billing", group: "Settings", keywords: ["billing", "subscription", "invoice", "plan", "upgrade"] },
  { label: "Integrations", href: "/settings/integrations", group: "Settings", keywords: ["integrations", "connect", "meta", "google", "linkedin", "tiktok", "hubspot", "salesforce", "connectors"] },
  { label: "Notifications", href: "/settings/notifications", group: "Settings", keywords: ["notifications", "alerts", "email", "preferences", "digest"] },
  { label: "Security", href: "/settings/security", group: "Settings", keywords: ["security", "password", "mfa", "sessions", "login", "audit"] },
  { label: "Usage & Limits", href: "/settings/usage", group: "Settings", keywords: ["usage", "limits", "quota", "plan", "metrics"] },
];

function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad/.test(navigator.platform);
}

/**
 * `isMac()` reads `navigator.platform`, which is undefined during SSR.
 * Rendering its result during first paint causes a hydration mismatch
 * (server: "Ctrl K" → client: "⌘K" on Mac users). This hook returns
 * `null` until the client has hydrated, then the real value — letting
 * the caller render a stable placeholder for the first paint.
 */
function useIsMac(): boolean | null {
  const [mac, setMac] = useState<boolean | null>(null);
  useEffect(() => {
    setMac(isMac());
  }, []);
  return mac;
}

function shortcutLabel(mac: boolean | null): string {
  // Default to the more common case (Ctrl K) when we don't yet know
  // the platform. The label flips silently after hydration on Macs.
  return mac ? "⌘K" : "Ctrl K";
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Global keyboard handler — ⌘K / Ctrl+K to toggle, Esc to close.
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

  // Focus the input on open. Clear query on close.
  useEffect(() => {
    if (open) {
      // Run on next tick so the input is mounted.
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    setQuery("");
    setActiveIndex(0);
  }, [open]);

  const filtered = useMemo(() => filterEntries(ENTRIES, query), [query]);

  const onSelect = useCallback(
    (entry: CommandEntry) => {
      setOpen(false);
      router.push(entry.href as never);
    },
    [router],
  );

  // Arrow-key navigation within the result list.
  const onInputKey = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const entry = filtered[activeIndex];
        if (entry) onSelect(entry);
      }
    },
    [activeIndex, filtered, onSelect],
  );

  if (!open) return null;

  // Group results for the dropdown.
  const groupOrder: CommandEntry["group"][] = [
    "Workspace",
    "Growth",
    "Creative",
    "Settings",
    "Action",
  ];
  const grouped = groupOrder
    .map((g) => ({ group: g, items: filtered.filter((e) => e.group === g) }))
    .filter((g) => g.items.length > 0);

  return (
    <div
      data-testid="command-palette"
      role="dialog"
      aria-modal="true"
      aria-label="Search"
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
            placeholder="Jump to a page…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            data-testid="command-palette-input"
          />
          <span className="hidden items-center gap-0.5 rounded-md border border-border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:inline-flex">
            esc
          </span>
        </div>
        <div
          className="max-h-80 overflow-y-auto py-1"
          data-testid="command-palette-results"
        >
          {filtered.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No matches. Try a different word.
            </div>
          ) : (
            grouped.map(({ group, items }) => (
              <div key={group} className="py-1.5">
                <div className="px-4 pb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {group}
                </div>
                {items.map((entry) => {
                  const idx = filtered.indexOf(entry);
                  const active = idx === activeIndex;
                  return (
                    <button
                      key={entry.href}
                      type="button"
                      data-testid={`command-result-${entry.href.slice(1) || "root"}`}
                      onMouseEnter={() => setActiveIndex(idx)}
                      onClick={() => onSelect(entry)}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-4 py-2 text-sm transition-colors",
                        active
                          ? "bg-ai-soft text-foreground"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <span className="flex flex-col text-left">
                        <span className="font-medium text-foreground">
                          {entry.label}
                        </span>
                        {entry.description && (
                          <span className="text-xs text-muted-foreground">
                            {entry.description}
                          </span>
                        )}
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
            <span>anywhere to open this.</span>
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
      {/* `suppressHydrationWarning` covers the case where a Mac user
          briefly sees "Ctrl K" before useEffect upgrades the label.
          The fallback is correct (stays "Ctrl K") on non-Mac. */}
      <span
        suppressHydrationWarning
        className="ml-3 inline-flex items-center gap-0.5 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium"
      >
        {shortcutLabel(mac)}
      </span>
    </button>
  );
}
