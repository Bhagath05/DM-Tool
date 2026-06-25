/**
 * Translate raw analytics KPIs → BusinessMetric props.
 *
 * Pure functions. No fetching. Tested in isolation.
 *
 * Each translator answers:
 *   - What does this number MEAN for the business? (plainLanguage)
 *   - Is it good/bad? (status — banded against industry rules of thumb)
 *   - What should the user do? (recommendation)
 *   - What will happen if they do it? (expectedResult)
 *   - How sure are we? (confidence — calibrated by sample size)
 *   - What data did this come from? (reason)
 *   - What are the raw numbers if a marketer wants them? (technicalDetails)
 *
 * If a translator can't produce a useful card (e.g. zero sample, no data),
 * it returns `null`. The dashboard renders a Coming Soon card in that
 * slot instead — keeps the Constitution's "ship questions, not numbers"
 * rule honest.
 */

import type {
  BusinessMetricProps,
  ImpactCategory,
} from "@/components/ui/business-metric";
import type { OverviewKpis, SourceRow } from "@/lib/api";

// ---------------------------------------------------------------------
//  Confidence calibration helpers
// ---------------------------------------------------------------------

/**
 * Scale confidence with sample size. Factual counts are 90+ (we
 * literally counted the rows). Rates / ratios need more data to trust.
 *
 * Bands match the Constitution: 80-100 High, 60-79 Medium, 40-59 Low,
 * <40 Speculative.
 */
function confidenceFromSample(sample: number): number {
  if (sample <= 0) return 0;
  if (sample >= 200) return 90;
  if (sample >= 50) return 80;
  if (sample >= 20) return 65;
  if (sample >= 5) return 50;
  return 35; // <5 = speculative, won't ship as CTA
}

// ---------------------------------------------------------------------
//  Lead Generation — total leads (last 30 days)
// ---------------------------------------------------------------------

/**
 * "Total leads this month" tile. Always renders (count is factual even
 * when zero), but the recommendation changes drastically by band.
 */
export function translateTotalLeads(
  kpis: OverviewKpis,
): BusinessMetricProps {
  const n = kpis.leads_30d;
  const total = kpis.total_leads;
  const hot = kpis.hot_leads;

  let plainLanguage: string;
  let status: BusinessMetricProps["status"];
  let businessImpact: string;
  let recommendation: string;
  let expectedResult: string;

  if (n === 0) {
    plainLanguage =
      "Nobody has filled out one of your lead pages in the last 30 days.";
    status = "bad";
    businessImpact =
      "No leads means no potential customers in the pipeline this month.";
    recommendation =
      "Publish a lead page if you haven't, then share it everywhere your audience hangs out.";
    expectedResult =
      "Even small traffic (50-100 visits) typically produces your first 1-3 leads.";
  } else if (n < 10) {
    plainLanguage = `${n} ${n === 1 ? "person has" : "people have"} shown interest in your business this month.`;
    status = "neutral";
    businessImpact =
      "You're past zero — now the goal is to make the trickle a steady flow.";
    recommendation =
      "Publish 2-3 more pieces of content this week, each linking back to your lead page.";
    expectedResult = `Expect 2-5x more leads next month if you keep posting consistently.`;
  } else if (n < 50) {
    plainLanguage = `${n} people showed interest in your business this month — steady flow.`;
    status = "good";
    businessImpact = "Healthy lead volume for an early-stage business.";
    recommendation =
      "Look at which channel sent the most leads and double down on it.";
    expectedResult =
      "Doubling down on one channel typically lifts leads 30-50% next period.";
  } else {
    plainLanguage = `Strong month — ${n} new leads.`;
    status = "good";
    businessImpact =
      "You have enough volume to start segmenting and converting at scale.";
    recommendation =
      "Focus on lead quality next: tag hot vs. cold and reach out to the hot ones first.";
    expectedResult =
      "Following up with hot leads within 24h typically converts 2-3x better than waiting.";
  }

  return {
    value: String(n),
    plainLanguage,
    status,
    impactCategory: "lead",
    businessImpact,
    recommendation,
    expectedResult,
    confidence: 90, // count is factual
    reason: `Counted from your leads table over the last 30 days.`,
    technicalDetails: {
      "Leads (30 days)": n,
      "Leads (7 days)": kpis.leads_7d,
      "Total leads (all time)": total,
      "Hot leads": hot,
    },
  };
}

// ---------------------------------------------------------------------
//  Lead Generation — visitor → lead conversion rate
// ---------------------------------------------------------------------

/**
 * "Visitor → lead conversion" tile. Only returns a metric if the
 * sample is large enough to trust the rate (small-sample discipline
 * from the Constitution). Otherwise returns null and the dashboard
 * surfaces a Coming Soon card.
 */
