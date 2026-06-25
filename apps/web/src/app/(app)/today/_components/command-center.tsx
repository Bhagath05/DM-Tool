"use client";

/**
 * Phase 7 — Founder Daily Command Center.
 *
 * Six-section advisory page that aggregates the existing AI surfaces
 * (Lead Intelligence, Opportunity Center, Trends) into one founder-
 * first morning view. No new LLM calls, no new endpoints — this file
 * is a pure composer.
 *
 *   SECTION 1  Hero AI recommendation     (highest-leverage action)
 *   SECTION 2  Customers to contact       (top 3 prioritized leads)
 *   SECTION 3  Growth opportunity         (best content opportunity)
 *   SECTION 4  Trend to act on            (top advisory trend)
 *   SECTION 5  Ad opportunity             (only when one exists)
 *   SECTION 6  Expected business impact   (deterministic recap)
 *
 * Architectural choices:
 *
 * - **Parallel fetch.** All three APIs fire on mount. We never call
 *   them sequentially because the page renders nothing until all three
 *   resolve — single round-trip latency for the founder.
 *
 * - **409 = no-profile, page-wide.** If either Lead Intelligence or the
 *   Opportunity Center returns 409 the whole page degrades to the
 *   "finish onboarding" empty state. Founder onboarding gates the
 *   product, so showing a partial /today before profile setup would
 *   be misleading.
 *
 * - **Trends are best-effort.** `api.trends.get()` returns null when
 *   no report exists yet (cold-start). The trend section then renders
 *   a one-line "Generate trends" nudge instead of blocking the page.
 *
 * - **30-min localStorage cache.** Mirrors the Lead Intelligence and
 *   Opportunity Center caches so reopening /today within the same
 *   session never re-bills three LLM-backed endpoints.
 *
 * - **Hero selection is deterministic.** A `pickHero` function picks
 *   the single advisory shown at the top using transparent rules
 *   (hot leads beat everything; otherwise highest confidence wins).
 *   See `pickHero` JSDoc + tests for the full table.
 */

import {
  ArrowRight,
  Compass,
  Inbox,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  QuickGenerateButton,
  type QuickGenerateContext,
  quickGenerateFromOpportunity,
  quickGenerateFromTrend,
} from "@/components/quick-generate";
import { AiRecommendation } from "@/components/ui/business-metric";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  api,
  type LeadIntelligenceReport,
  type LeadPriorityItem,
  type Opportunity,
  type OpportunityCenterReport,
  type TrendReport,
  type TrendingTopic,
} from "@/lib/api";
import {
  intelligenceToAdvisoryTrend,
  intelligenceToOpportunityReport,
  type AdvisorEmptyPlan,
  type DailyBrief,
  type IntelligenceReport,
} from "@/lib/intelligence-adapter";
import { cn } from "@/lib/utils";

import { PriorityRow } from "../../leads/_components/intelligence-card";
import {
  OpportunityCard,
  buildGeneratorHref,
} from "../../opportunities/_components/opportunity-card";

const CACHE_KEY = "aicmo:today:v2";
const CACHE_MAX_AGE_MS = 30 * 60 * 1000; // 30 min — matches sibling screens.

/** Test hook — lets vitest wipe the localStorage cache between cases. */
export const __TODAY_CACHE_KEY = CACHE_KEY;

interface CombinedReport {
  leads: LeadIntelligenceReport;
  opportunities: OpportunityCenterReport;
  /** Intelligence-backed trend advisory (replaces separate trends fetch). */
  intelligenceTrend: ReturnType<typeof intelligenceToAdvisoryTrend>;
  dailyBrief: IntelligenceReport["daily_brief"];
  trend: TrendReport | null;
}

type State =
  | { kind: "loading" }
  | { kind: "no-profile" }
  | { kind: "setup-needed"; plan: AdvisorEmptyPlan }
  | { kind: "error"; message: string }
  | { kind: "ready"; report: CombinedReport; loadedAt: number };

