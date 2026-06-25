"use client";

/**
 * Minimal in-house Modal primitive.
 *
 * Why custom and not Radix Dialog:
 *  - Same reasoning as `popover-menu.tsx` — the codebase keeps Radix
 *    deps opt-in to control bundle size. The interaction surface for
 *    a confirmation / generation modal is small: open on demand, close
 *    on ESC / overlay click / explicit close. ~80 lines handle it
 *    without dragging in Radix Dialog + its CSS + its peer-deps.
 *
 * Behaviour:
 *  - Rendered through a body-level React portal so the panel escapes
 *    any `overflow: hidden` ancestor.
 *  - Body scroll locks while the modal is open and restores on close.
 *  - ESC + clicking the overlay both call `onOpenChange(false)`.
 *  - The first interactive element inside the panel receives focus on
 *    open; the previously-focused trigger is re-focused on close.
 *
 * Accessibility:
 *  - role="dialog" + aria-modal="true" on the panel
 *  - `aria-labelledby` wired to the title row when `title` is provided
 *  - Focus is parked inside the panel; clicking outside dismisses
 *    instead of letting the page accept clicks behind the overlay.
 */

import { X } from "lucide-react";
import { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  "data-testid"?: string;
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
  "data-testid": testId,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();

  const close = useCallback(() => onOpenChange(false), [onOpenChange]);

  // ESC closes + lock body scroll while open.
  useEffect(() => {
    if (!open) return;
    previouslyFocused.current =
      typeof document !== "undefined"
        ? (document.activeElement as HTMLElement | null)
        : null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    }
    document.addEventListener("keydown", handleKey);

    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prevOverflow;
      // Restore focus to whatever opened us, on the next tick so React
      // has finished unmounting the panel first.
      const target = previouslyFocused.current;
      if (target && typeof target.focus === "function") {
        // setTimeout 0 keeps this off the same frame as the unmount.
        setTimeout(() => target.focus({ preventScroll: true }), 0);
      }
    };
  }, [open, close]);

  // Auto-focus the first interactive element on open.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusable = panel.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus({ preventScroll: true });
  }, [open]);

  if (!open) return null;
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-end justify-center p-3 sm:items-center sm:p-6"
      role="presentation"
      data-testid={testId ?? "modal"}
    >
      {/* Overlay */}
      <div
        aria-hidden="true"
        onClick={close}
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
      />
      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        className={cn(
          "relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-border bg-card shadow-xl",
          className,
        )}
      >
        {(title || description) && (
          <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-3">
            <div className="space-y-0.5">
              {title && (
                <h2
                  id={titleId}
                  className="text-base font-semibold leading-snug"
                >
                  {title}
                </h2>
              )}
              {description && (
                <p className="text-xs text-muted-foreground">{description}</p>
              )}
            </div>
            <button
              type="button"
              onClick={close}
              aria-label="Close"
              data-testid="modal-close"
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </header>
        )}
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
