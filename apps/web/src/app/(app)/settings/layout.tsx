"use client";

/**
 * Phase 10.1 — Settings shell.
 *
 * Persistent vertical sub-nav (Linear / Stripe / Vercel pattern) so
 * the founder always knows they're in Settings and can hop between
 * pages without losing context. The shell:
 *
 *   - Renders the page-level eyebrow + title once, top-left.
 *   - Renders the sub-nav left of the content on desktop (lg+).
 *   - Stacks the sub-nav above the content as a horizontal scroller
 *     on tablet / mobile (< lg).
 *   - Highlights the active route with an AI-accent rail bar.
 *
 * The shell does NOT render the page's own H1 — each settings page
 * carries its own `<SectionHeading size="lg">` for the heading. That
 * keeps the eyebrow + description per-page rather than forcing a
 * generic "Settings" hero on every screen.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

import { SETTINGS_NAV } from "./_nav";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div
      className="mx-auto flex max-w-6xl flex-col gap-8"
      data-testid="settings-shell"
    >
      <header className="flex flex-col gap-1.5">
        <p className="text-meta">Settings</p>
        <h1 className="text-section font-semibold tracking-tight">
          Workspace settings
        </h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Manage your workspace, team, billing, integrations, and security.
        </p>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row lg:gap-10">
        <SettingsNav pathname={pathname} />
        <section className="min-w-0 flex-1">{children}</section>
      </div>
    </div>
  );
}

function SettingsNav({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Settings"
      data-testid="settings-nav"
      className={cn(
        // Desktop: sticky sidebar.
        "lg:sticky lg:top-4 lg:w-60 lg:shrink-0 lg:self-start",
      )}
    >
      {/* Horizontal scroller on mobile/tablet, vertical column on lg+. */}
      <ul
        className={cn(
          "scrollbar-clean flex gap-1 overflow-x-auto pb-1",
          "lg:flex-col lg:gap-0.5 lg:overflow-visible lg:pb-0",
        )}
      >
        {SETTINGS_NAV.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <li key={item.href} className="shrink-0 lg:shrink">
              <Link
                href={item.href as never}
                data-testid={`settings-nav-${item.href.split("/").pop()}`}
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-foreground text-background shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {active && (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 hidden h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-ai lg:block"
                  />
                )}
                <Icon className="h-4 w-4 shrink-0" />
                <span className="whitespace-nowrap">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
