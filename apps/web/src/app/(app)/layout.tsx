import {
  CommandPalette,
  CommandPaletteTrigger,
} from "@/components/command-palette";
import { FromSourceBanner } from "@/components/from-source-banner";
import { NotificationsButton } from "@/components/notifications-button";
import { PlanChip } from "@/components/plan-chip";
import { RequireTenant } from "@/components/require-tenant";
import { Sidebar } from "@/components/sidebar";
import { TenantProvider } from "@/components/tenant-provider";
import { TenantTopbar } from "@/components/tenant-topbar";
import { UserMenu } from "@/components/user-menu";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // TenantProvider wraps the entire (app) group so every authenticated
    // page can call `useTenant()`. It boots /me on mount and re-routes
    // the user when `suggested_route` doesn't match the current path
    // (e.g. zero-memberships → /onboarding).
    <TenantProvider enforceSuggestedRoute>
      {/* CommandPalette is mounted at the layout level so ⌘K works
          from any (app) page without per-route plumbing. */}
      <CommandPalette />
      {/* h-dvh (dynamic viewport height) caps the outer at viewport so the
          sidebar stays put and only <main> scrolls. */}
      <div className="flex h-dvh overflow-hidden bg-background">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border/60 bg-background/85 px-4 backdrop-blur-md sm:px-6">
            {/* Left cluster — tenant context. Indented past the
                mobile hamburger so it never overlaps on small screens. */}
            <div className="ml-12 flex min-w-0 items-center md:ml-0">
              <TenantTopbar />
            </div>
            {/* Right cluster — global search, plan, notifications, profile. */}
            <div className="flex items-center gap-2 sm:gap-3">
              <CommandPaletteTrigger />
              <PlanChip />
              <NotificationsButton />
              <span aria-hidden className="hidden h-6 w-px bg-border/80 sm:block" />
              <UserMenu />
            </div>
          </header>
          {/* RequireTenant gates the page content but leaves sidebar +
              topbar visible. So during loading / missing-org / missing-
              brand states, the user still sees navigation + sign-out
              instead of a frozen blank screen. */}
          <main className="scrollbar-clean flex-1 overflow-y-auto px-4 py-8 sm:px-6 sm:py-10 lg:px-12 lg:py-12">
            {/* Auto-resolving "Back to {source}" banner. Renders only
                when the URL carries a known `?from=` slug. Silent no-op
                on every other page so layouts never get cluttered. */}
            <FromSourceBanner />
            <RequireTenant>{children}</RequireTenant>
          </main>
        </div>
      </div>
    </TenantProvider>
  );
}