export function translateConversionRate(
  kpis: OverviewKpis,
): BusinessMetricProps | null {
  const views = kpis.total_views;
  const subs = kpis.total_submissions;
  if (views < 20) {
    // Small-sample discipline. Don't ship a rate computed from <20
    // visits — it's noise. Render a Coming Soon card instead.
    return null;
  }

  const ratePct = (kpis.conversion_rate || 0) * 100;
  const rounded = Math.round(ratePct * 10) / 10;
  const perHundred = Math.round(ratePct);

  let status: BusinessMetricProps["status"];
  let businessImpact: string;
  let recommendation: string;
  let expectedResult: string;

  // Industry rules of thumb: 2-5% is healthy for paid traffic; 1-2% is
  // typical for cold organic; <1% suggests page-hook problem.
  if (ratePct < 1) {
    status = "bad";
    businessImpact =
      "Most visitors leave without becoming a lead — your page may need a stronger hook.";
    recommendation =
      "Rewrite your landing page headline + above-the-fold promise to be more specific.";
    expectedResult =
      "A stronger headline alone usually doubles conversion in 1-2 weeks.";
  } else if (ratePct < 2) {
    status = "warning";
    businessImpact =
      "Conversion is a bit below the healthy range — small fixes can move the needle.";
    recommendation =
      "Try one of: clearer offer, single CTA above the fold, social proof testimonial.";
    expectedResult = "Modest tweaks typically lift conversion 30-60%.";
  } else if (ratePct < 5) {
    status = "good";
    businessImpact = "Healthy conversion — your page is doing its job.";
    recommendation =
      "Now drive more traffic to it — every additional visitor turns into a measurable lead.";
    expectedResult = `At this rate, every 100 extra visitors should produce ~${perHundred} extra leads.`;
  } else {
    status = "good";
    businessImpact =
      "Exceptional conversion — your offer-to-audience fit is strong.";
    recommendation =
      "Increase traffic aggressively (paid + organic) — conversion this high is rare.";
    expectedResult = `Every 100 extra visitors should produce ~${perHundred} extra leads.`;
  }

  return {
    value: `${rounded}%`,
    plainLanguage: `About ${perHundred} of every 100 visitors became leads.`,
    status,
    impactCategory: "lead",
    businessImpact,
    recommendation,
    expectedResult,
    confidence: confidenceFromSample(views),
    reason: `Calculated from ${views.toLocaleString()} page views and ${subs.toLocaleString()} lead submissions.`,
    technicalDetails: {
      "Conversion rate": `${rounded}%`,
      "Total views": views,
      "Total submissions": subs,
      "Pages published": kpis.landing_pages_published,
    },
  };
}

// ---------------------------------------------------------------------
//  Lead Generation — best-performing channel (AiRecommendation shape)
// ---------------------------------------------------------------------

export interface ChannelRecommendation {
  whatIsHappening: string;
  impactCategory: ImpactCategory;
  recommendation: string;
  expectedResult: string;
  confidence: number;
  reason: string;
  technicalDetails: Record<string, string | number>;
}

/**
 * Pick the source row that drove the most leads and frame it as
 * "double down on this channel". Returns null if no source has driven
 * any leads.
 */
export function translateTopChannel(
  sources: SourceRow[],
): ChannelRecommendation | null {
  if (!sources.length) return null;
  const ranked = [...sources]
    .filter((s) => s.leads > 0)
    .sort((a, b) => b.leads - a.leads);
  if (!ranked.length) return null;

  const top = ranked[0];
  const label = humanChannelLabel(top);
  const totalLeads = ranked.reduce((s, r) => s + r.leads, 0);
  const share = totalLeads > 0 ? top.leads / totalLeads : 0;
  const sharePct = Math.round(share * 100);

  let whatIsHappening: string;
  let recommendation: string;
  let expectedResult: string;

  if (sharePct >= 50) {
    whatIsHappening = `${label} is your #1 source — driving about ${sharePct}% of your leads (${top.leads} out of ${totalLeads}).`;
    recommendation = `Put extra time into ${label} this week — it's already proven to work for you.`;
    expectedResult = `Increasing ${label} activity by 50% could lift total leads by roughly ${Math.round(share * 50)}%.`;
  } else {
    whatIsHappening = `${label} is your top channel right now (${top.leads} leads), but the mix is balanced — no single channel dominates.`;
    recommendation = `Run an experiment: double posting on ${label} for the next 2 weeks and measure the lift.`;
    expectedResult = `If ${label} responds, expect 20-40% more total leads.`;
  }

  return {
    whatIsHappening,
    impactCategory: "lead",
    recommendation,
    expectedResult,
    confidence: confidenceFromSample(totalLeads),
    reason: `Based on ${totalLeads} leads across ${ranked.length} ${ranked.length === 1 ? "source" : "sources"} in your data.`,
    technicalDetails: {
      "Top channel": label,
      "Top channel leads": top.leads,
      "Top channel share": `${sharePct}%`,
      "Total leads (sourced)": totalLeads,
      "Sources counted": ranked.length,
    },
  };
}

function humanChannelLabel(row: SourceRow): string {
  // Prefer human-friendly source name. Fall back through UTM fields.
  if (row.utm_source) {
    const s = row.utm_source.toLowerCase();
    const map: Record<string, string> = {
      instagram: "Instagram",
      facebook: "Facebook",
      linkedin: "LinkedIn",
      google: "Google",
      youtube: "YouTube",
      tiktok: "TikTok",
      direct: "Direct visits",
      email: "Email",
    };
    return map[s] ?? row.utm_source;
  }
  if (row.source_asset_type) return capitalise(row.source_asset_type);
  return "Direct";
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
