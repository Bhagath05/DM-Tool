"use client";

/**
 * PopoverMenu — minimal button-trigger + floating panel.
 *
 * Why custom and not @radix-ui/react-dropdown-menu:
 *  - We don't have the radix-dropdown-menu dep installed and adding it
 *    just for tenant switchers (which are render-when-needed only) is
 *    over-budget for the bundle.
 *  - The interaction surface is small: open on click, close on item
 *    click / escape / outside click. ~50 lines of React handle it.
 *
 * Accessibility:
 *  - Trigger is a real <button> with aria-haspopup="menu" + aria-expanded.
 *  - Panel is role="menu"; items render as role="menuitem".
 *  - ESC closes; outside-click closes; click on item closes (caller's
 *    handler runs first).
 *  - First menu item gets focus when the panel opens for keyboard nav.
 *
 * Layout:
 *  - The panel is `absolute` positioned below the trigger. Caller is
 *    expected to wrap the trigger in a `relative` container — we don't
 *    do portal-based positioning to avoid the complexity.
 */

import { cn } from "@/lib/utils";
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export interface PopoverMenuProps {
  /** Rendered as the always-visible button. Receives `isOpen` so the
   *  caller can style the chevron / active state. */
  trigger: (state: { isOpen: boolean }) => ReactNode;
  /** Menu content. Use `<PopoverMenuItem>` for keyboard nav to work. */
  children: ReactNode;
  /** Visual width hint. Defaults to "auto"; pass "trigger" to match the
   *  trigger's width. */
  panelClassName?: string;
  /** A11y label for the panel role="menu". */
  ariaLabel?: string;
  /** Suppress the entire popover (rendered as a plain inert trigger).
   *  Used by the switchers when there's only one option — the same
   *  visual shows, but clicking does nothing. */
  disabled?: boolean;
}

export function PopoverMenu({
  trigger,
  children,
  panelClassName,
  ariaLabel,
  disabled = false,
}: PopoverMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // Outside-click + ESC handlers. Bound on `document` because the panel
  // is sibling to the trigger, not a child.
  useEffect(() => {
    if (!isOpen) return;

    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (containerRef.current && !containerRef.current.contains(target)) {
        setIsOpen(false);
      }
    }
    function handleKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [isOpen]);

  // Move keyboard focus into the panel when it opens. Selecting the
  // first real menuitem (skipping section headers).
  useEffect(() => {
    if (!isOpen) return;
    const panel = panelRef.current;
    if (!panel) return;
    const first = panel.querySelector<HTMLElement>(
      '[role="menuitem"]:not([aria-disabled="true"])',
    );
    first?.focus();
  }, [isOpen]);

  function onPanelKey(e: KeyboardEvent<HTMLDivElement>) {
    // Naive but adequate arrow-key navigation between menuitems.
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const panel = panelRef.current;
    if (!panel) return;
    const items = Array.from(
      panel.querySelectorAll<HTMLElement>(
        '[role="menuitem"]:not([aria-disabled="true"])',
      ),
    );
    const active = document.activeElement as HTMLElement | null;
    const idx = active ? items.indexOf(active) : -1;
    const next =
      e.key === "ArrowDown"
        ? items[(idx + 1) % items.length]
        : items[(idx - 1 + items.length) % items.length];
    next?.focus();
    e.preventDefault();
  }

  if (disabled) {
    return (
      <div ref={containerRef} className="relative inline-flex">
        {trigger({ isOpen: false })}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={menuId}
        onClick={() => setIsOpen((s) => !s)}
        className="inline-flex"
      >
        {trigger({ isOpen })}
      </button>
      {isOpen && (
        <div
          ref={panelRef}
          id={menuId}
          role="menu"
          aria-label={ariaLabel}
          onKeyDown={onPanelKey}
          // onClick: close after a menuitem click. We close on bubble
          // (after the item's handler ran) so the caller doesn't have to
          // call close() manually.
          onClick={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[role="menuitem"]')) {
              setIsOpen(false);
            }
          }}
          className={cn(
            "absolute left-0 top-full z-50 mt-1 min-w-[12rem] overflow-hidden rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md",
            panelClassName,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * One row in the menu. Use `selected` to mark the currently-active
 * option (shows a checkmark + bold). `onSelect` runs before the menu
 * closes — `await` work in here is fine; the menu closes synchronously.
 */
export interface PopoverMenuItemProps {
  onSelect: () => void;
  selected?: boolean;
  disabled?: boolean;
  children: ReactNode;
  /** Extra description, rendered below the label in a muted color. */
  description?: ReactNode;
  /** Used by the test suite — the role="menuitem" element gets it. */
  "data-testid"?: string;
}

export function PopoverMenuItem({
  onSelect,
  selected = false,
  disabled = false,
  children,
  description,
  "data-testid": testId,
}: PopoverMenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      aria-disabled={disabled || undefined}
      data-testid={testId}
      onClick={(e) => {
        if (disabled) {
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        onSelect();
      }}
      className={cn(
        "flex w-full cursor-pointer items-start justify-between gap-3 rounded-sm px-2 py-1.5 text-left text-sm outline-none transition-colors",
        "focus:bg-accent focus:text-accent-foreground hover:bg-accent hover:text-accent-foreground",
        selected && "font-medium",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <div className="flex flex-col gap-0.5">
        <span>{children}</span>
        {description && (
          <span className="text-xs text-muted-foreground">{description}</span>
        )}
      </div>
      {selected && (
        <span aria-hidden className="text-primary">
          ✓
        </span>
      )}
    </button>
  );
}

/** Visual separator between menu sections. */
export function PopoverMenuSeparator() {
  return <div role="separator" className="my-1 h-px bg-border" />;
}

/** Non-interactive label inside the menu (e.g. "Switch organization"). */
export function PopoverMenuLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-2 py-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}
