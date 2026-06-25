"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type AdObjective,
  type AdType,
  type GenerateAdPayload,
  type GeneratedAd,
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
  | { kind: "ready" };

const DEFAULTS: FormState = {
  ad_type: "meta",
  objective: "conversions",
  goal: "Drive sales",
  tone: "",
  audience_override: "",
  landing_page_id: null,
};

export function Studio() {
  const [profileState, setProfileState] = useState<ProfileState>({
    kind: "loading",
  });
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [result, setResult] = useState<GeneratedAd | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<GeneratedAd[]>([]);
  // Phase 3.0 — inherit AI defaults.
  const ctx = useGenerationContext();
  const [contextApplied, setContextApplied] = useState(false);

  // Phase 3.3 — URL-param prefill from action chips.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const adType = params.get("ad_type");
    const objective = params.get("objective");
    const goal = params.get("goal");
    if (!adType && !objective && !goal) return;
    setForm((f) => ({
      ...f,
      ad_type: (adType as AdType | null) ?? f.ad_type,
      objective:
        (objective as typeof f.objective | null) ?? f.objective,
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
      const items = await api.ads.list({ limit: 10 });
      setRecent(items);
    } catch {
      /* Non-fatal — recent list stays empty */
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
        setProfileState({ kind: "ready" });
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

  const onGenerate = useCallback(
    async (overrideType?: AdType) => {
      setError(null);
      setGenerating(true);
      const payload: GenerateAdPayload = {
        ad_type: overrideType ?? form.ad_type,
        objective: form.objective,
        goal: form.goal.trim(),
        tone: form.tone.trim() || undefined,
        audience_override: form.audience_override.trim() || undefined,
        landing_page_id: form.landing_page_id ?? undefined,
      };
      try {
        const out = await api.ads.generate(payload);
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

  const onSelectRecent = (item: GeneratedAd) => {
    setResult(item);
    setForm({
      ad_type: item.ad_type,
      objective: item.objective,
      goal: item.goal,
      tone: item.tone,
      audience_override: "",
      landing_page_id: item.landing_page_id,
    });
  };

  const onToggleSaved = async (id: string, current: boolean) => {
    try {
      const updated = await api.ads.setSaved(id, !current);
      if (result?.id === id) setResult(updated);
      setRecent((items) => items.map((i) => (i.id === id ? updated : i)));
    } catch {
      /* swallow */
    }
  };

  const onDelete = async (id: string) => {
    try {
      await api.ads.delete(id);
      if (result?.id === id) setResult(null);
      setRecent((items) => items.filter((i) => i.id !== id));
    } catch {
      /* swallow */
    }
  };

  /**
   * Phase 10.5 — AI Recommends prefill for Ads Studio.
   * Maps an opportunity brief into the ads FormState. Strict type
   * narrowing on ad_type + objective so a brief with an unknown
   * format/objective leaves the founder's current selection alone
   * rather than crashing the form.
   *
   * Declared BEFORE the early returns below so the hook order stays
   * stable across renders (React rules-of-hooks). Placing it after the
   * `loading`/`missing`/`error` returns made it run conditionally and
   * threw "change in the order of Hooks".
   */
  const useBrief = useCallback((brief: RecommendedBrief) => {
    const adTypes: AdType[] = [
      "meta",
      "google_search",
      "instagram_promo",
      "linkedin",
      "youtube",
    ];
    const adObjectives: AdObjective[] = [
      "awareness",
      "traffic",
      "engagement",
      "leads",
      "app_installs",
      "conversions",
      "sales",
    ];
    setForm((f) => {
      const next: FormState = { ...f };
      const fmt = brief.format?.toLowerCase() ?? "";
      if (fmt && (adTypes as string[]).includes(fmt)) {
        next.ad_type = fmt as AdType;
      }
      const obj = brief.objective?.toLowerCase() ?? "";
      if (obj && (adObjectives as string[]).includes(obj)) {
        next.objective = obj as AdObjective;
      }
      if (brief.goal) next.goal = brief.goal;
      return next;
    });
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
            Ads need your business profile to ground targeting and copy.
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
        <AiRecommends target="ad" onUseBrief={useBrief} />

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
            onRegenerate={() => onGenerate(result.ad_type)}
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
    goal:
      force
        ? p.suggested_goal ?? current.goal
        : current.goal === "Drive sales"
          ? p.suggested_goal ?? current.goal
          : current.goal,
    tone: force ? "" : current.tone,
    landing_page_id:
      force
        ? p.suggested_landing_page_id ?? current.landing_page_id
        : current.landing_page_id ?? p.suggested_landing_page_id,
  };
}