export function CommandCenter() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    async ({ force = false }: { force?: boolean } = {}) => {
      if (!force) {
        const cached = readCache();
        if (cached) {
          setState({
            kind: "ready",
            report: cached.data,
            loadedAt: cached.ts,
          });
          return;
        }
      }
      setRefreshing(force);
      if (!force) setState({ kind: "loading" });
      try {
        const [leadsResult, intelligenceResult] = await Promise.allSettled([
          api.leads.intelligence(),
          api.advisor.intelligence(),
        ]);

        if (isNoProfileError(leadsResult) || isNoProfileError(intelligenceResult)) {
          setState({ kind: "no-profile" });
          return;
        }

        if (leadsResult.status === "rejected") {
          throw leadsResult.reason;
        }
        if (intelligenceResult.status === "rejected") {
          throw intelligenceResult.reason;
        }

        const intelligence = intelligenceResult.value;
        if (!intelligence.ready && intelligence.empty) {
          setState({ kind: "setup-needed", plan: intelligence.empty });
          return;
        }

        const report: CombinedReport = {
          leads: leadsResult.value,
          opportunities: intelligenceToOpportunityReport(intelligence),
          intelligenceTrend: intelligenceToAdvisoryTrend(intelligence.trend),
          dailyBrief: intelligence.daily_brief ?? null,
          trend: null,
        };
        const ts = Date.now();
        writeCache({ data: report, ts });
        setState({ kind: "ready", report, loadedAt: ts });
      } catch (e) {
        setState({
          kind: "error",
          message:
            e instanceof Error
              ? friendlyError(e.message)
              : "Something went wrong assembling today's view.",
        });
      } finally {
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (state.kind === "loading") {
    return <LoadingShell />;
  }
  if (state.kind === "no-profile") {
    return <NoProfileCard />;
  }
  if (state.kind === "setup-needed") {
    return <SetupNeededCard plan={state.plan} onRetry={() => void load({ force: true })} />;
  }
  if (state.kind === "error") {
    return (
      <ErrorCard
        message={state.message}
        retrying={refreshing}
        onRetry={() => void load({ force: true })}
      />
    );
  }

  return (
    <ReadyView
      report={state.report}
      loadedAt={state.loadedAt}
      refreshing={refreshing}
      onRefresh={() => void load({ force: true })}
    />
  );
}

// ---------------------------------------------------------------------
//  Ready state — the six-section layout
// ---------------------------------------------------------------------

function ReadyView({
  report,
  loadedAt,
  refreshing,
  onRefresh,
}: {
  report: CombinedReport;
  loadedAt: number;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const hero = useMemo(() => pickHero(report), [report]);
  const topLeads = useMemo(
    () => report.leads.priorities.slice(0, 3),
    [report.leads.priorities],
  );
  const topContentOpp = useMemo(
    () => firstWithAdvisory(report.opportunities.content_opportunities),
    [report.opportunities.content_opportunities],
  );
  const topAdOpp = useMemo(
    () => firstWithAdvisory(report.opportunities.ad_opportunities),
    [report.opportunities.ad_opportunities],
  );
  const topTrend = useMemo(
    () => report.intelligenceTrend ?? pickAdvisoryTrend(report.trend),
    [report.intelligenceTrend, report.trend],
  );

  // Phase 8 — one-click execution context for the hero. Derived from
  // the strongest underlying signal (top content opportunity, then
  // top advisory trend), with the founder-facing wording overridden
  // to the hero's own headline so what they click matches what they
  // see in the modal. Null when the hero is a leads recommendation
  // (the right next action there is to reply, not to post).
  const heroQuickGen = useMemo<QuickGenerateContext | null>(
    () => deriveHeroQuickGenerate({ hero, topContentOpp, topTrend }),
    [hero, topContentOpp, topTrend],
  );

  // Quick Generate for the trend section uses the same helper Trends
  // uses on its own page — consistent wording + a single source of
  // truth for which trend topics qualify.
  const trendQuickGen = useMemo<QuickGenerateContext | null>(
    () =>
      topTrend
        ? quickGenerateFromTrend({
            topic: topTrend.topic,
            why_it_matters: topTrend.what_is_happening,
            suggested_angles: [],
            relevance_score: null,
            recommended_action: topTrend.recommended_action,
            expected_result: topTrend.expected_result,
            confidence: topTrend.confidence,
            reason: topTrend.reason,
          })
        : null,
    [topTrend],
  );

  return (
    <div className="space-y-6" data-testid="today-command-center">
      <RefreshStrip
        loadedAt={loadedAt}
        refreshing={refreshing}
        onRefresh={onRefresh}
      />

      {report.dailyBrief && (
        <DailyBriefStrip brief={report.dailyBrief} />
      )}

      {/* SECTION 1 — Hero AI recommendation */}
      <HeroSection hero={hero} quickGen={heroQuickGen} />

      {/* SECTION 2 — Customers to contact */}
      <ContactLeadsSection
        leads={topLeads}
        totalPriorities={report.leads.priorities.length}
        hotCount={report.leads.counts.hot_count}
      />

      {/* SECTION 3 — Growth opportunity */}
      <GrowthOpportunitySection opportunity={topContentOpp} />

      {/* SECTION 4 — Trend to act on */}
      <TrendSection
        trend={topTrend}
        trendReport={report.trend}
        quickGen={trendQuickGen}
      />

      {/* SECTION 5 — Ad opportunity (conditional) */}
      {topAdOpp && <AdOpportunitySection opportunity={topAdOpp} />}

      {/* SECTION 6 — Expected business impact */}
      <ExpectedImpactSection
        hero={hero}
        leadCount={topLeads.length}
        leadExpected={topLeads[0]?.expected_result ?? null}
        contentExpected={topContentOpp?.expected_result ?? null}
        trendExpected={topTrend?.expected_result ?? null}
        adExpected={topAdOpp?.expected_result ?? null}
      />
    </div>
  );
}

// ---------------------------------------------------------------------
//  SECTION 1 — Hero
// ---------------------------------------------------------------------

const HERO_SOURCE_LABEL: Record<HeroPick["source"], string> = {
  leads: "From your inbox",
  opportunities: "From your growth signals",
  trend: "From what's trending right now",
};

function DailyBriefStrip({ brief }: { brief: DailyBrief }) {
  return (
    <Card data-testid="today-daily-brief">
      <CardContent className="space-y-2 pt-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          What happened
        </p>
        <p className="text-sm leading-relaxed">{brief.what_happened}</p>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Why
        </p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {brief.why_it_happened}
        </p>
      </CardContent>
    </Card>
  );
}

function HeroSection({
  hero,
  quickGen,
}: {
  hero: HeroPick;
  quickGen: QuickGenerateContext | null;
}) {
  return (
    <section className="space-y-2" data-testid="today-hero">
      <SectionHeader
        icon={<Compass className="h-4 w-4" />}
        eyebrow="Start here"
        title="The single most important thing to do today"
        sourceTag={HERO_SOURCE_LABEL[hero.source]}
        testIdSuffix="hero"
      />
      <AiRecommendation
        data-testid="today-hero-recommendation"
        whatIsHappening={hero.what}
        impactCategory={hero.impact}
        recommendation={hero.action}
        expectedResult={hero.expected}
        confidence={hero.confidence}
        reason={hero.reason}
      />

      {/* Phase 8 — one-click execution. The hero ships with a Generate
          button that opens the modal and auto-fires `api.content.
          generate` using the strongest underlying signal. Hidden when
          the hero is a leads recommendation (reply, don't post). */}
      {quickGen && (
        <div className="flex">
          <QuickGenerateButton
            context={quickGen}
            label="Generate this for me"
            data-testid="today-hero-quick-generate"
          />
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  SECTION 2 — Customers to contact
// ---------------------------------------------------------------------

function ContactLeadsSection({
  leads,
  totalPriorities,
  hotCount,
}: {
  leads: LeadPriorityItem[];
  totalPriorities: number;
  hotCount: number;
}) {
  const remaining = Math.max(0, totalPriorities - leads.length);
  return (
    <section className="space-y-3" data-testid="today-leads">
      <SectionHeader
        icon={<Inbox className="h-4 w-4" />}
        eyebrow="Today's contacts"
        title="Who to reply to first"
        testIdSuffix="leads"
      />

      {leads.length === 0 ? (
        <Card>
          <CardContent className="space-y-2 pt-6 text-sm text-muted-foreground">
            <p>
              No leads worth chasing right now — your inbox is calm. This is a
              good day to post, not to chase.
            </p>
            <Link
              href={"/leads" as never}
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              Open inbox
              <ArrowRight className="h-3 w-3" />
            </Link>
          </CardContent>
        </Card>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Three people are worth your time today
            {hotCount > 0 ? `, including ${hotCount} that are hot right now` : ""}.
            Reply in order — each row tells you exactly what to say and what
            to expect back.
          </p>
          <div className="space-y-2">
            {leads.map((lead) => (
              <PriorityRow
                key={lead.lead_id}
                item={lead}
                emphasized={lead.priority === "focus"}
              />
            ))}
          </div>
          <div className="flex items-center justify-between text-xs">
            {remaining > 0 ? (
              <span className="text-muted-foreground">
                {remaining} more lead{remaining === 1 ? "" : "s"} waiting in
                your inbox.
              </span>
            ) : (
              <span className="text-muted-foreground">
                That&apos;s everyone worth replying to today.
              </span>
            )}
            <Link
              href={"/leads" as never}
              className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              data-testid="today-leads-open-inbox"
            >
              Open inbox
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  SECTION 3 — Growth opportunity
// ---------------------------------------------------------------------

function GrowthOpportunitySection({
  opportunity,
}: {
  opportunity: Opportunity | null;
}) {
  return (
    <section className="space-y-3" data-testid="today-opportunity">
      <SectionHeader
        icon={<Sparkles className="h-4 w-4" />}
        eyebrow="Today's growth move"
        title="The best thing to post"
        testIdSuffix="opportunity"
      />

      {opportunity ? (
        <OpportunityCard opportunity={opportunity} />
      ) : (
        <EmptyInline
          body="No content opportunities lined up today. Open the Opportunity Center to refresh."
          linkLabel="Open Opportunities"
          href="/opportunities"
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  SECTION 4 — Trend to act on
// ---------------------------------------------------------------------

function TrendSection({
  trend,
  trendReport,
  quickGen,
}: {
  trend: AdvisoryTrend | null;
  trendReport: TrendReport | null;
  quickGen: QuickGenerateContext | null;
}) {
  return (
    <section className="space-y-3" data-testid="today-trend">
      <SectionHeader
        icon={<TrendingUp className="h-4 w-4" />}
        eyebrow="Today's trend"
        title="What to ride right now"
        testIdSuffix="trend"
      />

      {trend ? (
        <Card data-testid="today-trend-card">
          <CardContent className="space-y-4 pt-5">
            <h3 className="text-base font-semibold leading-snug">
              {trend.topic}
            </h3>
            <Block label="What's happening">{trend.what_is_happening}</Block>
            <Block label="Do this" accent>
              {trend.recommended_action}
            </Block>
            <Block label="What to expect">{trend.expected_result}</Block>
            <div className="flex flex-wrap items-center gap-2">
              <ConfidencePill confidence={trend.confidence} />
              <span
                className="text-[11px] italic text-muted-foreground"
                data-testid="today-trend-reason"
              >
                {trend.reason}
              </span>
              {/* Phase 8 — Generate now is the primary CTA. "See full
                  trend report" stays as a smaller secondary link for
                  founders who want context before posting. */}
              <div className="ml-auto flex items-center gap-2">
                {quickGen && (
                  <QuickGenerateButton
                    context={quickGen}
                    label="Generate a post"
                    data-testid="today-trend-quick-generate"
                  />
                )}
                <Button asChild size="sm" variant="ghost">
                  <Link href={"/trends" as never} prefetch={false}>
                    See full report
                    <ArrowRight className="h-3 w-3" />
                  </Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : trendReport && trendReport.status === "pending" ? (
        <EmptyInline
          body="The AI is still reading what's trending right now. Open Trends to watch it land."
          linkLabel="Open Trends"
          href="/trends"
        />
      ) : (
        <EmptyInline
          body="No trend report yet. Generate one to see what to ride this week."
          linkLabel="Open Trends"
          href="/trends"
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------
//  SECTION 5 — Ad opportunity (conditional)
// ---------------------------------------------------------------------

function AdOpportunitySection({ opportunity }: { opportunity: Opportunity }) {
  return (
    <section className="space-y-3" data-testid="today-ad">
      <SectionHeader
        icon={<Sparkles className="h-4 w-4" />}
        eyebrow="Today's paid move"
        title="The ad worth running"
        testIdSuffix="ad"
      />
      <OpportunityCard opportunity={opportunity} />
    </section>
  );
}

// ---------------------------------------------------------------------
//  SECTION 6 — Expected business impact
// ---------------------------------------------------------------------

function ExpectedImpactSection({
  hero,
  leadCount,
  leadExpected,
  contentExpected,
  trendExpected,
  adExpected,
}: {
  hero: HeroPick;
  leadCount: number;
  leadExpected: string | null;
  contentExpected: string | null;
  trendExpected: string | null;
  adExpected: string | null;
}) {
  const lines = [
    leadCount > 0 && leadExpected
      ? {
          label: `Reply to the top ${leadCount} ${
            leadCount === 1 ? "lead" : "leads"
          }`,
          expected: leadExpected,
          href: "/leads",
        }
      : null,
    contentExpected
      ? { label: "Post the growth move", expected: contentExpected, href: "/opportunities" }
      : null,
    trendExpected
      ? {
          label: "Ride the trend",
          expected: trendExpected,
          href: "/trends",
        }
      : null,
    adExpected
      ? {
          label: "Run the paid move",
          expected: adExpected,
          href: "/opportunities",
        }
      : null,
  ].filter((x): x is { label: string; expected: string; href: string } =>
    Boolean(x),
  );

  return (
    <section className="space-y-3" data-testid="today-impact">
      <SectionHeader
        icon={<Compass className="h-4 w-4" />}
        eyebrow="If you do all this today"
        title="What you can expect by the end of the week"
        testIdSuffix="impact"
      />

      <Card>
        <CardContent className="space-y-3 pt-5">
          <p className="text-sm leading-relaxed">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Headline ·{" "}
            </span>
            {hero.expected}
          </p>
          {lines.length > 0 && (
            <ul className="space-y-2 border-t pt-3">
              {lines.map((line, i) => (
                <li
                  key={i}
                  className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3"
                  data-testid={`today-impact-line-${i}`}
                >
                  <Link
                    href={line.href as never}
                    className="text-sm font-medium text-primary hover:underline sm:w-40 sm:shrink-0"
                  >
                    {line.label}
                  </Link>
                  <span className="text-sm text-foreground/85">
                    {line.expected}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="border-t pt-3 text-xs italic text-muted-foreground">
            Ranges, not promises — we calibrate against your own past
            results. Numbers tighten as you ship more.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}

// ---------------------------------------------------------------------
//  Subcomponents
// ---------------------------------------------------------------------

function SectionHeader({
  icon,
  eyebrow,
  title,
  sourceTag,
  testIdSuffix,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  sourceTag?: string;
  testIdSuffix: string;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-2">
      <div>
        <div
          className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
          data-testid={`today-section-eyebrow-${testIdSuffix}`}
        >
          {icon}
          {eyebrow}
        </div>
        <h2 className="text-lg font-semibold leading-snug tracking-tight">
          {title}
        </h2>
      </div>
      {sourceTag && (
        <span
          className="rounded-full border bg-muted/50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
          data-testid={`today-section-source-${testIdSuffix}`}
        >
          {sourceTag}
        </span>
      )}
    </header>
  );
}

function Block({
  label,
  children,
  accent,
}: {
  label: string;
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div
        className={cn(
          "text-[10px] font-semibold uppercase tracking-wide",
          accent ? "text-primary" : "text-muted-foreground",
        )}
      >
        {label}
      </div>
      <p
        className={cn(
          "text-sm leading-snug",
          accent && "font-medium text-foreground",
        )}
      >
        {children}
      </p>
    </div>
  );
}

function ConfidencePill({ confidence }: { confidence: number }) {
  const band = confidenceBand(confidence);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        band.cls,
      )}
      data-testid="today-trend-confidence"
    >
      {band.label} ({confidence}%)
    </span>
  );
}

function EmptyInline({
  body,
  linkLabel,
  href,
}: {
  body: string;
  linkLabel: string;
  href: string;
}) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5">
        <p className="text-sm text-muted-foreground">{body}</p>
        <Button asChild variant="outline" size="sm">
          <Link href={href as never} prefetch={false}>
            {linkLabel}
            <ArrowRight className="h-3 w-3" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function RefreshStrip({
  loadedAt,
  refreshing,
  onRefresh,
}: {
  loadedAt: number;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
      data-testid="today-refresh-strip"
    >
      <span>Built {formatRelative(loadedAt)} from your latest data.</span>
      <Button
        variant="ghost"
        size="sm"
        onClick={onRefresh}
        disabled={refreshing}
        data-testid="today-refresh"
      >
        {refreshing ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
        Refresh
      </Button>
    </div>
  );
}

function LoadingShell() {
  return (
    <Card data-testid="today-loading">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Loader2 className="h-4 w-4 animate-spin" />
          Building your day…
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Reading your inbox, your opportunities, and what&apos;s trending
        right now. This takes a few seconds.
      </CardContent>
    </Card>
  );
}

function SetupNeededCard({
  plan,
  onRetry,
}: {
  plan: AdvisorEmptyPlan;
  onRetry: () => void;
}) {
  return (
    <Card data-testid="today-setup-needed">
      <CardHeader>
        <CardTitle className="text-base">{plan.headline}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">{plan.message}</p>
        {plan.suggested_setup_steps.length > 0 && (
          <ul className="list-inside list-disc space-y-1 text-muted-foreground">
            {plan.suggested_setup_steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <Button asChild>
            <Link href={"/settings/integrations" as never}>Connect platforms</Link>
          </Button>
          <Button variant="outline" onClick={onRetry}>
            Check again
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function NoProfileCard() {
  return (
    <Card data-testid="today-no-profile">
      <CardHeader>
        <CardTitle className="text-base">
          Finish business onboarding first
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Today&apos;s view is tailored to your industry, audience, and
          goals. We can&apos;t pick what to do today without your profile.
        </p>
        <Button asChild>
          <Link href={"/onboarding/profile" as never}>Open onboarding</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function ErrorCard({
  message,
  retrying,
  onRetry,
}: {
  message: string;
  retrying: boolean;
  onRetry: () => void;
}) {
  return (
    <Card data-testid="today-error">
      <CardHeader>
        <CardTitle className="text-base">
          Couldn&apos;t build today&apos;s view
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">{message}</p>
        <Button onClick={onRetry} disabled={retrying}>
          {retrying ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Try again
        </Button>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------
//  Hero selection — deterministic policy
// ---------------------------------------------------------------------

type HeroSource = "leads" | "opportunities" | "trend";

export interface HeroPick {
  source: HeroSource;
  what: string;
  action: string;
  expected: string;
  confidence: number;
  reason: string;
  impact: "revenue" | "lead" | "customer" | "time" | "cost";
}

/**
 * Pick the single advisory to surface in the hero slot.
 *
 * Policy (in priority order):
 *
 * 1. **Hot inbox first.** If `counts.hot_count >= 1`, the lead hero
 *    always wins — replying to a hot lead is the highest-leverage
 *    thing a founder can do today, more than any post or ad.
 * 2. **Highest-confidence advisor otherwise.** Tie-break across
 *    leads / opportunities / trend (only when the trend has the
 *    Constitution advisory contract) by raw confidence score.
 * 3. **Leads break confidence ties.** Equal scores → leads, because
 *    inbox action is the most time-sensitive.
 *
 * Exported so tests can lock the policy in.
 */
export function pickHero(report: CombinedReport): HeroPick {
  const leadHero: HeroPick = {
    source: "leads",
    what: report.leads.hero_recommendation.what_is_happening,
    action: report.leads.hero_recommendation.recommendation,
    expected: report.leads.hero_recommendation.expected_result,
    confidence: report.leads.hero_recommendation.confidence,
    reason: report.leads.hero_recommendation.reason,
    impact: report.leads.hero_recommendation.impact_category,
  };

  if (report.leads.counts.hot_count >= 1) {
    return leadHero;
  }

  const oppHero: HeroPick = {
    source: "opportunities",
    what: report.opportunities.hero_recommendation.what_is_happening,
    action: report.opportunities.hero_recommendation.recommendation,
    expected: report.opportunities.hero_recommendation.expected_result,
    confidence: report.opportunities.hero_recommendation.confidence,
    reason: report.opportunities.hero_recommendation.reason,
    impact: report.opportunities.hero_recommendation.impact_category,
  };

  const candidates: HeroPick[] = [leadHero, oppHero];

  const advisoryTrend =
    report.intelligenceTrend ?? pickAdvisoryTrend(report.trend);
  if (advisoryTrend) {
    candidates.push({
      source: "trend",
      what: advisoryTrend.what_is_happening,
      action: advisoryTrend.recommended_action,
      expected: advisoryTrend.expected_result,
      confidence: advisoryTrend.confidence,
      reason: advisoryTrend.reason,
      // Trends don't carry an impact_category. Most trend-led actions
      // surface as visibility / leads, so we attribute them to leads.
      impact: "lead",
    });
  }

  // Stable sort: leads come first on ties (declared order matters).
  candidates.sort((a, b) => b.confidence - a.confidence);
  return candidates[0];
}

// ---------------------------------------------------------------------
//  Trend adapter — only return topics that satisfy the contract
// ---------------------------------------------------------------------

export interface AdvisoryTrend {
  topic: string;
  what_is_happening: string;
  recommended_action: string;
  expected_result: string;
  confidence: number;
  reason: string;
}

/**
 * Pick the single trend topic worth promoting to /today.
 *
 * Filters out legacy topics that lack the Constitution advisory
 * fields (no `recommended_action`, no `confidence`, etc.) — surfacing
 * them in /today would force the page to violate the four-question
 * contract. When every topic is legacy we return null and the trend
 * section degrades to a "Generate trends" empty state.
 */
export function pickAdvisoryTrend(
  report: TrendReport | null,
): AdvisoryTrend | null {
  if (!report || report.status !== "completed" || !report.analysis) return null;
  const candidates: AdvisoryTrend[] = [];
  for (const t of report.analysis.trending_topics) {
    if (!isAdvisoryTopic(t)) continue;
    candidates.push({
      topic: t.topic,
      what_is_happening: t.why_it_matters,
      recommended_action: t.recommended_action!,
      expected_result: t.expected_result!,
      confidence: t.confidence!,
      reason: t.reason!,
    });
  }
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.confidence - a.confidence);
  return candidates[0];
}

function isAdvisoryTopic(t: TrendingTopic): boolean {
  return Boolean(
    t.recommended_action &&
      t.expected_result &&
      t.reason &&
      typeof t.confidence === "number",
  );
}

function firstWithAdvisory(opps: Opportunity[]): Opportunity | null {
  // Opportunities already enforce the Constitution contract at the
  // schema layer, so the first item is always safe. Stays as a helper
  // for symmetry with `pickAdvisoryTrend` + future filtering.
  return opps.length > 0 ? opps[0] : null;
}

/**
 * Build the QuickGenerate context for the /today hero slot.
 *
 * The hero is a synthesized cross-source advisory — it's not tied to
 * one opportunity or trend. To honour Phase 8 ("Today → Generate →
 * Result") without inventing a new generation backend, we proxy
 * through the strongest underlying signal:
 *
 *   - leads hero          → no Generate (reply, don't post)
 *   - opportunities hero  → top content opportunity (if any qualifies)
 *   - trend hero          → the top advisory trend
 *
 * The request payload comes from the underlying signal; the founder-
 * facing wording (headline, expected result, reason, confidence) is
 * overridden to the hero itself so the modal reads as a literal
 * follow-through of the button the founder just clicked.
 *
 * Exported for tests.
 */
export function deriveHeroQuickGenerate({
  hero,
  topContentOpp,
  topTrend,
}: {
  hero: HeroPick;
  topContentOpp: Opportunity | null;
  topTrend: AdvisoryTrend | null;
}): QuickGenerateContext | null {
  if (hero.source === "leads") return null;

  let underlying: QuickGenerateContext | null = null;
  if (hero.source === "opportunities" && topContentOpp) {
    underlying = quickGenerateFromOpportunity(topContentOpp);
  } else if (hero.source === "trend" && topTrend) {
    underlying = quickGenerateFromTrend({
      topic: topTrend.topic,
      why_it_matters: topTrend.what_is_happening,
      suggested_angles: [],
      relevance_score: null,
      recommended_action: topTrend.recommended_action,
      expected_result: topTrend.expected_result,
      confidence: topTrend.confidence,
      reason: topTrend.reason,
    });
  }
  if (!underlying) return null;

  return {
    request: underlying.request,
    source: {
      label:
        hero.source === "opportunities"
          ? "Hero · From your top opportunity"
          : "Hero · From your top trend",
      headline: hero.action,
      reason: hero.reason,
      expectedResult: hero.expected,
      confidence: hero.confidence,
    },
  };
}

// ---------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------

function isNoProfileError(
  result: PromiseSettledResult<unknown>,
): boolean {
  return (
    result.status === "rejected" &&
    result.reason instanceof ApiError &&
    result.reason.status === 409
  );
}

function friendlyError(raw: string): string {
  const lowered = raw.toLowerCase();
  if (lowered.includes("503") || lowered.includes("unavailable")) {
    return "The AI provider was under heavy load. Wait a moment and try again.";
  }
  if (lowered.includes("429") || lowered.includes("rate")) {
    return "We hit the AI provider's rate limit. Wait 30 seconds and try again.";
  }
  if (lowered.includes("network")) {
    return "Couldn't reach the AI service. Check your connection and retry.";
  }
  return "Most errors here are temporary — try again in a moment.";
}

function confidenceBand(confidence: number): { label: string; cls: string } {
  if (confidence >= 80)
    return {
      label: "High",
      cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
    };
  if (confidence >= 60)
    return {
      label: "Medium",
      cls: "bg-sky-500/10 text-sky-600 border-sky-500/30",
    };
  if (confidence >= 40)
    return {
      label: "Low",
      cls: "bg-amber-500/10 text-amber-600 border-amber-500/30",
    };
  return {
    label: "Speculative",
    cls: "bg-muted text-muted-foreground border-border",
  };
}

function formatRelative(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(ts).toLocaleString();
}

// ---------------------------------------------------------------------
//  Cache (mirrors LeadIntelligenceCard / OpportunityCenter)
// ---------------------------------------------------------------------

interface CacheEntry {
  ts: number;
  data: CombinedReport;
}

function readCache(): CacheEntry | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEntry;
    if (!parsed || typeof parsed.ts !== "number" || !parsed.data) return null;
    if (Date.now() - parsed.ts > CACHE_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(entry: CacheEntry): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(entry));
  } catch {
    /* best-effort */
  }
}
