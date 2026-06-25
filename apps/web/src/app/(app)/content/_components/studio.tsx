"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type BusinessProfile,
  type ContentType,
  type GeneratedContent,
  type GenerateContentPayload,
  type GenerationContext,
} from "@/lib/api";
import { useGenerationContext } from "@/lib/use-generation-context";

import { AiRecommends, type RecommendedBrief } from "@/components/ai-recommends";

import { GeneratorForm, type FormState } from "./generator-form";
import { RecentList } from "./recent-list";
import { ResultCard } from "./result-card";

type ProfileState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; profile: BusinessProfile };

const DEFAULTS: FormState = {
  content_type: "social_post",
  platform: "",
  goal: "Drive engagement",
  tone: "",
  landing_page_id: null,
};

export function Studio() {
  const [profileState, setProfileState] = useState<ProfileState>({
    kind: "loading",
  });
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [result, setResult] = useState<GeneratedContent | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<GeneratedContent[]>([]);
  // Phase 3.0 — the AI's smart defaults for this user (winning platform,
  // best lead page, primary goal). Lands on mount; we merge into the form
  // only for fields the user hasn't manually touched.
  const ctx = useGenerationContext();
  const [contextApplied, setContextApplied] = useState(false);

  // Phase 3.3 — URL-param prefill from action chips. Runs once on mount,
  // before the context defaults effect, so chip-deep-links always win.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const type = params.get("type");
    const goal = params.get("goal");
    const platform = params.get("platform");
    if (!type && !goal && !platform) return;
    setForm((f) => ({
      ...f,
      content_type: (type as ContentType | null) ?? f.content_type,
      goal: goal ?? f.goal,
      platform: platform ?? f.platform,
    }));
  }, []);

  const loadRecent = useCallback(async () => {
    try {
      const items = await api.content.list({ limit: 10 });
      setRecent(items);
    } catch {
      // Non-fatal — the recent list just stays empty.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await api.business.get();
        if (cancelled) return;
        if (!profile) {
          setProfileState({ kind: "missing" });
          return;
        }
        setProfileState({ kind: "ready", profile });
        setForm((f) => ({
          ...f,
          platform: f.platform || profile.preferred_platforms[0] || "",
        }));
        loadRecent();
      } catch (e) {
        if (cancelled) return;
        setProfileState({
          kind: "error",
          message: e instanceof Error ? e.message : "Failed to load profile",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadRecent]);

  const platforms = useMemo(
    () =>
      profileState.kind === "ready"
        ? profileState.profile.preferred_platforms
        : [],
    [profileState],
  );

  // Apply AI defaults exactly once (on first context land). The user can
  // override anything from there; clicking "Reset to AI defaults" re-runs
  // the merge.
  useEffect(() => {
    if (contextApplied) return;
    if (ctx.context === null) return;
    setForm((f) => applyContextDefaults(f, ctx.context!));
    setContextApplied(true);
  }, [ctx.context, contextApplied]);

  const resetToAIDefaults = useCallback(() => {
    if (ctx.context === null) return;
    setForm((f) => applyContextDefaults({ ...DEFAULTS, ...f }, ctx.context!, true));
  }, [ctx.context]);

  const onGenerate = useCallback(
    async (overrideType?: ContentType) => {
      setError(null);
      setGenerating(true);
      const payload: GenerateContentPayload = {
        content_type: overrideType ?? form.content_type,
        platform: form.platform,
        goal: form.goal.trim(),
        tone: form.tone.trim() || undefined,
        landing_page_id: form.landing_page_id ?? undefined,
      };
      try {
        const out = await api.content.generate(payload);
        setResult(out);
        loadRecent();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          setProfileState({ kind: "missing" });
        } else {
          setError(e instanceof Error ? e.message : "Generation failed");
        }
      } finally {
        setGenerating(false);
      }
    },
    [form, loadRecent],
  );

  const onSelectRecent = (item: GeneratedContent) => {
    setResult(item);
    setForm({
      content_type: item.content_type,
      platform: item.platform,
      goal: item.goal,
      tone: item.tone,
      landing_page_id: item.landing_page_id,
    });
  };

  const onToggleSaved = async (id: string, current: boolean) => {
    try {
      const updated = await api.content.setSaved(id, !current);
      if (result?.id === id) setResult(updated);
      setRecent((items) => items.map((i) => (i.id === id ? updated : i)));
    } catch {
      /* swallow — the optimistic update would have flickered anyway */
    }
  };

  const onDelete = async (id: string) => {
    try {
      await api.content.delete(id);
      if (result?.id === id) setResult(null);
      setRecent((items) => items.filter((i) => i.id !== id));
    } catch {
      /* ignore */
    }
  };

  /**
   * Phase 10.5 — AI Recommends prefill. Closes the loop:
   *   opportunity → brief → form state → generate.
   * Only fields the founder hasn't already touched get overwritten,
   * mirroring the existing AI-defaults behaviour. content_type
   * format mapping prefers reel/carousel/ad_copy when the brief
   * names one; otherwise stays on the founder's current pick.
   *
   * Declared BEFORE the early returns below so the hook order stays
   * stable across renders (React rules-of-hooks).
   */
  const useBrief = useCallback((brief: RecommendedBrief) => {
    setForm((f) => {
      const next: FormState = { ...f };
      if (brief.platform) next.platform = brief.platform;
      if (brief.goal) next.goal = brief.goal;
      if (brief.format) {
        const fmt = brief.format.toLowerCase();
        if (fmt === "reel" || fmt === "carousel" || fmt === "ad_copy" || fmt === "social_post") {
          next.content_type = fmt as ContentType;
        }
      }
      return next;
    });
    setContextApplied(true);
    setError(null);
  }, []);

  if (profileState.kind === "loading") {
    return <LoadingCard text="Loading studio…" />;
  }

  if (profileState.kind === "missing") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Finish business onboarding first</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            The studio needs your business profile to ground every piece it
            generates.
          </p>
          <Button asChild>
            <Link href={"/onboarding/profile" as never}>Open onboarding</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (profileState.kind === "error") {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {profileState.message}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <AiRecommends target="content" onUseBrief={useBrief} />

        {ctx.context && (
          <div className="flex items-center justify-end px-1 text-xs text-muted-foreground">
            <button
              type="button"
              onClick={resetToAIDefaults}
              className="underline-offset-4 hover:text-foreground hover:underline"
            >
              Reset to AI defaults
            </button>
          </div>
        )}
        <GeneratorForm
          value={form}
          onChange={setForm}
          platforms={platforms}
          generating={generating}
          onGenerate={() => onGenerate()}
        />

        {error && (
          <Card>
            <CardContent className="pt-6 text-sm text-destructive">
              {error}
            </CardContent>
          </Card>
        )}

        {result && (
          <ResultCard
            item={result}
            regenerating={generating}
            onRegenerate={() => onGenerate(result.content_type)}
            onToggleSaved={() => onToggleSaved(result.id, result.is_saved)}
            onDelete={() => onDelete(result.id)}
          />
        )}
      </div>

      <RecentList
        items={recent}
        activeId={result?.id}
        onSelect={onSelectRecent}
      />
    </div>
  );
}

function LoadingCard({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {text}
      </CardContent>
    </Card>
  );
}

/**
 * Merge AI-suggested defaults into the form. With `force=false` (the auto
 * apply on first mount), we only overwrite fields the user clearly hasn't
 * touched yet — empty strings and nulls. With `force=true` (the "Reset to
 * AI defaults" link), every AI-suggested field overrides the current one.
 */
function applyContextDefaults(
  current: FormState,
  ctx: GenerationContext,
  force = false,
): FormState {
  const p = ctx.preferences;
  return {
    ...current,
    platform:
      force
        ? p.suggested_platform ?? current.platform
        : current.platform || p.suggested_platform || "",
    goal:
      force
        ? p.suggested_goal ?? current.goal
        : current.goal === "Drive engagement"
          ? p.suggested_goal ?? current.goal
          : current.goal,
    tone: force ? "" : current.tone,
    landing_page_id:
      force
        ? p.suggested_landing_page_id ?? current.landing_page_id
        : current.landing_page_id ?? p.suggested_landing_page_id,
  };
}
