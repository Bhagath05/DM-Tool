"use client";

import { Loader2, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type BusinessAnalysis, type BusinessProfile } from "@/lib/api";

import { StrategyAnalysis } from "./strategy-analysis";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "ready"; profile: BusinessProfile }
  | { kind: "error"; message: string };

const POLL_MS = 3000;
const MAX_POLLS = 20;

export function ProfileLoader() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloadVersion, setReloadVersion] = useState(0);
  const pollsRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    pollsRef.current = 0;

    const load = async () => {
      try {
        const profile = await api.business.get();
        if (cancelled) return;
        if (!profile) {
          setState({ kind: "missing" });
          return;
        }
        setState({ kind: "ready", profile });
        if (profile.analysis_status === "pending") {
          schedulePoll();
        }
      } catch (e) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Failed to load profile",
        });
      }
    };

    const schedulePoll = () => {
      if (cancelled) return;
      if (pollsRef.current >= MAX_POLLS) return;
      pollsRef.current += 1;
      setTimeout(load, POLL_MS);
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadVersion]);

  // Re-arm the analysis pipeline without making the user re-onboard.
  // Used by the "Try again" button on the failure card — common after a
  // transient provider 503 on first run.
  const onRetryAnalysis = useCallback(async () => {
    try {
      const updated = await api.business.retryAnalysis();
      setState({ kind: "ready", profile: updated });
      // Bumping the version re-runs the effect, which resets pollsRef
      // and starts polling again until analysis_status leaves "pending".
      setReloadVersion((v) => v + 1);
    } catch (e) {
      setState({
        kind: "error",
        message:
          e instanceof Error ? e.message : "Couldn't restart the analysis",
      });
    }
  }, []);

  if (state.kind === "loading") {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading your business profile…
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "missing") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Set up your business</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Tell the AI about your business once. Everything it generates from
            here — content, ads, trends, strategy — will be grounded in your
            profile.
          </p>
          <Button asChild>
            <Link href={"/onboarding/profile" as never}>
              <Sparkles className="h-4 w-4" />
              Start onboarding
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          Couldn’t load profile: {state.message}
          <button
            type="button"
            className="ml-2 underline"
            onClick={() => router.refresh()}
          >
            retry
          </button>
        </CardContent>
      </Card>
    );
  }

  return (
    <ProfileSummary profile={state.profile} onRetryAnalysis={onRetryAnalysis} />
  );
}

function ProfileSummary({
  profile,
  onRetryAnalysis,
}: {
  profile: BusinessProfile;
  onRetryAnalysis: () => void | Promise<void>;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between">
          <div>
            <CardTitle>{profile.business_name}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {profile.industry} · {profile.brand_tone} ·{" "}
              {profile.preferred_platforms.join(", ")}
            </p>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link href={"/onboarding/profile" as never}>Edit</Link>
          </Button>
        </CardHeader>
      </Card>

      <AnalysisCard profile={profile} onRetryAnalysis={onRetryAnalysis} />
    </div>
  );
}

function AnalysisCard({
  profile,
  onRetryAnalysis,
}: {
  profile: BusinessProfile;
  onRetryAnalysis: () => void | Promise<void>;
}) {
  if (profile.analysis_status === "pending") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="h-4 w-4 animate-spin" />
            AI analysis in progress
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Your AI strategist is reading your business right now — building
          audience insights, opportunities, and your growth path. Usually
          takes 5–15 seconds. This page will update on its own.
        </CardContent>
      </Card>
    );
  }

  if (profile.analysis_status === "failed") {
    return <AnalysisFailedCard profile={profile} onRetry={onRetryAnalysis} />;
  }

  const a = profile.analysis;
  if (!a) return null;

  // Phase 2.1 — if the analysis has v2 strategist fields, render the
  // consultant-style layout. Otherwise fall back to the v1 grid so analyses
  // persisted before v2 still render cleanly.
  if (hasV2Fields(a)) {
    return (
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{a.business_summary}</CardTitle>
          </CardHeader>
        </Card>
        <StrategyAnalysis analysis={a} />
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Strategy summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed">
          <p>{a.business_summary}</p>
          <p className="text-muted-foreground">{a.strategy_recommendation}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <ListCard title="Audience insights" items={a.audience_insights} />
        <ListCard
          title="Marketing opportunities"
          items={a.marketing_opportunities}
        />
        <ListCard title="Content directions" items={a.content_directions} />
      </div>
    </div>
  );
}

/**
 * Friendly version of the dashboard's "Analysis failed" state.
 *
 * The most common cause is a transient provider 503 (Gemini under load) on
 * first run, which is the founder's problem to fix only in the sense of
 * "click this button." We surface a one-click retry that re-runs the
 * analysis on the existing profile — no need to re-onboard.
 */
function AnalysisFailedCard({
  profile,
  onRetry,
}: {
  profile: BusinessProfile;
  onRetry: () => void | Promise<void>;
}) {
  const [retrying, setRetrying] = useState(false);
  const explanation = friendlyAnalysisError(profile.analysis_error);

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      // Parent flips state to pending → this card unmounts, so this only
      // runs if the retry itself errored.
      setRetrying(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          The AI couldn&apos;t finish reading your business
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">{explanation}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={handleRetry} disabled={retrying}>
            {retrying ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {retrying ? "Starting…" : "Try again"}
          </Button>
          <Button asChild variant="outline">
            <Link href={"/onboarding/profile" as never}>Edit your profile</Link>
          </Button>
        </div>
        {profile.analysis_error && (
          <details className="rounded-md border bg-muted/30 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Show the technical error
            </summary>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {profile.analysis_error}
            </p>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

/** Translate the raw provider error into something a founder can act on. */
function friendlyAnalysisError(raw: string | null): string {
  if (!raw) {
    return "The AI strategist hit a snag while reading your business. Most of the time, hitting Try again clears it.";
  }
  const lowered = raw.toLowerCase();
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI was under heavy load just now — that's a temporary blip on their end, not your profile. Hit Try again in a moment.";
  }
  if (lowered.includes("429") || lowered.includes("rate")) {
    return "We hit the AI provider's rate limit. Wait 30 seconds and try again — it'll go through.";
  }
  if (lowered.includes("api key") || lowered.includes("auth")) {
    return "There's an authentication issue with the AI provider. This usually needs an API key fix in your environment — ping engineering.";
  }
  return "The AI couldn't complete the analysis on the first try. Hit Try again — most errors here are transient.";
}

/** True when the analysis was produced by Intelligence Engine v2 — at least
 *  one strategist field is populated. Used to route between v1/v2 surfaces. */
function hasV2Fields(a: BusinessAnalysis): boolean {
  return Boolean(
    a.current_state ||
      a.desired_future_state ||
      a.gap_analysis ||
      (a.realistic_growth_path && a.realistic_growth_path.length > 0) ||
      (a.recommended_acquisition_channels &&
        a.recommended_acquisition_channels.length > 0),
  );
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm">
          {items.map((item, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
