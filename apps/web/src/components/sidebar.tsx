"use client";

/**
 * Phase 6.1 — outcome-oriented sidebar aligned to the real App Router.
 * Phase 6.6 — quieted to be visually secondary to the workspace, and made
 * collapsible to an icon rail on desktop.
 *
 * Every destination below points at a real, canonical route (verified against
 * the route tree). Legacy/dead targets were removed; where old cards still
 * deep-link to a legacy path, that path is a redirect shim (not a nav item).
 *
 *   TODAY           → Today's Plan, Needs Approval
 *   GROW            → Leads, Opportunities, CRM, Market Intelligence
 *   CREATE          → Creative Studio, Publishing
 *   MARKETING BRAIN → Marketing Brain (/ai)
 *   MEASURE         → Measure (/analytics; Performance/Social/Lab/History are tabs)
 *   SETTINGS        → Workspace
 *
 * Marketing Brain is the ONE AI destination (Phase 6.3). Its capabilities —
 * Business (brand-brain), Knowledge (beliefs), Decisions (ai-coach), Board —
 * are tabs inside /ai (BrainTabs), not competing nav items. The legacy
 * ai-employee operational composer stays reachable by direct URL only.
 *
 * Shell behavior:
 *   - collapsible groups with localStorage persistence (expanded state)
 *   - desktop icon-rail collapse (persisted) — labels become tooltips
 *   - mobile drawer with overlay
 *   - a quiet active-route treatment (soft, not an inverted pill) so the
 *     sidebar never competes with the content for attention
 */

