"use client";

/**
 * Phase 10.0 polish — Notifications surface (popover).
 *
 * UI scaffolding only — there's no notifications backend yet. The
 * popover renders a premium empty state so the affordance reads as
 * intentional rather than broken. When a `/notifications` endpoint
 * lands, the panel body swaps in for a real list; the trigger /
 * positioning / accessibility don't change.
 *
 * Closes on outside click + Escape.
 */

import { Bell, BellOff } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

export function NotificationsButton() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Outside click + Esc close.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Notifications"
        aria-expanded={open}
        data-testid="notifications-button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-all duration-200 hover:border-ai-border hover:text-foreground",
          open && "border-ai-border bg-ai-soft text-ai-soft-foreground",
        )}
      >
        <Bell className="h-4 w-4" />
        {/* Reserved for a future unread-count dot. Intentionally not
            rendered today — no fake "3 new" indicators. */}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          data-testid="notifications-popover"
          className="absolute right-0 top-full z-40 mt-2 w-80 origin-top-right animate-pop overflow-hidden rounded-2xl border border-border bg-card shadow-lg"
        >
          <div className="border-b border-border/60 px-4 py-3">
            <div className="text-card-title font-semibold">Notifications</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Activity from your workspace will appear here.
            </p>
          </div>
          <div className="p-4">
            <EmptyState
              icon={BellOff}
              title="You're all caught up"
              description="No notifications yet. New leads, finished uploads, and AI insights will land here when they're ready."
              hint="Sync to email + Slack arrives in a future release."
              data-testid="notifications-empty"
            />
          </div>
        </div>
      )}
    </div>
  );
}
