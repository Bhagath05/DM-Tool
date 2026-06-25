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
  type GenerateVisualPayload,
  type GeneratedVisual,
  type GenerationContext,
  type VisualType,
} from "@/lib/api";
import { useGenerationContext } from "@/lib/use-generation-context";

import { GeneratorForm, type FormState } from "./generator-form";
import { RecentList } from "./recent-list";
import { ResultCard } from "./result-card";

type ProfileState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; profile: BusinessProfile };

const DEFAULTS: FormState = {
  visual_type: "ad_creative",
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
  const [result, setResult] = useState<GeneratedVisual | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<GeneratedVisual[]>([]);
  // Phase 3.0 — AI defaults.
  const ctx = useGenerationContext();
  const [contextApplied, setContextApplied] = useState(false);

  // Phase 3.3 — URL-param prefill from action chips.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const visualType = params.get("visual_type");
    const platform = params.get("platform");
    const goal = params.get("goal");
    if (!visualType && !platform && !goal) return;
    setForm((f) => ({
      ...f,
      visual_type: (visualType as VisualType | null) ?? f.visual_type,
      platform: platform ?? f.platform,
      goal: goal ?? f.goal,
    }));
  }, []);

  useEffect(() => {
    if (contextApplied || ctx.context === null) return;
    setForm((f) => applyContextDefaults(f, ctx.context!));
    setContextApplied(true);
  }, [ctx.context, contextApplied]);

  const resetToAIDefaults = useCallback(() => {
    if (ctx.context === null) return;
    setForm((f) => applyContextDefaults({ ...DEFAULTS, ...f }, ctx.context!, true));
  }, [ctx.context]);

  const loadRecent = useCallback(async () => {
    try {
      const items = await api.visuals.list({ limit: 10 });
      setRecent(items);
    } catch {
      /* non-fatal */
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

  const onGenerate = useCallback(
    async (overrideType?: VisualType) => {
      setError(null);
      setGenerating(true);
      const payload: GenerateVisualPayload = {
        visual_type: overrideType ?? form.visual_type,
        platform: form.platform,
        goal: form.goal.trim(),
        tone: form.tone.trim() || undefined,
        landing_page_id: form.landing_page_id ?? undefined,
      };
      try {
        const out = await api.visuals.generate(payload);
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

  const onSelectRecent = (item: GeneratedVisual) => {
    setResult(item);
    setForm({
      visual_type: item.visual_type,
      platform: item.platform,
      goal: item.goal,
      tone: item.tone,
      landing_page_id: item.landing_page_id,
    });
  };

  const onToggleSaved = async (id: string, current: boolean) => {
    try {
      const updated = await api.visuals.setSaved(id, !current);
      if (result?.id === id) setResult(updated);
      setRecent((items) => items.map((i) => (i.id === id ? updated : i)));
    } catch {
      /* swallow */
    }
  };

  const onDelete = async (id: string) => {
    try {
      await api.visuals.delete(id);
      if (result?.id === id) setResult(null);
      setRecent((items) => items.filter((i) => i.id !== id));
    } catch {
      /* swallow */
    }
  };

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
            Image creatives need your business profile and preferred platforms.
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
            onRegenerate={() => onGenerate(result.visual_type)}
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
