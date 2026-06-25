/**
 * Map Intelligence Engine payloads → existing UI contracts.
 * No layout changes — only field adaptation.
 */

import type {
  ImpactCategory,
  AiRecommendationProps,
} from "@/components/ui/business-metric";
import type {
  Opportunity,
  OpportunityCenterReport,
  OpportunityGeneratorHint,
  OpportunityHeroRecommendation,
  OpportunityImpactCategory,
  RecommendationStatus,
} from "@/lib/api";

export interface DataSourceRef {
  key: string;
  label: string;
  value: string;
}

export interface IntelligenceRecommendation {
  id?: string | null;
  observation: string;
  root_cause: string;
  recommended_action: string;
  expected_impact: string;
  confidence: number;
  data_sources_used: DataSourceRef[];
  impact_category?: OpportunityImpactCategory;
  generator_hint?: OpportunityGeneratorHint | Record<string, unknown> | null;
  task_status?: RecommendationStatus | null;
  recommendation_id?: string | null;
}

export interface IntelligenceOpportunity extends IntelligenceRecommendation {
  kind: "content" | "ad";
  headline: string;
}

export interface DailyBrief {
  what_happened: string;
  why_it_happened: string;
  confidence: number;
  data_sources_used: DataSourceRef[];
}

export interface AdvisorEmptyPlan {
  ready: boolean;
  headline: string;
  message: string;
  suggested_setup_steps: string[];
  signals_used: string[];
  generated_at: string;
}

export interface IntelligenceReport {
  ready: boolean;
  empty?: AdvisorEmptyPlan | null;
  hero?: IntelligenceRecommendation | null;
  content_opportunities: IntelligenceOpportunity[];
  ad_opportunities: IntelligenceOpportunity[];
  trend?: IntelligenceRecommendation | null;
  daily_brief?: DailyBrief | null;
  signals_used: string[];
  confidence_cap: number;
  generated_at: string;
}

export interface AdvisoryTrend {
  topic: string;
  what_is_happening: string;
  recommended_action: string;
  expected_result: string;
  confidence: number;
  reason: string;
}

function dataSourcesToTechnicalDetails(
  sources: DataSourceRef[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of sources) {
    out[s.label] = s.value;
  }
  return out;
}

export function translateIntelligenceRec(
  rec: IntelligenceRecommendation,
): AiRecommendationProps {
  return {
    whatIsHappening: rec.observation,
    impactCategory: (rec.impact_category ?? "lead") as ImpactCategory,
    recommendation: rec.recommended_action,
    expectedResult: rec.expected_impact,
    confidence: rec.confidence,
    reason: rec.root_cause,
    technicalDetails: dataSourcesToTechnicalDetails(rec.data_sources_used),
  };
}

export function intelligenceToHero(
  rec: IntelligenceRecommendation,
): OpportunityHeroRecommendation {
  return {
    what_is_happening: rec.observation,
    impact_category: rec.impact_category ?? "lead",
    recommendation: rec.recommended_action,
    expected_result: rec.expected_impact,
    confidence: rec.confidence,
    reason: rec.root_cause,
    task_status: rec.task_status ?? null,
  };
}

function hintFromRaw(
  raw: IntelligenceOpportunity["generator_hint"],
  kind: "content" | "ad",
): OpportunityGeneratorHint {
  if (raw && typeof raw === "object" && "target" in raw) {
    return raw as OpportunityGeneratorHint;
  }
  return {
    target: kind === "ad" ? "ad" : "content",
    format: kind === "ad" ? "meta" : "social_post",
    platform: "Instagram",
    goal: "Drive engagement",
    objective: kind === "ad" ? "leads" : null,
  };
}

export function intelligenceToOpportunity(
  opp: IntelligenceOpportunity,
  index: number,
): Opportunity {
  return {
    id: opp.recommendation_id ?? opp.id ?? `intel-${opp.kind}-${index}`,
    kind: opp.kind,
    headline: opp.headline,
    what_is_happening: opp.observation,
    why_it_matters: opp.root_cause,
    recommended_action: opp.recommended_action,
    expected_result: opp.expected_impact,
    confidence: opp.confidence,
    reason: opp.root_cause,
    impact_category: opp.impact_category ?? "lead",
    evidence: opp.data_sources_used.map((d) => `${d.label}: ${d.value}`),
    generator: hintFromRaw(opp.generator_hint, opp.kind),
    task_status: opp.task_status ?? null,
  };
}

export function intelligenceToOpportunityReport(
  report: IntelligenceReport,
): OpportunityCenterReport {
  if (!report.ready || !report.hero) {
    return {
      headline: report.empty?.headline ?? "Setup needed",
      hero_recommendation: {
        what_is_happening: report.empty?.message ?? "Complete setup to continue.",
        impact_category: "lead",
        recommendation: report.empty?.suggested_setup_steps[0] ?? "Complete onboarding",
        expected_result: "Unlock evidence-backed recommendations.",
        confidence: 0,
        reason: report.empty?.message ?? "",
      },
      content_opportunities: [],
      ad_opportunities: [],
      skip_for_now: [],
      signals_used: report.signals_used,
      generated_at: report.generated_at,
      advisor_ready: false,
      advisor_setup_steps: report.empty?.suggested_setup_steps ?? [],
    };
  }

  return {
    headline: "Today's intelligence",
    hero_recommendation: intelligenceToHero(report.hero),
    content_opportunities: report.content_opportunities.map(intelligenceToOpportunity),
    ad_opportunities: report.ad_opportunities.map(intelligenceToOpportunity),
    skip_for_now: [],
    signals_used: report.signals_used,
    generated_at: report.generated_at,
    advisor_ready: true,
    advisor_setup_steps: [],
  };
}

export function intelligenceToAdvisoryTrend(
  rec: IntelligenceRecommendation | null | undefined,
): AdvisoryTrend | null {
  if (!rec) return null;
  return {
    topic: rec.recommended_action.slice(0, 80),
    what_is_happening: rec.observation,
    recommended_action: rec.recommended_action,
    expected_result: rec.expected_impact,
    confidence: rec.confidence,
    reason: rec.root_cause,
  };
}