import {
  BarChart3,
  ChevronDown,
  Clapperboard,
  Compass,
  Handshake,
  Inbox,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  Send,
  Menu,
  Settings as SettingsIcon,
  ShieldCheck,
  Sparkles,
  Sun,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavGroup {
  key: string;
  label: string;
  items: NavItem[];
  defaultOpen?: boolean;
}

// ---------------------------------------------------------------------
//  Primary navigation — every target is a real, canonical route.
// ---------------------------------------------------------------------
//
// Regression-pinned by sidebar.test.tsx: every href here must resolve to a
// real route (no dead links) and the set must match the approved IA.

const PRIMARY_NAV: NavGroup[] = [
  {
    key: "today",
    label: "Today",
    defaultOpen: true,
    items: [
      { href: "/today", label: "Today's Plan", icon: Sun },
      { href: "/ai/approvals", label: "Needs Approval", icon: ShieldCheck },
    ],
  },
  {
    key: "grow",
    label: "Grow",
    defaultOpen: true,
    items: [
      { href: "/leads", label: "Leads", icon: Inbox },
      { href: "/opportunities", label: "Opportunities", icon: Compass },
      { href: "/crm", label: "CRM", icon: Handshake },
      { href: "/grow/market-intelligence", label: "Market Intelligence", icon: Radar },
    ],
  },
  {
    key: "create",
    label: "Create",
    defaultOpen: true,
    items: [
      { href: "/studio", label: "Creative Studio", icon: Clapperboard },
      { href: "/publishing", label: "Publishing", icon: Send },
    ],
  },
  {
    // The one canonical AI destination. Business / Knowledge / Decisions /
    // Board are capabilities WITHIN the Brain (BrainTabs), not separate nav
    // items — so AI Coach / AI Employee / Brand Brain never read as competing
    // products.
    key: "brain",
    label: "Marketing Brain",
    defaultOpen: true,
    items: [
      { href: "/ai", label: "Marketing Brain", icon: Sparkles },
    ],
  },
  {
    // One canonical Measure destination (/analytics). Performance, Social,
    // Learning Lab and History are capabilities WITHIN Measure (MeasureTabs),
    // not competing nav items. Library (saved assets) lives in the command
    // palette. External market trends live under Grow, not Measure.
    key: "measure",
    label: "Measure",
    defaultOpen: true,
    items: [
      { href: "/analytics", label: "Measure", icon: BarChart3 },
    ],
  },
  {
    // Settings collapses to ONE top-level link. Sub-pages (Organization,
    // Team, Billing, Integrations, Notifications, Security, Usage) live in
    // the in-page settings sub-nav.
    key: "settings",
    label: "Settings",
    defaultOpen: true,
    items: [
      { href: "/settings", label: "Workspace", icon: SettingsIcon },
    ],
  },
];

const COLLAPSE_STORAGE_KEY = "aicmo.sidebar.collapse.v1";
const RAIL_STORAGE_KEY = "aicmo.sidebar.rail.v1";

export function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [rail, setRail] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    return PRIMARY_NAV.reduce<Record<string, boolean>>((acc, g) => {
      if (g.defaultOpen === false) acc[g.key] = true;
      return acc;
    }, {});
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(COLLAPSE_STORAGE_KEY);
      if (raw) setCollapsed(JSON.parse(raw));
    } catch {
      /* ignore corrupt cache */
    }
    try {
      setRail(window.localStorage.getItem(RAIL_STORAGE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  const toggleGroup = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        window.localStorage.setItem(
          COLLAPSE_STORAGE_KEY,
          JSON.stringify(next),
        );
      } catch {
        /* best effort */
      }
      return next;
    });
  }, []);

  const toggleRail = useCallback(() => {
    setRail((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(RAIL_STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* best effort */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      <button
        type="button"
        aria-label="Open navigation"
        data-testid="sidebar-mobile-trigger"
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-3 z-30 inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-foreground shadow-sm md:hidden"
      >
        <Menu className="h-4 w-4" />
      </button>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-foreground/40 backdrop-blur-sm md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <aside
        data-testid="sidebar"
        data-rail={rail ? "true" : "false"}
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-card/60",
          "fixed inset-y-0 left-0 z-50 w-64 transform transition-[transform,width] duration-200 ease-out md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          rail && "md:w-[4.5rem]",
        )}
      >
        <SidebarHeader
          rail={rail}
          onClose={() => setMobileOpen(false)}
          onToggleRail={toggleRail}
        />
        <nav
          className="scrollbar-clean flex-1 overflow-y-auto px-3 pb-2 pt-3"
          data-testid="sidebar-nav"
        >
          {PRIMARY_NAV.map((group) => (
            <NavGroupBlock
              key={group.key}
              group={group}
              pathname={pathname}
              rail={rail}
              collapsed={!!collapsed[group.key]}
              onToggle={() => toggleGroup(group.key)}
            />
          ))}
        </nav>
        <SidebarFooter rail={rail} />
      </aside>
    </>
  );
}

function SidebarHeader({
  rail,
  onClose,
  onToggleRail,
}: {
  rail: boolean;
  onClose: () => void;
  onToggleRail: () => void;
}) {
  return (
    <div
      className={cn(
        "flex h-14 shrink-0 items-center gap-2 border-b border-border px-5",
        rail && "md:justify-center md:px-0",
      )}
    >
      <div
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-ai text-ai-foreground shadow-sm"
        aria-hidden
      >
        <Sparkles className="h-4 w-4" />
      </div>
      <span className={cn("text-sm font-semibold tracking-tight", rail && "md:hidden")}>
        DM Tool
      </span>
      {/* Desktop rail toggle — keeps the sidebar quiet and out of the way. */}
      <button
        type="button"
        aria-label={rail ? "Expand sidebar" : "Collapse sidebar"}
        aria-pressed={rail}
        onClick={onToggleRail}
        data-testid="sidebar-rail-toggle"
        className={cn(
          "ml-auto hidden h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:inline-flex",
          rail && "md:ml-0",
        )}
      >
        {rail ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
      </button>
      <button
        type="button"
        aria-label="Close navigation"
        onClick={onClose}
        className="ml-auto inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function NavGroupBlock({
  group,
  pathname,
  rail,
  collapsed,
  onToggle,
}: {
  group: NavGroup;
  pathname: string;
  rail: boolean;
  collapsed: boolean;
  onToggle: () => void;
}) {
  // In rail mode the group header is pointless (no room for a label), so
  // hide it on desktop and always show the items as an icon stack.
  const itemsHidden = collapsed && !rail;
  return (
    <div
      className="mb-3 last:mb-0"
      data-testid={`sidebar-group-${group.key}`}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        className={cn(
          "group flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70 transition-colors hover:text-foreground",
          rail && "md:hidden",
        )}
        data-testid={`sidebar-group-toggle-${group.key}`}
      >
        <span>{group.label}</span>
        <ChevronDown
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            collapsed && "-rotate-90",
          )}
        />
      </button>
      <ul className={cn("mt-0.5 space-y-0.5", itemsHidden && "hidden")}>
        {group.items.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} rail={rail} />
        ))}
      </ul>
    </div>
  );
}

