"use client";

/**
 * Phase 10.3 — Founder Simplification Pass sidebar.
 *
 * Outcome-oriented IA: 5 groups, 8 primary items
 * (down from 17 — see docs/phase-10.3-founder-simplification.md).
 *
 *   TODAY    → Today's Plan                  (front door)
 *   GROW     → Leads, Opportunities, Market Intelligence
 *   CREATE   → Social Posts, Ads, Creatives
 *   RESULTS  → Performance
 *   SETTINGS → Workspace
 *
 * Three power-user destinations (Library, Campaign Lab, raw Trends)
 * appear ONLY when the founder flips the topbar Simple↔Pro toggle to
 * "Pro". Same `useViewMode` state that controls technical-details
 * disclosure on every <BusinessMetric> / <AiRecommendation> card
 * (Constitution: Dual-Layer Information System). One toggle, two
 * effects — Pro mode means "I'm a power user; show me more depth AND
 * more destinations." Default = Simple (clean primary nav only).
 *
 * Carries forward the 10.0 polish: animated active-route indicator,
 * collapsible groups with localStorage persistence, mobile drawer,
 * footer with workspace identity + plan.
 */

import {
  BarChart3,
  ChevronDown,
  Clapperboard,
  Compass,
  Contact,
  FlaskConical,
  History,
  Inbox,
  Image as ImageIcon,
  Linkedin,
  Handshake,
  Megaphone,
  Send,
  Menu,
  Radar,
  Settings as SettingsIcon,
  Sparkles,
  Sun,
  TrendingUp,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useTenant } from "@/components/tenant-provider";
import { useViewMode } from "@/lib/use-view-mode";
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
//  Primary navigation — what every founder sees by default.
// ---------------------------------------------------------------------
//
// Hard rule (regression-pinned by sidebar.test.tsx): the primary set is
// exactly 8 items. Adding a 9th means breaking the cognitive-load
// promise of the Founder Simplification Pass — make a different
// surface (Advanced Mode, command palette, settings sub-nav) instead.

const PRIMARY_NAV: NavGroup[] = [
  {
    key: "today",
    label: "Today",
    defaultOpen: true,
    items: [
      { href: "/today", label: "Today's Plan", icon: Sun },
    ],
  },
  {
    key: "grow",
    label: "Grow",
    defaultOpen: true,
    items: [
      { href: "/grow/leads", label: "Leads", icon: Inbox },
      { href: "/crm", label: "CRM", icon: Handshake },
      { href: "/crm/contacts", label: "Contacts", icon: Contact },
      { href: "/grow/opportunities", label: "Opportunities", icon: Compass },
      {
        href: "/grow/market-intelligence",
        label: "Market Intelligence",
        icon: Radar,
      },
    ],
  },
  {
    key: "create",
    label: "Create",
    defaultOpen: true,
    items: [
      { href: "/studio", label: "Creative Studio", icon: Clapperboard },
      { href: "/create/social-posts", label: "Social Posts", icon: Sparkles },
      { href: "/create/linkedin", label: "LinkedIn Studio", icon: Linkedin },
      { href: "/create/ads", label: "Ads", icon: Megaphone },
      { href: "/create/creatives", label: "Creatives", icon: ImageIcon },
      { href: "/publishing", label: "Publishing", icon: Send },
    ],
  },
  {
    key: "results",
    label: "Results",
    defaultOpen: true,
    items: [
      { href: "/results", label: "Performance", icon: BarChart3 },
      { href: "/history", label: "AI History", icon: History },
    ],
  },
  {
    // Settings collapses to ONE top-level link. Sub-pages (Organization,
    // Team, Billing, Integrations, Notifications, Security, Usage,
    // Preferences) live in the in-page settings sub-nav.
    key: "settings",
    label: "Settings",
    defaultOpen: true,
    items: [
      { href: "/settings", label: "Workspace", icon: SettingsIcon },
    ],
  },
];

// ---------------------------------------------------------------------
//  Pro-mode destinations — shown only when ViewMode === "professional".
// ---------------------------------------------------------------------
//
// All three remain reachable via direct URL + command palette regardless
// of the toggle. The toggle controls SIDEBAR VISIBILITY, not access.

