/**
 * Theme (System / Light / Dark) — explicit, persisted, first-party.
 *
 * The product supports an explicit theme choice that always wins over the
 * OS. "System" tracks `prefers-color-scheme`; "Light"/"Dark" force it. The
 * choice is written to the <html data-theme> attribute, which globals.css
 * keys off:
 *
 *   choice "system" → remove the attribute  (OS media query governs)
 *   choice "light"  → data-theme="light"    (forces light)
 *   choice "dark"   → data-theme="dark"      (forces dark)
 *
 * Framework-free on purpose (mirrors lib/view-mode.ts): a module-level
 * value any code can read, plus a tiny event so components subscribe
 * without a context provider. SSR-safe — the default ("system") is what
 * server HTML assumes, and the inline bootstrap script (THEME_INIT_SCRIPT)
 * applies the persisted value before first paint so there is no flash.
 */

export type ThemeChoice = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "aicmo.theme.v1";
const CHANGE_EVENT = "aicmo:theme-change";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function getThemeChoice(): ThemeChoice {
  const s = storage();
  if (!s) return "system";
  try {
    const raw = s.getItem(THEME_STORAGE_KEY);
    return raw === "light" || raw === "dark" ? raw : "system";
  } catch {
    return "system";
  }
}

/** Mirror a choice onto <html data-theme> so globals.css re-skins. */
export function applyThemeChoice(choice: ThemeChoice): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (choice === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", choice);
  }
}

export function setThemeChoice(choice: ThemeChoice): void {
  applyThemeChoice(choice);
  const s = storage();
  if (s) {
    try {
      if (choice === "system") s.removeItem(THEME_STORAGE_KEY);
      else s.setItem(THEME_STORAGE_KEY, choice);
    } catch {
      /* persistence is best-effort */
    }
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: choice }));
  }
}

/** What the browser is actually showing, given the choice + OS preference. */
export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice === "light" || choice === "dark") return choice;
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function onThemeChange(handler: (choice: ThemeChoice) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const listener = (e: Event) =>
    handler((e as CustomEvent<ThemeChoice>).detail ?? getThemeChoice());
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

/**
 * Inline <script> body injected into <head> so the persisted theme is on
 * <html> before the first paint (no flash of the wrong theme). Kept tiny
 * and dependency-free; wrapped in try/catch so a blocked localStorage can
 * never break the page — it just falls back to "system".
 */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`;

// Test-only.
export function __resetThemeForTests(): void {
  const s = storage();
  if (s) {
    try {
      s.removeItem(THEME_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
  if (typeof document !== "undefined") {
    document.documentElement.removeAttribute("data-theme");
  }
}
