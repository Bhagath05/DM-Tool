/**
 * View-mode (Simple vs Professional) — Constitution rule.
 *
 * Simple Mode (default): plain-language explanations, recommendations
 * visible, technical details COLLAPSED.
 *
 * Professional Mode: same plain-language is still visible (we never hide
 * the business explanation), but the technical-details disclosure starts
 * EXPANDED. Eventually we may also surface extra charts only relevant
 * to advanced marketers.
 *
 * Persisted in localStorage so a toggle survives reload. SSR-safe — the
 * default ("simple") is what server-rendered HTML uses, and the client
 * hydrates with the persisted value if different.
 *
 * NOT a React context: kept as a module-level value so any component
 * (including non-hook code in lib/) can read it. A tiny event listener
 * lets components subscribe to changes without a context provider.
 */

export type ViewMode = "simple" | "professional";

export const VIEW_MODE_STORAGE_KEY = "aicmo.view_mode.v1";
const CHANGE_EVENT = "aicmo:view-mode-change";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function getViewMode(): ViewMode {
  const s = storage();
  if (!s) return "simple";
  try {
    const raw = s.getItem(VIEW_MODE_STORAGE_KEY);
    return raw === "professional" ? "professional" : "simple";
  } catch {
    return "simple";
  }
}

export function setViewMode(mode: ViewMode): void {
  const s = storage();
  if (!s) return;
  try {
    s.setItem(VIEW_MODE_STORAGE_KEY, mode);
    window.dispatchEvent(
      new CustomEvent(CHANGE_EVENT, { detail: mode }),
    );
  } catch {
    /* persistence is best-effort */
  }
}

/**
 * Subscribe to mode changes. Returns an unsubscribe function. Used by
 * the `useViewMode` hook below.
 */
export function onViewModeChange(handler: (mode: ViewMode) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const listener = (e: Event) =>
    handler((e as CustomEvent<ViewMode>).detail ?? getViewMode());
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

// Test-only.
export function __resetViewModeForTests(): void {
  const s = storage();
  if (s) {
    try {
      s.removeItem(VIEW_MODE_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
}
