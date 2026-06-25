"use client";

import {
  ArchiveRestore,
  BeakerIcon,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Hash,
  Loader2,
  Minus,
  RefreshCw,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type CampaignExperiment,
  type ExperimentStatus,
  type LearningEvent,
  type LearningRunResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Campaign Learning Lab. Three sections stacked top → bottom:
 *
 *  1. Findings — high-confidence LearningEvents. These are what the next
 *     generation inherits. The actual moat.
 *  2. Experiments — every recorded generation, newest first. Lets the
 *     user audit "which generation caused that finding?"
 *  3. Run-the-engine controls — a single button that asks Gemini to
 *     re-cluster everything.
 *
 * Deliberately NOT styled like a/b testing tools (Optimizely, VWO). No
 * sample-size calculator, no statistical-significance gates. This is
 * an EVIDENCE log for a creative process, not a hypothesis tester.
 */

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; message: string };

const STATUS_LABEL: Record<ExperimentStatus, string> = {
  pending: "Just generated",
  live: "Distributed",
  completed: "Has results",
  archived: "Archived",
};

const STATUS_TONE: Record<ExperimentStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  live: "bg-blue-500/15 text-blue-600 dark:text-blue-300",
  completed: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  archived: "bg-muted/40 text-muted-foreground",
};

