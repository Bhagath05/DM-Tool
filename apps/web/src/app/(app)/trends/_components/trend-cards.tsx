"use client";

import { Hash, Lightbulb, Megaphone, ShieldCheck, TrendingUp } from "lucide-react";

import {
  QuickGenerateButton,
  quickGenerateFromTrend,
} from "@/components/quick-generate";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { TrendAnalysis, TrendingTopic } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Founder Experience Audit (Batch 3 / C5 + C6 + H8).
 *
 * The previous version of this screen treated trends like a research
 * dashboard — every topic was a `relevance_score` integer next to a
 * `why_it_matters` blurb and a bullet list of "suggested_angles". A
 * non-marketer reading it had no idea what to actually do.
 *
 * The screen now follows the Opportunity Center pattern: each trend
 * answers the same four questions every other AI surface answers,
 * with confidence rendered as a plain-language tier instead of a
 * naked integer.
 *
 *   What is happening?      → topic + why_it_matters
 *   What should I do?       → recommended_action
 *   What result can I expect? → expected_result
 *   Confidence              → fit tier (Strong / Worth a shot / Speculative)
 *   Why?                    → reason
 *
 * Section headers across the page were also rewritten in founder
 * language ("Trend landscape" → "What's heating up", "Marketing angles"
 * → "Angles to lean into this week", "Hashtag clusters" → "Hashtags
 * worth using").
 */
export function TrendCards({ analysis }: { analysis: TrendAnalysis }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">What's heating up right now</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-relaxed">
          {analysis.summary}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center gap-2">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">
            Trends to act on this week
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {analysis.trending_topics.map((t) => (
            <TrendingTopicCard key={t.topic} topic={t} />
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Lightbulb className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Things you could post</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {analysis.content_ideas.map((idea, i) => (
              <div
                key={i}
                className="border-b border-border pb-3 last:border-0 last:pb-0"
              >
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
                  <span className="rounded bg-muted px-1.5 py-0.5">
                    {idea.platform}
                  </span>
                  <span>·</span>
                  <span>{idea.format}</span>
                </div>
                <div className="mt-2 text-sm font-medium leading-snug">
                  “{idea.hook}”
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {idea.description}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Megaphone className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">
              Angles to lean into this week
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {analysis.marketing_angles.map((a, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center gap-2">
          <Hash className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">Hashtags worth using</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {analysis.hashtag_clusters.map((c) => (
            <div key={c.theme}>
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {c.theme}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {c.hashtags.map((h) => (
                  <span
                    key={h}
                    className="rounded-md bg-muted px-2 py-0.5 text-xs"
                  >
                    {h.startsWith("#") ? h : `#${h}`}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * One trend rendered as the same advisory card every other AI surface
 * uses. When the LLM hasn't populated the new advisory fields (legacy
 * reports created before Batch 3 shipped), we fall back to the old
 * topic + why + angles view so the screen never goes blank.
 */
function TrendingTopicCard({ topic }: { topic: TrendingTopic }) {
  const hasAdvisory = Boolean(
    topic.recommended_action && topic.expected_result && topic.reason,
  );

  // Confidence tier — turns a 1-100 integer into a phrase a founder
  // actually parses. Mirrors the Opportunity Center's confidence
  // language so the two screens feel like one product voice.
  const tier = confidenceTier(topic.confidence);

  return (
    <div className="border-b border-border pb-4 last:border-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-semibold">{topic.topic}</div>
        {tier && <ConfidenceTierPill tier={tier} />}
      </div>

      <Section label="What is happening">
        <p className="text-sm text-foreground/90">{topic.why_it_matters}</p>
      </Section>

      {hasAdvisory ? (
        <>
          <Section label="What you should do">
            <p className="text-sm font-medium text-foreground">
              {topic.recommended_action}
            </p>
          </Section>

          <Section label="What you can expect">
            <p className="text-sm text-foreground/90">{topic.expected_result}</p>
          </Section>

          {topic.reason && (
            <Section label="Why we believe it">
              <p className="text-xs text-muted-foreground leading-relaxed">
                {topic.reason}
              </p>
            </Section>
          )}

          {/* Phase 8 — one-click execution. Only surfaces when the
              trend has the full Constitution advisory contract; the
              Generate button never appears without a "why" the
              founder can read above the result. */}
          <TrendQuickGenerate topic={topic} />
        </>
      ) : (
        // Legacy report fallback — surface the suggested angles list so
        // an old report still gives the founder something concrete.
        <Section label="Angles you could use">
          <ul className="space-y-1">
            {topic.suggested_angles.map((a, i) => (
              <li key={i} className="flex gap-2 text-xs text-foreground/80">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-primary" />
                {a}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function TrendQuickGenerate({ topic }: { topic: TrendingTopic }) {
  const ctx = quickGenerateFromTrend(topic);
  if (!ctx) return null;
  return (
    <div className="mt-3 flex">
      <QuickGenerateButton
        context={ctx}
        label="Generate a post"
        data-testid="trend-quick-generate"
      />
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-3 space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      {children}
    </div>
  );
}

type ConfidenceTier = "strong" | "worth-a-shot" | "speculative";

function confidenceTier(score: number | null): ConfidenceTier | null {
  if (score == null) return null;
  if (score >= 75) return "strong";
  if (score >= 50) return "worth-a-shot";
  return "speculative";
}

const TIER_LABEL: Record<ConfidenceTier, string> = {
  strong: "Strong fit",
  "worth-a-shot": "Worth a shot",
  speculative: "Speculative",
};

function ConfidenceTierPill({ tier }: { tier: ConfidenceTier }) {
  return (
    <span
      className={cn(
        "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        tier === "strong" && "bg-primary text-primary-foreground",
        tier === "worth-a-shot" && "bg-muted text-foreground",
        tier === "speculative" && "bg-muted text-muted-foreground",
      )}
    >
      <ShieldCheck className="h-3 w-3" />
      {TIER_LABEL[tier]}
    </span>
  );
}
