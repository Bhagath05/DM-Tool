"use client";

import { useCallback, useEffect, useState } from "react";

import { api, type GenerationContext } from "@/lib/api";

/**
 * Phase 3.0 — shared inheritance hook.
 *
 * Every studio form calls this on mount. The context is fetched once,
 * cached in localStorage for 10 minutes, and re-used across all four
 * studios so the founder never re-fills the same fields twice.
 *
 * Cache lifetime is short by design: a freshly updated profile, a newly
 * published lead page, or a new top-converting asset should reflect in
 * defaults within minutes.
 */

const CACHE_KEY = "aicmo:generation-context:v1";
const CACHE_MAX_AGE_MS = 10 * 60 * 1000; // 10 min

export type ContextState =
  | { kind: "loading" }
  | { kind: "missing" } // profile not onboarded yet
  | { kind: "error"; message: string }
  | { kind: "ready"; context: GenerationContext };

export function useGenerationContext() {
  const [state, setState] = useState<ContextState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({ kind: "ready", context: cached });
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const ctx = await api.context.snapshot();
        writeCache(ctx);
        setState({ kind: "ready", context: ctx });
      } catch (e) {
        // 409 = profile not yet onboarded — special case, surface as
        // 'missing' so the caller can route the user to /onboarding.
        const msg = e instanceof Error ? e.message : "context unavailable";
        if (msg.toLowerCase().includes("onboarding")) {
          setState({ kind: "missing" });
        } else {
          setState({ kind: "error", message: msg });
        }
      } finally {
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return {
    state,
    refreshing,
    refresh: () => void load({ force: true }),
    /** Convenience accessor that returns null until the snapshot lands. */
    context: state.kind === "ready" ? state.context : null,
  };
}

// ---------------- 10min localStorage cache ----------------

function readCache(): GenerationContext | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as {
      savedAt: number;
      context: GenerationContext;
    };
    if (Date.now() - parsed.savedAt > CACHE_MAX_AGE_MS) return null;
    return parsed.context;
  } catch {
    return null;
  }
}

function writeCache(context: GenerationContext): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ savedAt: Date.now(), context }),
    );
  } catch {
    /* quota — ignore */
  }
}

/**
 * Convenience: invalidate the cached snapshot. Call after publishing a
 * landing page, completing analysis re-runs, etc. so the next studio
 * mount picks up fresh defaults.
 */
export function invalidateGenerationContextCache(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CACHE_KEY);
  } catch {
    /* ignore */
  }
}
