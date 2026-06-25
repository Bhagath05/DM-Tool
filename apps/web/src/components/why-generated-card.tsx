"use client";

import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Microscope,
  Minus,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import {
  ApiError,
  api,
  type ExperimentProvenance,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Shows *why* this particular asset was generated the way it was:
 *
 *   1. The hypothesis the AI was working from at gen time.
 *   2. The variable choices it actually made (hook, format, tone…).
 *   3. The patterns it inherited from Social Intelligence.
 *   4. Any matching LearningEvents the engine has surfaced about those
 *      variables since.
 *
 * Renders nothing (returns null) when no experiment was recorded for
 * this asset — that's the right default for legacy generations from
 * before Phase 1B shipped. The card never blocks the rest of the
 * result-card from rendering.
 *
 * Default-collapsed so it doesn't shout. The dimensions matter when the
 * user is curious; otherwise they're noise.
 */
export function WhyGeneratedCard({
  sourceAssetId,
  className,
}: {
  sourceAssetId: string;
  className?: string;
}) {
  const [state, setState] = useState<
    | { kind: "loading" }
    | { kind: "ready"; prov: ExperimentProvenance }
    | { kind: "absent" }
    | { kind: "error"; message: string }
  >({ kind: "loading" });
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const prov = await api.learning.provenance(sourceAssetId);
      setState({ kind: "ready", prov });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        // Asset was generated before Phase 1B — perfectly fine, just hide.
        setState({ kind: "absent" });
        return;
      }
      setState({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Couldn't load provenance.",
      });
    }
  }, [sourceAssetId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") return null;
  if (state.kind === "absent") return null;
  if (state.kind === "error") return null;

  const { experiment, matched_events, latest_result } = state.prov;
  const hasAnything =
    !!experiment.hypothesis ||
    Object.keys(experiment.variable_choices).length > 0 ||
    experiment.inherited_patterns.length > 0 ||
    matched_events.length > 0;
  if (!hasAnything) return null;

  return (
    <Card className={cn("border-dashed", className)}>
      <CardContent className="space-y-2 p-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-2 text-left text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground"
        >
          {open ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <Microscope className="h-3 w-3" />
          Why we generated this
          {matched_events.length > 0 && (
            <span className="ml-auto rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium normal-case tracking-normal text-amber-700 dark:text-amber-300">
              {matched_events.length} matching finding
              {matched_events.length === 1 ? "" : "s"}
            </span>
          )}
        </button>

        {open && (
          <div className="space-y-3 pt-1 text-xs">
            {experiment.hypothesis && (
              <div className="space-y-0.5">
                <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <Target className="h-3 w-3" />
                  What the AI was going for
                </div>
                <p>{experiment.hypothesis}</p>
              </div>
            )}

            {humanizedChoices(experiment.variable_choices).length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  How the AI built this
                </div>
                <ul className="space-y-0.5 text-muted-foreground">
                  {humanizedChoices(experiment.variable_choices).map((line, i) => (
                    <li key={i}>— {line}</li>
                  ))}
                </ul>
              </div>
            )}

            {experiment.inherited_patterns.length > 0 && (
              <div className="space-y-0.5">
                <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                  <Sparkles className="h-3 w-3" />
                  What we learned from your past posts
                </div>
                <ul className="space-y-0.5 text-muted-foreground">
                  {experiment.inherited_patterns.slice(0, 4).map((p, i) => (
                    <li key={i}>— {p}</li>
                  ))}
                </ul>
              </div>
            )}

            {matched_events.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  What worked before for similar posts
                </div>
                {matched_events.map((ev) => (
                  <FindingMini key={ev.id} ev={ev} />
                ))}
              </div>
            )}

            {latest_result && (
              <div className="space-y-0.5 border-t pt-2">
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  How this is doing so far
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {humanizePerformance(latest_result)}
                </p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FindingMini({ ev }: { ev: ExperimentProvenance["matched_events"][number] }) {
  const icon =
    ev.direction === "positive" ? (
      <TrendingUp className="h-3 w-3 text-emerald-500" />
    ) : ev.direction === "negative" ? (
      <TrendingDown className="h-3 w-3 text-rose-500" />
    ) : (
      <Minus className="h-3 w-3 text-muted-foreground" />
    );
  const confidenceLabel = confidenceTier(ev.confidence_score);
  return (
    <div className="flex items-start gap-2 rounded border bg-muted/30 px-2 py-1.5">
      <div className="mt-0.5">{icon}</div>
      <div className="flex-1 space-y-0.5">
        <p className="leading-snug">{ev.finding}</p>
        <div className="flex items-center gap-2 text-[10px] tracking-wide text-muted-foreground">
          <span className="flex items-center gap-0.5">
            <ShieldCheck className="h-3 w-3" />
            {confidenceLabel} confidence
          </span>
          <span>· based on {ev.sample_size} past posts</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Founder Experience Audit (C10): translate the raw `variable_choices`
 * dict into plain-English sentences. The previous UI dumped chips like
 * `tone=playful` and `trend_grounded=true` straight from the database —
 * non-marketers had no chance of parsing them. Every line below is the
 * sentence a founder would actually say in conversation. Unknown keys
 * are skipped (we never want raw `snake_case=value` leaking through).
 */
function humanizedChoices(choices: Record<string, unknown>): string[] {
  const out: string[] = [];

  const platform = stringFrom(choices, "platform");
  const contentType = stringFrom(choices, "content_type");
  const adType = stringFrom(choices, "ad_type");
  const visualType = stringFrom(choices, "visual_type");
  const objective = stringFrom(choices, "objective");
  const tone = stringFrom(choices, "tone");
  const audienceOverride = stringFrom(choices, "audience_override");
  const trendGrounded = boolFrom(choices, "trend_grounded");
  const hasLandingPage = boolFrom(choices, "has_landing_page");

  if (contentType && platform) {
    out.push(`Wrote a ${prettyContentType(contentType)} for ${prettyPlatform(platform)}.`);
  } else if (adType) {
    out.push(`Drafted a ${prettyAdType(adType)} ad.`);
  } else if (visualType && platform) {
    out.push(`Designed a ${prettyVisualType(visualType)} for ${prettyPlatform(platform)}.`);
  } else if (platform) {
    out.push(`Built for ${prettyPlatform(platform)}.`);
  }

  if (objective) {
    out.push(`Goal: ${prettyObjective(objective)}.`);
  }

  if (tone) {
    out.push(`Voice: ${prettyTone(tone)}.`);
  }

  if (audienceOverride) {
    out.push(`Targeted: ${audienceOverride}.`);
  }

  if (trendGrounded) {
    out.push("Built on a trend that's heating up right now.");
  }

  if (hasLandingPage) {
    out.push("Wired to a lead page so clicks turn into contacts.");
  }

  return out;
}

function stringFrom(d: Record<string, unknown>, k: string): string | null {
  const v = d[k];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function boolFrom(d: Record<string, unknown>, k: string): boolean {
  return d[k] === true;
}

function prettyPlatform(p: string): string {
  const m: Record<string, string> = {
    instagram: "Instagram",
    facebook: "Facebook",
    linkedin: "LinkedIn",
    tiktok: "TikTok",
    youtube: "YouTube",
    twitter: "X (Twitter)",
    x: "X (Twitter)",
    threads: "Threads",
    google: "Google",
    web: "your website",
    email: "email",
  };
  return m[p.toLowerCase()] ?? p;
}

function prettyContentType(t: string): string {
  const m: Record<string, string> = {
    post: "social post",
    caption: "caption",
    story: "story",
    reel: "short video script",
    short: "short video script",
    blog: "blog outline",
    email: "email",
    newsletter: "newsletter",
  };
  return m[t.toLowerCase()] ?? t.replace(/_/g, " ");
}

function prettyAdType(t: string): string {
  const m: Record<string, string> = {
    facebook: "Facebook",
    instagram: "Instagram",
    google_search: "Google Search",
    google_display: "Google Display",
    youtube: "YouTube",
    linkedin: "LinkedIn",
    tiktok: "TikTok",
  };
  return m[t.toLowerCase()] ?? t.replace(/_/g, " ");
}

function prettyVisualType(t: string): string {
  const m: Record<string, string> = {
    static: "single image",
    carousel: "carousel",
    story: "story graphic",
    reel_cover: "video cover",
    ad_creative: "ad image",
  };
  return m[t.toLowerCase()] ?? t.replace(/_/g, " ");
}

function prettyObjective(o: string): string {
  const m: Record<string, string> = {
    leads: "get more leads",
    awareness: "get the brand seen",
    traffic: "drive people to the site",
    engagement: "spark conversation",
    conversions: "close more sales",
    sales: "close more sales",
    app_installs: "get app installs",
  };
  return m[o.toLowerCase()] ?? o.replace(/_/g, " ");
}

function prettyTone(t: string): string {
  // Tone is already human-readable in most cases (e.g. "warm and confident"),
  // so we just lowercase it for sentence flow.
  return t.toLowerCase();
}

/**
 * Founder Experience Audit (C11): turn the raw `imp · eng · leads` line
 * into a sentence a non-marketer can read in one beat. We never use the
 * abbreviation "imp" — founders read it as a misspelling.
 */
function humanizePerformance(r: {
  impressions: number;
  engagement_rate: number;
  leads: number;
}): string {
  const seen = formatCount(r.impressions, "person", "people");
  const engaged = `${(r.engagement_rate * 100).toFixed(1)}% engaged`;
  const leadsLine =
    r.leads === 0
      ? "no leads yet"
      : `${r.leads} ${r.leads === 1 ? "lead" : "leads"}`;
  return `${seen} saw it · ${engaged} · ${leadsLine}.`;
}

function formatCount(n: number, singular: string, plural: string): string {
  return `${n.toLocaleString()} ${n === 1 ? singular : plural}`;
}

function confidenceTier(score: number): string {
  if (score >= 0.75) return "High";
  if (score >= 0.5) return "Moderate";
  return "Low";
}
