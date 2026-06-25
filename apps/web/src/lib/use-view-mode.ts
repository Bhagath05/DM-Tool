"use client";

/**
 * React hook over the module-level view-mode state.
 *
 * Why a separate file: keep `lib/view-mode.ts` framework-free so it can
 * be imported by anything (including lib code that runs on the edge).
 * This file holds the only React-specific glue.
 */

import { useEffect, useState } from "react";

import {
  getViewMode,
  onViewModeChange,
  setViewMode,
  type ViewMode,
} from "./view-mode";

export function useViewMode(): {
  mode: ViewMode;
  setMode: (m: ViewMode) => void;
  isProfessional: boolean;
} {
  // Default to "simple" so SSR + first paint match. Real value picked
  // up in the effect after mount.
  const [mode, setLocal] = useState<ViewMode>("simple");

  useEffect(() => {
    setLocal(getViewMode());
    const unsub = onViewModeChange((m) => setLocal(m));
    return unsub;
  }, []);

  return {
    mode,
    setMode: (m) => {
      setViewMode(m);
      setLocal(m);
    },
    isProfessional: mode === "professional",
  };
}
