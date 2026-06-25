"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RealityCheckCard } from "@/components/reality-check-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type BusinessProfile,
  type CampaignPlan,
  type CampaignType,
  type GenerateCampaignPayload,
  type GenerationContext,
  type RealityCheck,
} from "@/lib/api";
import { useGenerationContext } from "@/lib/use-generation-context";

import { PlannerForm, type FormState } from "./planner-form";
import { RecentList } from "./recent-list";
import { ResultCard } from "./result-card";

const REALITY_DEBOUNCE_MS = 1500;
const REALITY_MIN_GOAL_LEN = 6;

type RealityState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "data"; check: RealityCheck };

type ProfileState =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ready"; profile: BusinessProfile };

const DEFAULTS: FormState = {
  campaign_type: "product_launch",
  duration_days: 14,
  platforms: [],
  goal: "Drive launch-day revenue",
  tone: "",
  audience_override: "",
  landing_page_id: null,
};

export function Studio() {
  const [profileState, setProfileState] = useState<ProfileState>({
    kind: "loading",
  });
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [result, setResult] = useState<CampaignPlan | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<CampaignPlan[]>([]);
  const [reality, setReality] = useState<RealityState>({ kind: "idle" });
  // Phase 3.0 — AI defaults.
  const ctx = useGenerationContext();
  const [contextApplied, setContextApplied] = useState(false);

  // Phase 3.3 — URL-param prefill from action chips.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const campaignType = params.get("campaign_type");
    const goal = params.get("goal");
    if (!campaignType && !goal) return;
    setForm((f) => ({
      ...f,
      campaign_type: (campaignType as CampaignType | null) ?? f.campaign_type,
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

  // Debounced reality check whenever the goal text + duration settle.
  // Purely advisory — never blocks submission, never throws to the user.
  useEffect(() => {
    if (profileState.kind !== "ready") return;
    const goal = form.goal.trim();
    if (goal.length < REALITY_MIN_GOAL_LEN) {
      setReality({ kind: "idle" });
      return;
    }
    setReality({ kind: "loading" });
    const handle = setTimeout(async () => {
      try {
        const check = await api.coach.realityCheck({
          goal_text: goal,
          timeline_hint: `${form.duration_days} days`,
        });
        setReality({ kind: "data", check });
      } catch (e) {
        setReality({
          kind: "error",
          message: e instanceof Error ? e.message : "Reality check failed",
        });
      }
    }, REALITY_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [form.goal, form.duration_days, profileState.kind]);

  const loadRecent = useCallback(async () => {
    try {
      const items = await api.campaigns.list({ limit: 10 });
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
          platforms:
            f.platforms.length > 0
              ? f.platforms
              : profile.preferred_platforms.slice(0, 3),
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

  const availablePlatforms = useMemo(
    () =>
      profileState.kind === "ready"
        ? profileState.profile.preferred_platforms
        : [],
    [profileState],
  );

  const onGenerate = useCallback(
    async (overrideType?: CampaignType) => {
      setError(null);
      setGenerating(true);
      const payload: GenerateCampaignPayload = {
        campaign_type: overrideType ?? form.campaign_type,
        duration_days: form.duration_days,
        platforms: form.platforms,
        goal: form.goal.trim(),
        tone: form.tone.trim() || undefined,
        audience_override: form.audience_override.trim() || undefined,
        landing_page_id: form.landing_page_id ?? undefined,
      };
      try {
        const out = await api.campaigns.generate(payload);
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

  const onSelectRecent = (item: CampaignPlan) => {
    setResult(item);
    setForm({
      campaign_type: item.campaign_type,
      duration_days: item.duration_days as FormState["duration_days"],
      platforms: item.strategy.platforms.map((p) => p.platform),
      goal: item.goal,
      tone: item.tone,
      audience_override: "",
      landing_page_id: item.landing_page_id,
    });
  };

  const onToggleSaved = async (id: string, current: boolean) => {
    try {
      const updated = await api.campaigns.setSaved(id, !current);
      if (result?.id === id) setResult(updated);
      setRecent((items) => items.map((i) => (i.id === id ? updated : i)));
    } catch {
      /* swallow */
    }
  };

  const onDelete = async (id: string) => {
    try {
      await api.campaigns.delete(id);
      if (result?.id === id) setResult(null);
      setRecent((items) => items.filter((i) => i.id !== id));
    } catch {
      /* swallow */
    }
  };

  if (profileState.kind === "loading") {
    return <LoadingCard text="Loading planner…" />;
  }

  if (profileState.kind === "missing") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Finish business onboarding first</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Campaign plans need your business profile and preferred platforms.
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
        <PlannerForm
          value={form}
          onChange={setForm}
          availablePlatforms={availablePlatforms}
          generating={generating}
          onGenerate={() => onGenerate()}
        />

        <RealityCheckCard state={reality} />

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
            onRegenerate={() => onGenerate(result.campaign_type)}
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
        : current.goal === "Drive launch-day revenue"
          ? p.suggested_goal ?? current.goal
          : current.goal,
    tone: force ? "" : current.tone,
    landing_page_id:
      force
        ? p.suggested_landing_page_id ?? current.landing_page_id
        : current.landing_page_id ?? p.suggested_landing_page_id,
  };
}