function NavLink({
  item,
  pathname,
  rail,
}: {
  item: NavItem;
  pathname: string;
  rail: boolean;
}) {
  const Icon = item.icon;
  const active =
    pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <li>
      <Link
        href={item.href as never}
        aria-label={item.label}
        aria-current={active ? "page" : undefined}
        title={rail ? item.label : undefined}
        data-testid={`sidebar-item-${item.href.slice(1) || "root"}`}
        className={cn(
          "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200",
          rail && "md:justify-center md:px-0",
          active
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
        )}
      >
        {/* Quiet active indicator — a thin AI accent bar, not an inverted
            pill, so the sidebar stays secondary to the content. */}
        {active && (
          <span
            aria-hidden
            className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-ai"
          />
        )}
        <Icon
          className={cn(
            "h-4 w-4 shrink-0 transition-colors",
            active ? "text-ai" : "text-muted-foreground group-hover:text-foreground",
          )}
        />
        <span className={cn("truncate", rail && "md:hidden")}>{item.label}</span>
      </Link>
    </li>
  );
}

function SidebarFooter({ rail }: { rail: boolean }) {
  const tenant = useTenant();
  const initials = makeInitials(
    tenant.user?.display_name ?? tenant.user?.email ?? "?",
  );
  const orgName =
    tenant.activeOrg?.name ?? tenant.memberships?.[0]?.organization.name ?? null;
  const brandName = tenant.activeBrand?.name ?? null;

  return (
    <div
      data-testid="sidebar-footer"
      className={cn(
        "shrink-0 border-t border-border bg-muted/20 px-3 py-3",
        rail && "md:px-2",
      )}
    >
      {/* Theme control for small screens, where the topbar toggle is hidden
          to protect the 375px layout. sm:hidden is the exact complement of
          the topbar control (hidden sm:inline-flex) — no desktop duplication. */}
      <div className="mb-2 flex justify-center sm:hidden">
        <ThemeToggle />
      </div>
      <Link
        href="/settings/billing"
        className={cn(
          "flex items-center gap-3 rounded-lg p-2 transition-colors hover:bg-muted",
          rail && "md:justify-center md:p-1",
        )}
      >
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ai/15 text-xs font-semibold uppercase tracking-wide text-ai"
          aria-hidden
        >
          {initials}
        </span>
        <div className={cn("flex min-w-0 flex-1 flex-col", rail && "md:hidden")}>
          <span className="truncate text-xs font-semibold text-foreground">
            {tenant.user?.display_name ?? tenant.user?.email ?? "Workspace"}
          </span>
          {orgName && (
            <span className="truncate text-[11px] text-muted-foreground">
              {orgName}
              {brandName && ` · ${brandName}`}
            </span>
          )}
        </div>
      </Link>
      <div
        className={cn(
          "mt-2 flex items-center justify-between rounded-lg border border-ai-border/60 bg-ai-soft/60 px-3 py-1.5",
          rail && "md:hidden",
        )}
      >
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ai-soft-foreground">
          Plan
        </span>
        <span className="text-xs font-medium text-ai-soft-foreground">
          Early Access
        </span>
      </div>
    </div>
  );
}

function makeInitials(s: string): string {
  const t = s.trim();
  if (!t) return "?";
  if (t.includes("@")) return t[0].toUpperCase();
  const parts = t.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