const ADVANCED_NAV: NavItem[] = [
  { href: "/library", label: "Library", icon: History },
  { href: "/campaign-lab", label: "Campaign Lab", icon: FlaskConical },
  { href: "/trends", label: "Trends (raw)", icon: TrendingUp },
];

// Pages no longer in any sidebar surface but still reachable via direct
// URL + command palette: /campaigns, /ai-coach, /bundles, /landing-pages.
// Each is folded into a primary destination per Phase 10.3 design.

const COLLAPSE_STORAGE_KEY = "aicmo.sidebar.collapse.v1";

export function Sidebar() {
  const pathname = usePathname();
  const { isProfessional } = useViewMode();
  const [mobileOpen, setMobileOpen] = useState(false);
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
        className={cn(
          "flex w-64 shrink-0 flex-col border-r border-border bg-card",
          "fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-out md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        <SidebarHeader onClose={() => setMobileOpen(false)} />
        <nav
          className="scrollbar-clean flex-1 overflow-y-auto px-3 pb-2 pt-3"
          data-testid="sidebar-nav"
        >
          {PRIMARY_NAV.map((group) => (
            <NavGroupBlock
              key={group.key}
              group={group}
              pathname={pathname}
              collapsed={!!collapsed[group.key]}
              onToggle={() => toggleGroup(group.key)}
            />
          ))}

          {isProfessional && (
            <div
              className="mb-3 mt-1 last:mb-0"
              data-testid="sidebar-group-advanced"
            >
              <div
                className="flex items-center justify-between rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/60"
                aria-label="Pro tools"
              >
                <span>Pro tools</span>
              </div>
              <ul className="mt-0.5 space-y-0.5">
                {ADVANCED_NAV.map((item) => (
                  <NavLink key={item.href} item={item} pathname={pathname} />
                ))}
              </ul>
            </div>
          )}
        </nav>
        <SidebarFooter />
      </aside>
    </>
  );
}

function SidebarHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-5">
      <div
        className="flex h-7 w-7 items-center justify-center rounded-lg bg-ai text-white shadow-sm"
        aria-hidden
      >
        <Sparkles className="h-4 w-4" />
      </div>
      <span className="text-sm font-semibold tracking-tight">DM Tool</span>
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
  collapsed,
  onToggle,
}: {
  group: NavGroup;
  pathname: string;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className="mb-3 last:mb-0"
      data-testid={`sidebar-group-${group.key}`}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!collapsed}
        className="group flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70 transition-colors hover:text-foreground"
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
      {!collapsed && (
        <ul className="mt-0.5 space-y-0.5">
          {group.items.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </ul>
      )}
    </div>
  );
}

function NavLink({
  item,
  pathname,
  variant = "primary",
}: {
  item: NavItem;
  pathname: string;
  variant?: "primary" | "secondary";
}) {
  const Icon = item.icon;
  const active =
    pathname === item.href || pathname.startsWith(`${item.href}/`);
  const isSecondary = variant === "secondary";
  return (
    <li>
      <Link
        href={item.href as never}
        data-testid={`sidebar-item-${item.href.slice(1) || "root"}`}
        className={cn(
          "group relative flex items-center gap-2.5 rounded-lg px-3 transition-all duration-200",
          isSecondary ? "py-1.5 text-sm" : "py-2 text-sm font-medium",
          active
            ? isSecondary
              ? "bg-muted text-foreground"
              : "bg-foreground text-background shadow-sm"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        {active && !isSecondary && (
          <span
            aria-hidden
            className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-ai"
          />
        )}
        <Icon
          className={cn(
            isSecondary ? "h-3.5 w-3.5" : "h-4 w-4",
            "shrink-0 transition-transform duration-200 group-hover:scale-[1.06]",
          )}
        />
        <span className="truncate">{item.label}</span>
      </Link>
    </li>
  );
}

function SidebarFooter() {
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
      className="shrink-0 border-t border-border bg-muted/30 px-3 py-3"
    >
      <Link
        href="/billing"
        className="flex items-center gap-3 rounded-lg p-2 transition-colors hover:bg-muted"
      >
        <span
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ai/15 text-xs font-semibold uppercase tracking-wide text-ai"
          aria-hidden
        >
          {initials}
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
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
      <div className="mt-2 flex items-center justify-between rounded-lg border border-ai-border/60 bg-ai-soft/70 px-3 py-1.5">
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
