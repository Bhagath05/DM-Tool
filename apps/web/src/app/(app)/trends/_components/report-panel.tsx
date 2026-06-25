"use client";

import { Loader2, RefreshCw, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api, type TrendReport } from "@/lib/api";

import { TrendCards } from "./trend-cards";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "no-profile" }
  | { kind: "ready"; report: TrendReport }
  | { kind: "error"; message: string };

const POLL_MS = 3500;
const MAX_POLLS = 30;

export function TrendReportPanel() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const pollsRef = useRef(0);

  const load = useCallback(async () => {
    try {
      const report = await api.trends.get();
      if (!report) {
        setState({ kind: "missing" });
        return;
      }
      setState({ kind: "ready", report });
      if (report.status === "pending" && pollsRef.current < MAX_POLLS) {
        pollsRef.current += 1;
        setTimeout(load, POLL_MS);
      }
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "Failed to load report",
      });
    }
  }, []);

  useEffect(() => {
    pollsRef.current = 0;
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const report = await api.trends.refresh();
      pollsRef.current = 0;
      setState({ kind: "ready", report });
      if (report.status === "pending") {
        setTimeout(load, POLL_MS);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setState({ kind: "no-profile" });
      } else {
        setRefreshError(
          e instanceof Error ? e.message : "Refresh failed",
        );
      }
    } finally {
      setRefreshing(false);
    }
  };

  if (state.kind === "loading") {
    return <LoadingCard text="Loading trend report…" />;
  }

  if (state.kind === "no-profile") {
    return (
      <EmptyCard
        title="Finish business onboarding first"
        body="Trends are tailored to your industry and audience — we can't fetch
        anything useful without your profile."
        action={
          <Button asChild>
            <Link href={"/onboarding/profile" as never}>Open onboarding</Link>
          </Button>
        }
      />
    );
  }

  if (state.kind === "missing") {
    return (
      <EmptyCard
        title="No trend report yet"
        body="Pull fresh signals from Google Trends and Reddit and the AI will
        map them onto your business. Takes about 15 seconds."
        action={
          <Button onClick={onRefresh} disabled={refreshing}>
            {refreshing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Starting…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate trends
              </>
            )}
          </Button>
        }
        error={refreshError}
      />
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          Couldn’t load report: {state.message}
        </CardContent>
      </Card>
    );
  }

  const r = state.report;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          Last updated {new Date(r.updated_at).toLocaleString()}
          {r.raw_trends?.sources_failed.length ? (
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
              {r.raw_trends.sources_failed.join(", ")} unavailable
            </span>
          ) : null}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing || r.status === "pending"}
        >
          {refreshing || r.status === "pending" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Refresh
        </Button>
      </div>

      {refreshError && (
        <p className="text-sm text-destructive">{refreshError}</p>
      )}

      {r.status === "pending" && (
        <LoadingCard
          text="Reading what's trending right now and connecting it to your business…"
          icon={<TrendingUp className="h-4 w-4 animate-pulse" />}
        />
      )}

      {r.status === "failed" && (
        <TrendsFailedCard
          rawError={r.analysis_error}
          retrying={refreshing}
          onRetry={onRefresh}
        />
      )}

      {r.status === "completed" && r.analysis && (
        <TrendCards analysis={r.analysis} />
      )}
    </div>
  );
}

function LoadingCard({
  text,
  icon,
}: {
  text: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground">
        {icon ?? <Loader2 className="h-4 w-4 animate-spin" />}
        {text}
      </CardContent>
    </Card>
  );
}

function EmptyCard({
  title,
  body,
  action,
  error,
}: {
  title: string;
  body: string;
  action: React.ReactNode;
  error?: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{body}</p>
        {action}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

/**
 * Friendly Trends failure card with a one-click retry.
 *
 * Mirrors the dashboard's AnalysisFailedCard — the raw provider error is
 * tucked into a collapsible "Show technical error" pane so the default
 * surface stays calm and actionable. The most common cause here is a
 * Gemini truncation (schema too large for max_tokens) or a transient 503.
 */
function TrendsFailedCard({
  rawError,
  retrying,
  onRetry,
}: {
  rawError: string | null;
  retrying: boolean;
  onRetry: () => void | Promise<void>;
}) {
  const explanation = friendlyTrendsError(rawError);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          The AI couldn&apos;t finish reading the trends
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">{explanation}</p>
        <Button onClick={onRetry} disabled={retrying}>
          {retrying ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {retrying ? "Trying again…" : "Try again"}
        </Button>
        {rawError && (
          <details className="rounded-md border bg-muted/30 px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Show technical error
            </summary>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {rawError}
            </p>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function friendlyTrendsError(raw: string | null): string {
  if (!raw) {
    return "The AI hit a snag while reading what's trending. Try again — most errors here are temporary.";
  }
  const lowered = raw.toLowerCase();
  if (lowered.includes("truncated") || lowered.includes("max_tokens")) {
    return "The AI had so much to say it ran past its limit on the first try. We've already fixed the ceiling — try again and it'll complete.";
  }
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI was under heavy load just now. Wait a moment and try again — that's a temporary blip on their end.";
  }
  if (lowered.includes("429") || lowered.includes("rate")) {
    return "We hit the AI provider's rate limit, or Google Trends throttled us. Wait 30 seconds and try again.";
  }
  if (lowered.includes("non-json") || lowered.includes("validation")) {
    return "The AI's response didn't match what we expected. This is usually fixed on the second try.";
  }
  return "Try again — most errors here are transient. Both trend sources are best-effort.";
}
