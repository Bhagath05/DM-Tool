"use client";

/**
 * React hook over the module-level theme state.
 *
 * Why a separate file: keep lib/theme.ts framework-free (importable by the
 * edge / server). This file holds the only React glue. It also re-renders
 * when the OS preference flips while the choice is "system", so the
 * resolved theme a component shows stays accurate.
 */

import { useEffect, useState } from "react";

import {
  getThemeChoice,
  onThemeChange,
  resolveTheme,
  setThemeChoice,
  type ResolvedTheme,
  type ThemeChoice,
} from "./theme";

export function useTheme(): {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (c: ThemeChoice) => void;
} {
  // Default to "system" so SSR + first paint match; real value in the effect.
  const [choice, setLocal] = useState<ThemeChoice>("system");
  const [resolved, setResolved] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const initial = getThemeChoice();
    setLocal(initial);
    setResolved(resolveTheme(initial));

    const unsub = onThemeChange((c) => {
      setLocal(c);
      setResolved(resolveTheme(c));
    });

    // Track OS flips while following "system".
    const mql = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onSystem = () => setResolved(resolveTheme(getThemeChoice()));
    mql?.addEventListener?.("change", onSystem);

    return () => {
      unsub();
      mql?.removeEventListener?.("change", onSystem);
    };
  }, []);

  return {
    choice,
    resolved,
    setChoice: (c) => {
      setThemeChoice(c);
      setLocal(c);
      setResolved(resolveTheme(c));
    },
  };
}