export function CampaignLab() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [experiments, setExperiments] = useState<CampaignExperiment[]>([]);
  const [events, setEvents] = useState<LearningEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<LearningRunResult | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const [exps, evts] = await Promise.all([
        api.learning.experiments({ limit: 100 }),
        api.learning.events({ only_active: true, limit: 50 }),
      ]);
      setExperiments(exps);
      setEvents(evts);
      setState({ kind: "ready" });
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : "Couldn't load the lab. Try again in a moment.";
      setState({ kind: "error", message: msg });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleAnalyze = useCallback(async () => {
    setRunning(true);
    try {
      const result = await api.learning.analyze();
      setLastRun(result);
      await load();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.message
          : "Couldn't run the engine. Try again.";
      setState({ kind: "error", message: msg });
    } finally {
      setRunning(false);
    }
  }, [load]);

  const handleArchiveEvent = useCallback(
    async (id: string) => {
      try {
        await api.learning.archiveEvent(id);
        await load();
      } catch {
        // Best-effort — let the user retry. No toast system to plug into yet.
      }
    },
    [load],
  );

  const eventsByVariable = useMemo(() => {
    const m = new Map<string, LearningEvent[]>();
    for (const e of events) {
      const k = e.variable;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(e);
    }
    return Array.from(m.entries());
  }, [events]);

  if (state.kind === "loading") {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading the lab…
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <Card>
        <CardContent className="py-8 text-sm text-muted-foreground">
          {state.message}
          <Button
            variant="outline"
            size="sm"
            className="ml-3"
            onClick={() => void load()}
          >
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* ----- Run engine ----- */}
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <FlaskConical className="h-4 w-4" />
              Re-cluster what you&apos;ve generated
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              The engine reads every experiment + its results and surfaces 0-6
              evidence-backed findings. Findings under{" "}
              <span className="font-mono">n=3</span> are hidden.
            </p>
          </div>
          <Button
            onClick={() => void handleAnalyze()}
            disabled={running || experiments.length < 3}
            size="sm"
          >
            {running ? (
              <>
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                Thinking…
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-3.5 w-3.5" />
                Re-analyze
              </>
            )}
          </Button>
        </CardHeader>
        {(lastRun || experiments.length < 3) && (
          <CardContent className="border-t pt-4 text-sm text-muted-foreground">
            {experiments.length < 3 ? (
              <p>
                Generate at least 3 pieces (ads, reels, pages) before the engine
                has enough to compare. You have{" "}
                <span className="font-mono">{experiments.length}</span> so far.
              </p>
            ) : lastRun ? (
              <p>
                Last run:{" "}
                <span className="font-medium text-foreground">
                  {lastRun.events_created}
                </span>{" "}
                finding(s) created
                {lastRun.events_superseded > 0
                  ? `, ${lastRun.events_superseded} superseded`
                  : ""}
                ; considered{" "}
                <span className="font-mono">
                  {lastRun.experiments_considered}
                </span>{" "}
                experiments.
              </p>
            ) : null}
          </CardContent>
        )}
      </Card>

      {/* ----- Findings ----- */}
      <Card>
        <CardHeader className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <Trophy className="h-4 w-4 text-amber-500" />
            Findings the next generation inherits
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Each finding is one line the AI will see on the next ad or reel it
            writes. We show only{" "}
            <span className="font-mono">confidence ≥ 0.55</span> and{" "}
            <span className="font-mono">n ≥ 3</span> here, since the rest aren&apos;t
            trustworthy enough to feed back.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {eventsByVariable.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No findings yet — generate a handful of pieces, wait for results,
              then click <span className="font-medium">Re-analyze</span>.
            </p>
          )}
          {eventsByVariable.map(([variable, vs]) => (
            <div key={variable} className="space-y-2">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                <Hash className="h-3 w-3" />
                {variable}
              </div>
              {vs.map((ev) => (
                <FindingRow
                  key={ev.id}
                  event={ev}
                  onArchive={() => void handleArchiveEvent(ev.id)}
                />
              ))}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ----- Experiments ----- */}
      <Card>
        <CardHeader className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <BeakerIcon className="h-4 w-4" />
            Experiments (every generation we&apos;ve recorded)
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Click a row to see the creative dimensions we chose and any
            matching findings the engine has surfaced.
          </p>
        </CardHeader>
        <CardContent>
          {experiments.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing yet. Generate a piece in any studio — it&apos;ll show up
              here as soon as it&apos;s written.
            </p>
          ) : (
            <div className="space-y-2">
              {experiments.map((exp) => (
                <ExperimentRow
                  key={exp.id}
                  experiment={exp}
                  open={!!expanded[exp.id]}
                  onToggle={() =>
                    setExpanded((m) => ({ ...m, [exp.id]: !m[exp.id] }))
                  }
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------
//  Sub-components
// ---------------------------------------------------------------------

function FindingRow({
  event,
  onArchive,
}: {
  event: LearningEvent;
  onArchive: () => void;
}) {
  const directionIcon =
    event.direction === "positive" ? (
      <TrendingUp className="h-4 w-4 text-emerald-500" />
    ) : event.direction === "negative" ? (
      <TrendingDown className="h-4 w-4 text-rose-500" />
    ) : (
      <Minus className="h-4 w-4 text-muted-foreground" />
    );
  return (
    <div className="flex items-start gap-3 rounded-md border bg-card p-3">
      <div className="mt-0.5">{directionIcon}</div>
      <div className="flex-1 space-y-1.5">
        <p className="text-sm font-medium leading-snug">{event.finding}</p>
        {event.evidence.length > 0 && (
          <ul className="space-y-0.5 text-xs text-muted-foreground">
            {event.evidence.slice(0, 4).map((bullet, i) => (
              <li key={i}>— {bullet}</li>
            ))}
          </ul>
        )}
        <div className="flex items-center gap-3 pt-1 text-[11px] uppercase tracking-wide text-muted-foreground">
          <span className="flex items-center gap-1">
            <ShieldCheck className="h-3 w-3" />
            confidence {(event.confidence_score * 100).toFixed(0)}%
          </span>
          <span className="font-mono">n={event.sample_size}</span>
          {event.effect_size != null && (
            <span className="font-mono">
              effect ×{event.effect_size.toFixed(1)}
            </span>
          )}
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 px-2 text-xs text-muted-foreground"
        onClick={onArchive}
        title="Dismiss this finding so it stops feeding the generators"
      >
        <ArchiveRestore className="mr-1 h-3 w-3" />
        Dismiss
      </Button>
    </div>
  );
}

function ExperimentRow({
  experiment,
  open,
  onToggle,
}: {
  experiment: CampaignExperiment;
  open: boolean;
  onToggle: () => void;
}) {
  const created = experiment.created_at?.slice(0, 10) ?? "";
  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/50"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
            STATUS_TONE[experiment.status],
          )}
        >
          {STATUS_LABEL[experiment.status]}
        </span>
        <span className="text-xs font-medium text-muted-foreground">
          {experiment.source_asset_type}
          {experiment.platform ? ` · ${experiment.platform}` : ""}
        </span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {created}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t bg-muted/20 px-3 py-3 text-xs">
          {experiment.hypothesis && (
            <div className="space-y-0.5">
              <div className="flex items-center gap-1 uppercase tracking-wide text-muted-foreground">
                <Target className="h-3 w-3" />
                What the AI was going for
              </div>
              <p className="text-foreground">{experiment.hypothesis}</p>
            </div>
          )}
          {humanizedLabChoices(experiment.variable_choices).length > 0 && (
            <div className="space-y-0.5">
              <div className="uppercase tracking-wide text-muted-foreground">
                How the AI built this
              </div>
              <ul className="space-y-0.5 text-muted-foreground">
                {humanizedLabChoices(experiment.variable_choices).map((line, i) => (
                  <li key={i}>— {line}</li>
                ))}
              </ul>
            </div>
          )}
          {experiment.inherited_patterns.length > 0 && (
            <div className="space-y-0.5">
              <div className="uppercase tracking-wide text-muted-foreground">
                What we learned from your past posts
              </div>
              <ul className="space-y-0.5 text-muted-foreground">
                {experiment.inherited_patterns.slice(0, 4).map((p, i) => (
                  <li key={i}>— {p}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Founder Experience Audit (C10): translate the raw `variable_choices`
 * dict into plain-English sentences. Lab is technically a power-user
 * surface, but the chips were unreadable for anyone (`tone=playful`,
 * `trend_grounded=true`). This emits the sentences a founder would
 * say out loud.
 */
function humanizedLabChoices(choices: Record<string, unknown>): string[] {
  const out: string[] = [];
  const get = (k: string) => {
    const v = choices[k];
    return typeof v === "string" && v.trim() ? v.trim() : null;
  };
  const truthy = (k: string) => choices[k] === true;

  const platform = get("platform");
  const contentType = get("content_type");
  const adType = get("ad_type");
  const visualType = get("visual_type");
  const objective = get("objective");
  const tone = get("tone");
  const audienceOverride = get("audience_override");

  if (contentType && platform) {
    out.push(`Wrote a ${contentType.replace(/_/g, " ")} for ${platform}.`);
  } else if (adType) {
    out.push(`Drafted a ${adType.replace(/_/g, " ")} ad.`);
  } else if (visualType && platform) {
    out.push(`Designed a ${visualType.replace(/_/g, " ")} for ${platform}.`);
  } else if (platform) {
    out.push(`Built for ${platform}.`);
  }
  if (objective) out.push(`Goal: ${objective.replace(/_/g, " ")}.`);
  if (tone) out.push(`Voice: ${tone.toLowerCase()}.`);
  if (audienceOverride) out.push(`Targeted: ${audienceOverride}.`);
  if (truthy("trend_grounded")) out.push("Built on a trend that's heating up right now.");
  if (truthy("has_landing_page")) out.push("Wired to a lead page so clicks turn into contacts.");
  return out;
}
