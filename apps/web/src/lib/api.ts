/**
 * Typed fetch client for the DM Tool FastAPI backend.
 *
 * This is a thin hand-written wrapper today. Once we wire OpenAPI codegen
 * (openapi-typescript), the response types here become generated rather
 * than hand-written.
 *
 * Tenant headers:
 * - `X-Organization-Id` and `X-Brand-Id` are pulled from the module-level
 *   cache in `lib/tenant.ts` (populated by `TenantProvider`).
 * - Callers can override per-request via `init.organizationId` / `init.brandId`.
 *   This is used by `TenantProvider`'s initial `/me` boot call where the
 *   cache hasn't been seeded yet.
 */

import { getAuthToken } from "./auth-token";
import { dedupeRequest } from "./request-dedupe";
import type {
  BrandAsset,
  CampaignBuildResponse,
  CreativeBrief,
  DesignResponse,
  DesignSummary,
  GenerateBriefPayload,
  GrowthObjective,
  NlEditResponse,
  ObjectiveKind,
  RevisionSummary,
  StockResult,
  VideoExport,
  VideoRenderResponse,
  VideoStatus,
} from "./studio-types";
import {
  clearPersistedSelection,
  getActiveTenantHeaders,
  setActiveTenantHeaders,
  type MeResponse,
} from "./tenant";

// Self-heal guard for a stale tenant selection. If a brand-scoped request
// 403s with "not a member of this organization" because the cached org id is
// no longer valid (e.g. a long-lived tab whose persisted selection points at
// an org from a previous session), we drop the stale selection and reload so
// TenantProvider re-resolves from /me. Capped to avoid any reload loop.
const TENANT_RECOVER_KEY = "aicmo.tenant.autorecover.v1";
const TENANT_RECOVER_MAX = 2;

function maybeRecoverFromStaleTenant(
  status: number,
  message: string,
  sentCachedOrg: string | null,
  usedOverride: boolean,
): void {
  if (typeof window === "undefined") return;
  // Only when WE attached a cached org header (not a deliberate per-call
  // override like onboarding) and the backend rejected membership.
  if (
    status !== 403 ||
    usedOverride ||
    !sentCachedOrg ||
    !/not a member of this organization/i.test(message)
  ) {
    return;
  }
  let count = 0;
  try {
    count = Number(window.sessionStorage.getItem(TENANT_RECOVER_KEY) || 0);
  } catch {
    /* sessionStorage unavailable — skip self-heal */
    return;
  }
  if (count >= TENANT_RECOVER_MAX) return; // give up rather than loop
  try {
    window.sessionStorage.setItem(TENANT_RECOVER_KEY, String(count + 1));
  } catch {
    return;
  }
  clearPersistedSelection();
  setActiveTenantHeaders({ organization_id: null, brand_id: null });
  window.location.reload();
}

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL?.trim() || "http://localhost:8000"
).replace(/\/$/, "");

export interface HealthResponse {
  status: string;
  env: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI returns validation errors as `detail: [{loc, msg, type}, ...]`.
 *  Plain `String()` on that gives "[object Object]" — flatten it properly. */
function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object" && "msg" in d) {
          const loc =
            "loc" in d && Array.isArray((d as { loc: unknown[] }).loc)
              ? (d as { loc: unknown[] }).loc.slice(1).join(".")
              : "";
          const msg = String((d as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return JSON.stringify(d);
      })
      .join(" · ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return String(detail ?? "Request failed");
}

async function request<T>(
  path: string,
  init?: RequestInit & {
    token?: string;
    /** Override the cached active org for this one call. */
    organizationId?: string | null;
    /** Override the cached active brand for this one call. */
    brandId?: string | null;
  },
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");

  // Authorization header — per-call `token` override wins, else pull
  // from the auth-token cache (populated by ClerkTokenBridge in prod;
  // null in dev when Clerk isn't configured, which lets the backend's
  // dev-user bypass take over). Token-getter handles refresh per call.
  const explicitToken = init?.token;
  const token = explicitToken ?? (await getAuthToken());
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // Tenant headers — explicit per-call override wins over the module-level
  // cache. Skip setting either header if the value is null/undefined so we
  // don't smuggle empty strings to the backend.
  const cached = getActiveTenantHeaders();
  const orgId =
    init?.organizationId !== undefined
      ? init.organizationId
      : cached.organization_id;
  const brandId =
    init?.brandId !== undefined ? init.brandId : cached.brand_id;
  if (orgId) headers.set("X-Organization-Id", orgId);
  if (brandId) headers.set("X-Brand-Id", brandId);

  const method = (init?.method ?? "GET").toUpperCase();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch (networkErr) {
    // Network-level failure (DNS, refused, offline). Surface to Sentry
    // because the user sees a spinner-forever, not a structured error.
    const { captureApiError } = await import("./sentry-tenant");
    captureApiError(networkErr, { method, path });
    throw networkErr;
  }
  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const err = new ApiError(
      typeof body === "object" && body && "detail" in body
        ? formatDetail((body as { detail: unknown }).detail)
        : res.statusText,
      res.status,
      body,
    );
    // Only 5xx auto-reports to Sentry. 4xx is usually user/input error
    // and would just create noise. Callers can manually capture if a
    // specific 4xx is unexpected for them.
    if (res.status >= 500) {
      const { captureApiError } = await import("./sentry-tenant");
      captureApiError(err, { method, path, status: res.status });
    }
    // Self-heal a stale tenant selection: if the cached org id we attached is
    // one this user no longer belongs to, drop it and reload once so the
    // provider re-resolves. No-op for deliberate per-call org overrides.
    maybeRecoverFromStaleTenant(
      res.status,
      err.message,
      orgId ?? null,
      init?.organizationId !== undefined,
    );
    throw err;
  }

  return body as T;
}

export interface GrowthMilestone {
  phase: string;
  goal: string;
  actions: string[];
  success_metric: string;
}

export interface ChannelRecommendation {
  channel: string;
  why_now: string;
  expected_outcome: string;
}

export interface BusinessAnalysis {
  // v1 fields — always present
  business_summary: string;
  audience_insights: string[];
  marketing_opportunities: string[];
  content_directions: string[];
  strategy_recommendation: string;
  // Phase 2.1 — Intelligence Engine v2 fields. Optional so legacy
  // analyses (persisted before v2) still validate when read.
  current_state?: string | null;
  desired_future_state?: string | null;
  gap_analysis?: string | null;
  growth_bottlenecks?: string[] | null;
  competitor_signals?: string[] | null;
  realistic_growth_path?: GrowthMilestone[] | null;
  recommended_acquisition_channels?: ChannelRecommendation[] | null;
}

export interface BusinessProfile {
  id: string;
  user_id: string;
  business_name: string;
  website: string | null;
  industry: string;
  target_audience: string;
  brand_tone: string;
  competitors: string[];
  goals: string[];
  preferred_platforms: string[];
  /** Phase 2.0 — conversational onboarding fields. Null for rows
   *  created by the legacy wizard. */
  business_location: string | null;
  current_monthly_leads_band: string | null;
  monthly_budget_band: string | null;
  primary_goal_text: string | null;
  // Phase 3.1 business understanding.
  products: string[];
  services: string[];
  unique_selling_points: string[];
  pricing: string | null;
  growth_stage: string | null;
  // Phase 8 Brand Brain — brand identity.
  brand_colors: string[];
  fonts: string[];
  keywords: string[];
  brand_rules: string[];
  writing_style: string | null;
  analysis_status: "pending" | "completed" | "failed";
  analysis: BusinessAnalysis | null;
  analysis_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface BusinessProfileSubmitPayload {
  business_name: string;
  website?: string;
  industry: string;
  target_audience: string;
  competitors: string[];
  goals: string[];
  brand_tone: string;
  preferred_platforms: string[];
  // Phase 2.0 — all optional, backend tolerates absence.
  business_location?: string;
  current_monthly_leads_band?: string;
  monthly_budget_band?: string;
  primary_goal_text?: string;
  // Phase 3.1 + Phase 8 Brand Brain — optional, backend defaults to empty.
  products?: string[];
  services?: string[];
  unique_selling_points?: string[];
  pricing?: string;
  brand_colors?: string[];
  fonts?: string[];
  keywords?: string[];
  brand_rules?: string[];
  writing_style?: string;
}

// ---------- AI Marketing Health ----------

/** One plain-language health score. Carries the full constitution contract:
 *  what it means, why it matters, and what to do next. */
export interface HealthScore {
  key: string;
  label: string;
  score: number;
  status: "good" | "watch" | "bad";
  explanation: string;
  why: string;
  recommendation: string;
}

export interface MarketingHealth {
  overall: number;
  overall_status: "good" | "watch" | "bad";
  headline: string;
  /** Key of the weakest score — what to fix first. */
  focus_key: string;
  scores: HealthScore[];
}

// ---------- Intelligent Onboarding — AI discovery ----------

/** The AI's proposed Brand Brain, shown for review + editing before it's applied. */
export interface DiscoveryDraft {
  business_description: string;
  products: string[];
  services: string[];
  target_audience: string;
  unique_selling_points: string[];
  competitors: string[];
  brand_tone: string;
  writing_style: string;
  keywords: string[];
  brand_colors: string[];
  fonts: string[];
  brand_rules: string[];
  goals: string[];
  summary: string;
  content_opportunities: string[];
  marketing_opportunities: string[];
  seo_opportunities: string[];
  brand_completeness_score: number;
  content_readiness_score: number;
  advertising_readiness_score: number;
  seo_readiness_score: number;
}

/** Real progress marker advanced by the backend runner (never a fake timer). */
export type DiscoveryStage =
  | "queued"
  | "reading"
  | "understanding"
  | "building"
  | "done";

export interface DiscoveryRun {
  id: string;
  source: "website" | "scratch";
  url: string | null;
  business_name: string;
  industry: string | null;
  status: "pending" | "running" | "completed" | "failed";
  stage: DiscoveryStage;
  draft: DiscoveryDraft | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartWebsiteDiscoveryPayload {
  business_name: string;
  website_url: string;
  industry: string;
}

export interface StartScratchDiscoveryPayload {
  business_name: string;
  what_you_sell: string;
  who_to_reach: string;
  what_makes_different?: string;
  style: string;
  main_goal: string;
  industry?: string;
}

// ---------- Trends ----------

/**
 * One trending topic mapped onto the Constitution's 4-question advisor
 * contract. The advisory fields (`recommended_action`, `expected_result`,
 * `confidence`, `reason`) are nullable purely so legacy reports already
 * stored in Postgres still hydrate — new reports always populate them.
 *
 * The frontend renders the founder advisory card (action + expected
 * result + confidence tier + reason) whenever the four fields are
 * present, and falls back to the legacy summary view otherwise.
 */
export interface TrendingTopic {
  topic: string;
  why_it_matters: string;
  suggested_angles: string[];
  /** Legacy 1-100 score. UI no longer renders this directly. */
  relevance_score: number | null;
  recommended_action: string | null;
  expected_result: string | null;
  confidence: number | null;
  reason: string | null;
}

export interface ContentIdea {
  platform: string;
  format: string;
  hook: string;
  description: string;
}

export interface HashtagCluster {
  theme: string;
  hashtags: string[];
}

export interface TrendAnalysis {
  summary: string;
  trending_topics: TrendingTopic[];
  content_ideas: ContentIdea[];
  hashtag_clusters: HashtagCluster[];
  marketing_angles: string[];
}

export interface RawTrendsSummary {
  google_trends: unknown[];
  reddit_posts: unknown[];
  sources_attempted: string[];
  sources_failed: string[];
}

export interface TrendReport {
  id: string;
  user_id: string;
  status: "pending" | "completed" | "failed";
  raw_trends: RawTrendsSummary | null;
  analysis: TrendAnalysis | null;
  analysis_error: string | null;
  created_at: string;
  updated_at: string;
}

// ---------- Content ----------

export type ContentType =
  | "social_post"
  | "reel"
  | "carousel"
  | "ad_copy"
  | "landing_page_copy"
  | "blog_article"
  | "email"
  | "product_description"
  | "press_release"
  | "case_study"
  | "customer_story"
  | "testimonial"
  | "product_comparison"
  | "faq"
  | "website_copy"
  | "homepage_copy"
  | "about_us"
  | "service_page"
  | "sales_page"
  | "email_newsletter"
  | "cold_email"
  | "followup_email"
  | "promo_email"
  | "youtube_title"
  | "youtube_description"
  | "video_script"
  | "shorts_script"
  | "tiktok_script"
  | "pinterest_description"
  | "x_thread"
  | "cta_variations"
  | "headlines"
  | "taglines"
  | "hooks"
  | "meta_description"
  | "seo_title"
  | "keyword_ideas";

// All content types, for filter dropdowns (kept in sync with the backend enum).
export const CONTENT_TYPES: ContentType[] = [
  "social_post", "reel", "carousel", "ad_copy", "landing_page_copy",
  "blog_article", "email", "product_description", "press_release",
  "case_study", "customer_story", "testimonial", "product_comparison", "faq",
  "website_copy", "homepage_copy", "about_us", "service_page", "sales_page",
  "email_newsletter", "cold_email", "followup_email", "promo_email",
  "youtube_title", "youtube_description", "video_script", "shorts_script",
  "tiktok_script", "pinterest_description", "x_thread", "cta_variations",
  "headlines", "taglines", "hooks", "meta_description", "seo_title", "keyword_ideas",
];

export interface ContentStrategy {
  trend_influence: string;
  audience_angle: string;
  strategy_note: string;
}

export interface GeneratedContent {
  id: string;
  user_id: string;
  business_profile_id: string;
  trend_report_id: string | null;
  landing_page_id: string | null;
  campaign_id: string | null;
  bundle_id: string | null;
  strategy_id: string | null;
  recommendation_id: string | null;
  content_type: ContentType;
  platform: string;
  goal: string;
  tone: string;
  strategy: ContentStrategy;
  output: Record<string, unknown>;
  share_url: string | null;
  is_saved: boolean;
  review_status: ReviewStatus;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface GenerateContentPayload {
  content_type: ContentType;
  platform: string;
  goal: string;
  tone?: string;
  landing_page_id?: string;
}

// ---------- Content ops (Phase 6.2B) ----------

export type ReviewStatus =
  | "draft"
  | "in_review"
  | "changes_requested"
  | "approved"
  | "rejected"
  | "published"
  | "archived";

export const REVIEW_STATUSES: ReviewStatus[] = [
  "draft", "in_review", "changes_requested", "approved",
  "rejected", "published", "archived",
];

// Legal next-states per status — mirrors the backend `_ALLOWED` transition
// table so the UI only offers moves the API will accept.
export const REVIEW_TRANSITIONS: Record<ReviewStatus, ReviewStatus[]> = {
  draft: ["in_review", "archived"],
  in_review: ["changes_requested", "approved", "rejected"],
  changes_requested: ["in_review", "draft"],
  approved: ["published", "changes_requested", "archived"],
  rejected: ["draft", "archived"],
  published: ["archived"],
  archived: ["draft"],
};

export interface ContentVersion {
  id: string;
  version_no: number;
  edit_source: string; // "ai" | "manual" | "restore"
  change_summary: string | null;
  author_user_id: string;
  created_at: string;
}

export interface VersionOutput {
  version_no: number;
  edit_source: string;
  output: Record<string, unknown>;
}

export interface VersionCompare {
  a: VersionOutput;
  b: VersionOutput;
}

export interface ReviewEvent {
  id: string;
  from_status: string;
  to_status: string;
  reason: string | null;
  reviewer_user_id: string;
  created_at: string;
}

export interface ContentFolder {
  id: string;
  name: string;
  kind: string; // "folder" | "collection"
  parent_id: string | null;
  pinned: boolean;
  created_at: string;
}

export interface ContentComment {
  id: string;
  content_id: string;
  parent_id: string | null;
  author_user_id: string;
  body: string;
  mentions: string[];
  resolved: boolean;
  resolved_by_user_id: string | null;
  created_at: string;
}

export interface ContentSearchResult {
  items: GeneratedContent[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContentSearchParams {
  q?: string;
  content_type?: ContentType;
  review_status?: ReviewStatus;
  folder_id?: string;
  campaign_id?: string;
  strategy_id?: string;
  saved_only?: boolean;
  limit?: number;
  offset?: number;
}

// ---------- Ads ----------

export type AdType =
  | "meta"
  | "google_search"
  | "instagram_promo"
  | "linkedin"
  | "youtube";

export type AdObjective =
  | "awareness"
  | "traffic"
  | "engagement"
  | "leads"
  | "app_installs"
  | "conversions"
  | "sales";

export interface AdStrategy {
  trend_influence: string;
  audience_angle: string;
  emotional_trigger: string;
  conversion_strategy: string;
}

export interface AdTargeting {
  audience_description: string;
  interests: string[];
  demographics: string[];
  behaviors: string[];
}

export interface GeneratedAd {
  id: string;
  user_id: string;
  business_profile_id: string;
  trend_report_id: string | null;
  landing_page_id: string | null;
  ad_type: AdType;
  platform: string;
  objective: AdObjective;
  goal: string;
  tone: string;
  strategy: AdStrategy;
  targeting: AdTargeting;
  output: Record<string, unknown>;
  share_url: string | null;
  is_saved: boolean;
  created_at: string;
  updated_at: string;
  rendered_visual_id?: string | null;
  primary_image_url?: string | null;
}

export interface GenerateAdPayload {
  ad_type: AdType;
  objective: AdObjective;
  goal: string;
  tone?: string;
  audience_override?: string;
  landing_page_id?: string;
}

// ---------- Visuals ----------

export type VisualType = "ad_creative" | "carousel" | "reel" | "thumbnail";

export interface ColorSwatch {
  name: string;
  hex: string;
  role: string;
}

export interface TypographyHint {
  style: string;
  headline_treatment: string;
  body_treatment: string;
  suggested_fonts: string[];
}

export interface VisualStrategy {
  visual_concept: string;
  emotional_trigger: string;
  audience_angle: string;
  trend_influence: string;
  composition_principle: string;
  conversion_rationale: string;
}

export interface GeneratedVisual {
  id: string;
  user_id: string;
  business_profile_id: string;
  trend_report_id: string | null;
  landing_page_id: string | null;
  visual_type: VisualType;
  platform: string;
  goal: string;
  tone: string;
  strategy: VisualStrategy;
  output: Record<string, unknown>;
  share_url: string | null;
  is_saved: boolean;
  created_at: string;
  updated_at: string;
  renders?: RenderedVisual[];
  primary_signed_url?: string | null;
  thumbnail_url?: string | null;
}

export interface GenerateVisualPayload {
  visual_type: VisualType;
  platform: string;
  goal: string;
  tone?: string;
  landing_page_id?: string;
}

// ---------- Campaigns ----------

export type CampaignType =
  | "product_launch"
  | "brand_awareness"
  | "lead_generation"
  | "seasonal"
  | "engagement_growth"
  | "retargeting";

export type CampaignDuration = 7 | 14 | 30;

export interface CampaignStrategyMeta {
  campaign_theme: string;
  audience_focus: string;
  funnel_strategy: string;
  posting_cadence: string;
  cta_progression: string;
  success_signals: string[];
}

export interface PlatformRecommendation {
  platform: string;
  role: "primary" | "secondary" | "amplifier";
  rationale: string;
}

export interface VisualDirectionHint {
  aesthetic: string;
  palette_direction: string;
  typography_direction: string;
}

export interface CampaignSequencePhase {
  phase_name: string;
  day_range: string;
  objective: string;
  primary_metric: string;
}

export interface CampaignStrategyEnvelope {
  strategy: CampaignStrategyMeta;
  platforms: PlatformRecommendation[];
  visual_direction: VisualDirectionHint;
  sequence: CampaignSequencePhase[];
}

export interface CalendarDay {
  day: number;
  platform: string;
  content_type: string;
  objective: string;
  hook: string;
  cta: string;
  visual_direction_summary: string;
  recommended_ad_support: string;
  rationale: string;
}

export interface CampaignPlan {
  id: string;
  user_id: string;
  business_profile_id: string;
  trend_report_id: string | null;
  landing_page_id: string | null;
  campaign_type: CampaignType;
  duration_days: number;
  goal: string;
  tone: string;
  strategy: CampaignStrategyEnvelope;
  calendar: CalendarDay[];
  /** Per-day attributed share URLs, keyed by day number ("1", "2", ...).
   *  Empty object when no landing page is attached. */
  share_urls: Record<string, string>;
  is_saved: boolean;
  created_at: string;
  updated_at: string;
}

export interface GenerateCampaignPayload {
  campaign_type: CampaignType;
  duration_days: CampaignDuration;
  platforms: string[];
  goal: string;
  tone?: string;
  audience_override?: string;
  landing_page_id?: string;
}

// ---------- Landing pages + Leads ----------

export interface LandingPageBenefit {
  title: string;
  body: string;
  icon?: string | null;
}

export interface LandingPageSocialProof {
  quote: string;
  author: string;
  role?: string | null;
}

export interface LandingPageFAQ {
  q: string;
  a: string;
}

export type FormFieldType = "text" | "email" | "tel" | "textarea";

export interface LandingPageFormField {
  name: string;
  label: string;
  type: FormFieldType;
  required: boolean;
  placeholder?: string | null;
}

export interface LandingPageContent {
  headline: string;
  subheadline?: string | null;
  benefits: LandingPageBenefit[];
  cta_text: string;
  form_fields: LandingPageFormField[];
  social_proof: LandingPageSocialProof[];
  faq: LandingPageFAQ[];
  footer_text?: string | null;
  privacy_blurb?: string | null;
}

export type LandingPageStatus = "draft" | "published";

export interface LandingPage {
  id: string;
  user_id: string;
  business_profile_id: string;
  slug: string;
  title: string;
  status: LandingPageStatus;
  preview_token: string;
  content: LandingPageContent;
  redirect_url: string | null;
  view_count: number;
  submission_count: number;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateLandingPagePayload {
  title: string;
  slug?: string;
  content: LandingPageContent;
  redirect_url?: string;
}

export interface UpdateLandingPagePayload {
  title?: string;
  slug?: string;
  content?: LandingPageContent;
  redirect_url?: string | null;
  status?: LandingPageStatus;
  is_archived?: boolean;
}

export interface PublicLandingPage {
  slug: string;
  title: string;
  content: LandingPageContent;
  redirect_url: string | null;
  turnstile_site_key: string | null;
}

export type LeadStatus = "new" | "hot" | "warm" | "cold" | "archived";

export interface Lead {
  id: string;
  user_id: string;
  business_profile_id: string;
  email: string;
  name: string | null;
  phone: string | null;
  company: string | null;
  message: string | null;
  extra_data: Record<string, unknown>;
  landing_page_id: string | null;
  source_asset_type: string | null;
  source_asset_id: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  utm_term: string | null;
  utm_content: string | null;
  status: LeadStatus;
  tags: string[];
  notes: string | null;
  referrer: string | null;
  created_at: string;
  updated_at: string;
}

export interface UpdateLeadPayload {
  status?: LeadStatus;
  tags?: string[];
  notes?: string;
}

export interface CreateLeadPayload {
  email: string;
  name?: string | null;
  phone?: string | null;
  company?: string | null;
  message?: string | null;
  status?: LeadStatus;
  tags?: string[];
  notes?: string | null;
}

export interface LeadImportResult {
  inserted: number;
  skipped: number;
  errors: string[];
}

// ---------- Lead Intelligence (Phase 5) ----------
//
// Mirrors apps/api/aicmo/modules/leads/schemas.py. Keep field names and
// literal types in sync. Backend refuses to ship a recommendation
// missing any contract field; the frontend `<AiRecommendation>` does
// the same. These types let TypeScript catch a drift between the two.

export type LeadImpactCategory =
  | "revenue"
  | "lead"
  | "customer"
  | "time"
  | "cost";

export type LeadPriorityBucket = "focus" | "hot" | "warm" | "cold";

export type EstimatedValueBand = "high" | "medium" | "low" | "unknown";

export interface LeadHeroRecommendation {
  what_is_happening: string;
  impact_category: LeadImpactCategory;
  recommendation: string;
  expected_result: string;
  confidence: number;
  reason: string;
}

export interface LeadPriorityItem {
  lead_id: string;
  email: string;
  name: string | null;
  company: string | null;
  rank: number;
  priority: LeadPriorityBucket;
  why_now: string;
  recommended_action: string;
  expected_result: string;
  confidence: number;
  reason: string;
  impact_category: LeadImpactCategory;
  estimated_value_band: EstimatedValueBand;
  cta_label: string;
}

export interface LeadCountsSnapshot {
  total: number;
  new_count: number;
  hot_count: number;
  last_7d: number;
  last_24h: number;
}

export interface LeadIntelligenceReport {
  headline: string;
  hero_recommendation: LeadHeroRecommendation;
  priorities: LeadPriorityItem[];
  skip_for_now: string[];
  counts: LeadCountsSnapshot;
  signals_used: string[];
  generated_at: string;
}

// ---------- Opportunity Center (Phase 6) ----------
//
// Mirrors apps/api/aicmo/modules/opportunities/schemas.py. Same
// Constitution contract enforcement on both sides — backend Pydantic
// refuses to ship, frontend `<AiRecommendation>` refuses to render.

export type OpportunityKind = "content" | "ad";

export type OpportunityImpactCategory =
  | "revenue"
  | "lead"
  | "customer"
  | "time"
  | "cost";

export type OpportunityContentFormat =
  | "social_post"
  | "reel"
  | "carousel"
  | "ad_copy"
  | "blog_outline"
  | "short_video_script";

export type OpportunityAdFormat =
  | "meta"
  | "google_search"
  | "instagram_promo"
  | "linkedin";

export type OpportunityAdObjective =
  | "awareness"
  | "traffic"
  | "engagement"
  | "leads"
  | "app_installs"
  | "conversions"
  | "sales";

export interface OpportunityGeneratorHint {
  target: "content" | "ad";
  /** ContentFormat when target='content', AdFormat when target='ad'. */
  format: string;
  platform: string | null;
  goal: string;
  /** Ad-only. Always null for content opportunities. */
  objective: OpportunityAdObjective | null;
}

export type RecommendationStatus =
  | "not_started"
  | "in_progress"
  | "completed"
  | "skipped";

export interface OpportunityHeroRecommendation {
  what_is_happening: string;
  impact_category: OpportunityImpactCategory;
  recommendation: string;
  expected_result: string;
  confidence: number;
  reason: string;
  task_status?: RecommendationStatus | null;
}

export interface Opportunity {
  id: string;
  kind: OpportunityKind;
  headline: string;
  what_is_happening: string;
  why_it_matters: string;
  recommended_action: string;
  expected_result: string;
  confidence: number;
  reason: string;
  impact_category: OpportunityImpactCategory;
  /** Supporting signals — Simple Mode HIDES, Professional Mode SHOWS. */
  evidence: string[];
  generator: OpportunityGeneratorHint;
  task_status?: RecommendationStatus | null;
}

export interface OpportunityCenterReport {
  headline: string;
  hero_recommendation: OpportunityHeroRecommendation;
  content_opportunities: Opportunity[];
  ad_opportunities: Opportunity[];
  skip_for_now: string[];
  signals_used: string[];
  generated_at: string;
  advisor_ready?: boolean;
  advisor_setup_steps?: string[];
}

export interface AdvisorHistoryItem {
  id: string;
  date: string;
  title: string;
  description: string;
  status: RecommendationStatus;
  observation?: string | null;
  root_cause?: string | null;
  recommended_action?: string | null;
  expected_impact?: string | null;
  result_summary: string | null;
  outcome_status?: string | null;
  effectiveness_score?: number | null;
  learning?: string | null;
  impact_score: number;
  impact_label: "High" | "Medium" | "Low";
  confidence: number;
  why: string | null;
  data_used?: Array<{ key: string; label: string; value: string }>;
  expected_result: string | null;
}

export interface AgentReportRecommendation {
  observation: string;
  root_cause: string;
  recommended_action: string;
  expected_impact: string;
  confidence: number;
  data_sources_used: Array<{ key: string; label: string; value: string }>;
}

export interface AgentReport {
  report_type: string;
  ready: boolean;
  summary: string;
  sections: Array<{ title: string; body: string; confidence: number }>;
  recommendations: AgentReportRecommendation[];
  setup_steps: string[];
  confidence: number;
  data_sources_used: Array<{ key: string; label: string; value: string }>;
  period_start: string;
  period_end: string;
  generated_at: string;
}

// ---------- Analytics ----------

export interface OverviewKpis {
  total_leads: number;
  leads_7d: number;
  leads_30d: number;
  hot_leads: number;
  landing_pages_published: number;
  total_views: number;
  total_submissions: number;
  conversion_rate: number;
  top_landing_page_title: string | null;
  top_landing_page_slug: string | null;
  top_landing_page_submissions: number;
}

export interface TimelinePoint {
  day: string; // ISO date
  leads: number;
}

export interface TimelineResponse {
  days: TimelinePoint[];
  total: number;
  window_days: number;
}

export interface SourceRow {
  source_asset_type: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  leads: number;
  hot_leads: number;
}

export interface LandingPagePerformanceRow {
  id: string;
  slug: string;
  title: string;
  status: string;
  view_count: number;
  submission_count: number;
  conversion_rate: number;
  hot_leads: number;
}

export interface StatusDistribution {
  new: number;
  hot: number;
  warm: number;
  cold: number;
  archived: number;
}

// ---------- Coach (Reality Engine) ----------

export type FeasibilityLabel =
  | "Highly achievable"
  | "Achievable with strong execution"
  | "Aggressive but possible"
  | "High-risk target"
  | "Unrealistic under current constraints";

export type RiskKind =
  | "timeline"
  | "budget"
  | "saturation"
  | "execution"
  | "acquisition"
  | "stage"
  | "channel";

export type RiskSeverity = "info" | "watch" | "blocker";

export interface RealityMilestone {
  timeframe: string;
  target: string;
  why_realistic: string;
}

export interface PhasedStep {
  phase: string;
  focus: string;
  rationale: string;
}

export interface RiskFlag {
  kind: RiskKind;
  note: string;
  severity: RiskSeverity;
}

export interface RealityCheck {
  feasibility_score: number; // 0-100
  feasibility_label: FeasibilityLabel;
  headline: string;
  realistic_milestones: RealityMilestone[];
  phased_growth_path: PhasedStep[];
  risk_flags: RiskFlag[];
  strategic_notes: string[];
  score_signals: string[];
}

export interface RealityCheckPayload {
  goal_text: string;
  timeline_hint?: string;
}

// ---------- Coach (Weekly Action Rollup, Phase 2.4) ----------

export type ActionTarget =
  | "content"
  | "ads"
  | "visuals"
  | "campaigns"
  | "lead_pages"
  | "trends"
  | "analytics"
  | "profile";

export type ActionPriority = "focus" | "important" | "stretch";

export type ImpactCategory =
  | "revenue"
  | "lead"
  | "customer"
  | "time"
  | "cost";

export interface WeeklyAction {
  /** Named action_title (not title) to avoid Gemini's JSON-Schema reserved-word collision. */
  action_title: string;
  why: string;
  business_impact: string;
  impact_category: ImpactCategory;
  expected_result: string;
  confidence: number; // 0-100
  reason: string;
  cta_label: string;
  cta_target: ActionTarget;
  priority: ActionPriority;
  estimated_time: string;
}

export interface WeeklyPlan {
  headline: string;
  week_focus: string;
  actions: WeeklyAction[];
  skip_this_week: string[];
  signals_used: string[];
  /** ISO timestamp; used for the 12h client-side cache decision. */
  generated_at: string;
}

// ---------- Rendered visuals (Phase 4-A) ----------

export interface RenderedVisual {
  id: string;
  visual_id: string;
  provider: string;
  width: number;
  height: number;
  mime_type: string;
  cost_cents: number;
  latency_ms: number;
  created_at: string;
  /** Relative path like `/api/v1/media/<uuid>?exp=...&sig=...`.
   *  The frontend prepends NEXT_PUBLIC_API_URL when embedding in <img>. */
  signed_url: string;
  slide_index?: number | null;
}

export interface RenderQuotaStatus {
  used_today: number;
  daily_cap: number;
  remaining: number;
}

export interface RenderRequestPayload {
  quality?: "standard" | "hd";
}

// ---------- Bundles (Phase 3.1) ----------

export type BundlePieceKind = "campaign" | "content" | "ad" | "visual";

export interface BundlePiece {
  kind: BundlePieceKind;
  id: string | null;
  label: string;
  platform: string | null;
  subtype: string | null;
  is_error: boolean;
  error_message: string | null;
}

export interface CampaignBundle {
  id: string;
  user_id: string;
  business_profile_id: string;
  theme: string;
  objective: string;
  duration_days: number;
  landing_page_id: string | null;
  pieces: BundlePiece[];
  created_at: string;
}

export interface GenerateBundlePayload {
  theme: string;
  objective: AdObjective;
  duration_days?: 7 | 14 | 30;
  landing_page_id?: string;
}

// ---------- Social Intelligence Layer (Phase 1) ----------

export type SocialPlatform =
  | "instagram"
  | "facebook"
  | "linkedin"
  | "youtube"
  | "tiktok";

export interface SocialAvailability {
  platform: SocialPlatform;
  available: boolean;
  reason: string | null;
}

export interface SocialConnection {
  id: string;
  user_id: string;
  platform: SocialPlatform;
  source: "oauth" | "manual_import";
  metadata_json: Record<string, unknown>;
  last_synced_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export type IntegrationConnectionState =
  | "DISCONNECTED"
  | "PENDING_AUTH"
  | "ACTIVE"
  | "EXPIRED"
  | "ERROR"
  | "SUSPENDED";

export interface IntegrationProviderInfo {
  slug: string;
  display_name: string;
  category: string;
  icon_id: string;
  description: string;
  scopes: string[];
  available: boolean;
}

export interface IntegrationConnection {
  id: string;
  organization_id: string;
  brand_id: string | null;
  provider_slug: string;
  state: IntegrationConnectionState;
  external_account_id: string | null;
  external_account_name: string | null;
  scopes_granted: string[];
  error_message: string | null;
  connected_at: string | null;
  last_sync_at: string | null;
  last_error_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntegrationCatalogEntry {
  provider: IntegrationProviderInfo;
  connection: IntegrationConnection | null;
}

export interface IntegrationSyncResult {
  connection_id: string;
  state: IntegrationConnectionState;
  started_at: string;
  finished_at: string;
  rows_pulled: number;
  error_message: string | null;
}

// Phase 6.1 — integration activity log + analytics.
export interface IntegrationEvent {
  id: string;
  connection_id: string | null;
  provider_slug: string;
  event_type: string;
  status: "success" | "failure" | "info";
  message: string | null;
  detail: Record<string, unknown>;
  duration_ms: number | null;
  occurred_at: string;
}

export interface IntegrationAnalytics {
  window_days: number;
  connections_total: number;
  connections_by_state: Record<string, number>;
  syncs_total: number;
  syncs_succeeded: number;
  syncs_failed: number;
  sync_success_rate: number | null;
  errors_total: number;
  events_total: number;
  events_by_provider: Record<string, number>;
}

export interface IntegrationEventQuery {
  connection_id?: string;
  provider?: string;
  event_type?: string;
  status?: string;
  limit?: number;
}

export type PublishPlatform =
  | "instagram"
  | "facebook"
  | "linkedin"
  | "youtube"
  | "pinterest"
  | "google_business_profile";
export type PublishStatus =
  | "draft"
  | "scheduled"
  | "publishing"
  | "published"
  | "failed"
  | "cancelled"
  | "paused";

export type ApprovalStatus =
  | "not_required"
  | "pending"
  | "approved"
  | "rejected"
  | "changes_requested";

export interface ScheduledPost {
  id: string;
  content_asset_id: string;
  recommendation_id: string | null;
  platform: PublishPlatform;
  scheduled_at: string;
  publish_status: PublishStatus;
  platform_post_id: string | null;
  published_at: string | null;
  error_message: string | null;
  attempt_count: number;
  next_attempt_at: string | null;
  approval_status: ApprovalStatus;
  approval_required: boolean;
  reviewed_by_user_id: string | null;
  approval_reason: string | null;
  schedule_timezone: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformHealth {
  platform: string;
  published: number;
  failed: number;
  scheduled: number;
  success_rate: number;
}

export interface QueueAnalytics {
  published: number;
  scheduled: number;
  publishing: number;
  failed: number;
  cancelled: number;
  paused: number;
  approval_pending: number;
  draft: number;
  queue_length: number;
  total_retries: number;
  success_rate: number;
  avg_publish_seconds: number | null;
  platform_health: PlatformHealth[];
}

// ---------- CRM (Phase 6.5) ----------

export type CrmPipelineKind = "marketing" | "sales" | "enterprise" | "agency" | "custom";
export type CrmDealStatus = "open" | "won" | "lost";
export type CrmPriority = "low" | "medium" | "high";

export interface CrmStage {
  id: string;
  name: string;
  position: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface CrmPipeline {
  id: string;
  name: string;
  kind: string;
  is_default: boolean;
  archived: boolean;
  created_at: string;
  stages: CrmStage[];
}

export interface CrmDealNextAction {
  recommendation: string;
  reason: string;
  confidence: number;
  expected_result: string;
  risk_score: number;
  opportunity_score: number;
}

export interface CrmDeal {
  id: string;
  pipeline_id: string;
  stage_id: string | null;
  lead_id: string | null;
  title: string;
  company: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  value: number;
  currency: string;
  probability: number | null;
  status: CrmDealStatus;
  priority: CrmPriority;
  expected_close_date: string | null;
  owner_user_id: string | null;
  source: string | null;
  tags: string[];
  products: unknown[];
  competitors: string[];
  lost_reason: string | null;
  won_at: string | null;
  lost_at: string | null;
  ai_next_action: CrmDealNextAction | null;
  ai_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmDealCreate {
  pipeline_id: string;
  stage_id?: string | null;
  lead_id?: string | null;
  title: string;
  company?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  value?: number;
  currency?: string;
  priority?: CrmPriority;
  expected_close_date?: string | null;
  source?: string | null;
  tags?: string[];
}

export interface CrmStageBreakdown {
  stage_id: string | null;
  stage_name: string;
  count: number;
  value: number;
}

export interface CrmAnalytics {
  pipeline_id: string | null;
  open_deals: number;
  won_deals: number;
  lost_deals: number;
  pipeline_value: number;
  weighted_forecast: number;
  won_value: number;
  win_rate: number;
  avg_deal_size: number;
  conversion_rate: number;
  by_stage: CrmStageBreakdown[];
}

// ---- CRM Slice 2: companies, contacts, activities ----

export interface CrmEntitySummary {
  summary: string;
  confidence: number;
  reason: string;
  talking_points?: string[];
  opportunities?: string[];
  risks?: string[];
}

export interface CrmCompany {
  id: string;
  name: string;
  domain: string | null;
  website: string | null;
  industry: string | null;
  annual_revenue: number | null;
  employees: number | null;
  tech_stack: string[];
  social_links: Record<string, string>;
  address: string | null;
  timezone: string | null;
  owner_user_id: string | null;
  tags: string[];
  custom_fields: Record<string, unknown>;
  ai_summary: CrmEntitySummary | null;
  ai_generated_at: string | null;
  health_score: number | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CrmCompanyCreate {
  name: string;
  website?: string | null;
  industry?: string | null;
  annual_revenue?: number | null;
  employees?: number | null;
  tags?: string[];
}

export interface CrmContact {
  id: string;
  company_id: string | null;
  lead_id: string | null;
  name: string;
  title: string | null;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  owner_user_id: string | null;
  tags: string[];
  custom_fields: Record<string, unknown>;
  notes: string | null;
  ai_summary: CrmEntitySummary | null;
  ai_generated_at: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CrmContactCreate {
  name: string;
  company_id?: string | null;
  title?: string | null;
  email?: string | null;
  phone?: string | null;
  linkedin?: string | null;
  tags?: string[];
  notes?: string | null;
}

export interface CrmActivity {
  id: string;
  kind: "note" | "email" | "call" | "meeting" | "file" | "linkedin";
  subject: string | null;
  body: string | null;
  contact_id: string | null;
  company_id: string | null;
  deal_id: string | null;
  occurred_at: string;
  actor_user_id: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface CrmActivityCreate {
  kind: CrmActivity["kind"];
  subject?: string | null;
  body?: string | null;
  contact_id?: string | null;
  company_id?: string | null;
  deal_id?: string | null;
}

export interface CrmDuplicate {
  id: string;
  name: string;
  reason: string;
}

export interface CrmCompanyDetail {
  company: CrmCompany;
  contacts: CrmContact[];
  deals: CrmDeal[];
  health_score: number | null;
}

export interface CrmContactDetail {
  contact: CrmContact;
  company: CrmCompany | null;
  deals: CrmDeal[];
}

// ---- CRM Slice 3: tasks & calendar ----

export type CrmTaskStatus = "open" | "in_progress" | "completed" | "cancelled";
export type CrmTaskPriority = "low" | "medium" | "high" | "urgent";
export type CrmActivityType =
  | "call" | "meeting" | "demo" | "follow_up"
  | "email_reminder" | "internal" | "approval" | "custom";

export interface CrmTaskSuggestion {
  recommended_priority: CrmTaskPriority;
  recommended_due_in_days: number;
  follow_up: string;
  risk_alert: string;
  confidence: number;
  reason: string;
}

export interface CrmTask {
  id: string;
  title: string;
  description: string | null;
  activity_type: CrmActivityType;
  status: CrmTaskStatus;
  priority: CrmTaskPriority;
  owner_user_id: string | null;
  assignee_user_id: string | null;
  due_at: string | null;
  reminder_at: string | null;
  is_recurring: boolean;
  recurrence: Record<string, unknown> | null;
  recurrence_parent_id: string | null;
  calendar_event: boolean;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  completed_at: string | null;
  notes: string | null;
  attachments: unknown[];
  tags: string[];
  lead_id: string | null;
  contact_id: string | null;
  company_id: string | null;
  deal_id: string | null;
  campaign_id: string | null;
  source: string | null;
  ai_suggestion: CrmTaskSuggestion | null;
  ai_generated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrmTaskCreate {
  title: string;
  description?: string | null;
  activity_type?: CrmActivityType;
  priority?: CrmTaskPriority;
  assignee_user_id?: string | null;
  due_at?: string | null;
  recurrence?: { freq: "daily" | "weekly" | "monthly"; interval?: number } | null;
  deal_id?: string | null;
  contact_id?: string | null;
  company_id?: string | null;
  lead_id?: string | null;
  tags?: string[];
}

// ---- CRM Slice 4: email platform ----

export type CrmEmailCategory =
  | "welcome" | "follow_up" | "proposal" | "reminder"
  | "thank_you" | "meeting" | "renewal" | "custom";

export interface CrmEmailTemplate {
  id: string;
  name: string;
  category: CrmEmailCategory;
  subject: string;
  body: string;
  variables: string[];
  folder_id: string | null;
  is_active: boolean;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface CrmEmailTemplateCreate {
  name: string;
  category?: CrmEmailCategory;
  subject: string;
  body: string;
  variables?: string[];
}

export interface CrmEmailTemplateVersion {
  id: string;
  version_no: number;
  subject: string;
  body: string;
  edit_summary: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface CrmEmailSequenceStep {
  id: string;
  position: number;
  template_id: string | null;
  delay_hours: number;
  wait_for_open: boolean;
  stop_on_reply: boolean;
}

export interface CrmEmailSequence {
  id: string;
  name: string;
  description: string | null;
  status: "draft" | "active" | "archived";
  created_at: string;
  steps: CrmEmailSequenceStep[];
}

export interface CrmEmail {
  id: string;
  to_email: string;
  subject: string;
  status: string;
  provider: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  opened_at: string | null;
  clicked_at: string | null;
  replied_at: string | null;
  bounced_at: string | null;
  unsubscribed_at: string | null;
  open_count: number;
  click_count: number;
  contact_id: string | null;
  deal_id: string | null;
  created_at: string;
}

export interface CrmEmailStats {
  sent: number;
  delivered: number;
  opened: number;
  clicked: number;
  replied: number;
  bounced: number;
  unsubscribed: number;
  open_rate: number;
  click_rate: number;
  reply_rate: number;
  bounce_rate: number;
}

// ---- CRM Slice 5: AI Sales Assistant ----

export type CrmInsightSubject = "lead" | "deal" | "contact" | "company" | "task" | "email";

export interface CrmInsightEvidence {
  source: string;
  detail: string;
}

export interface CrmInsight {
  id: string;
  subject_type: string;
  subject_id: string;
  kind: string;
  summary: string | null;
  recommendation: string | null;
  evidence: CrmInsightEvidence[];
  reasoning: string | null;
  confidence: number;
  affected_records: string[];
  expected_outcome: string | null;
  insufficient_evidence: boolean;
  model: string | null;
  generated_at: string;
  expires_at: string | null;
}

// ---- CRM Slice 6: executive dashboard ----

export interface CrmExecKPIs {
  total_leads: number;
  qualified_leads: number;
  active_opportunities: number;
  won_deals: number;
  lost_deals: number;
  revenue: number;
  pipeline_value: number;
  avg_deal_size: number;
  win_rate: number;
  conversion_rate: number;
  sales_velocity: number;
  avg_sales_cycle_days: number | null;
  lead_response_time_hours: number | null;
  email_open_rate: number;
  email_reply_rate: number;
  meetings_completed: number;
  tasks_completed: number;
  follow_up_compliance: number | null;
}

export interface CrmStageFunnel {
  stage_id: string | null;
  stage_name: string;
  count: number;
  value: number;
  avg_days_in_stage: number | null;
}

export interface CrmRepPerformance {
  owner_user_id: string;
  revenue: number;
  won_deals: number;
  open_deals: number;
  pipeline_value: number;
  win_rate: number;
  activities: number;
  meetings: number;
  calls: number;
  emails: number;
  tasks_completed: number;
}

export interface CrmForecastPeriod {
  period: string;
  won_revenue: number;
  deals: number;
}

export interface CrmExecutiveDashboard {
  kpis: CrmExecKPIs;
  pipeline: {
    analytics: CrmAnalytics;
    funnel: CrmStageFunnel[];
    lost_reasons: { reason: string; count: number }[];
    risk_distribution: { band: string; count: number; value: number }[];
    stalled_deals: { id: string; title: string; value: number; days_inactive: number; owner_user_id: string | null }[];
  };
  reps: CrmRepPerformance[];
  activity: {
    calls: number;
    meetings: number;
    emails: number;
    notes: number;
    tasks_open: number;
    tasks_completed: number;
    follow_ups_due: number;
  };
  forecast: {
    monthly: CrmForecastPeriod[];
    quarterly: CrmForecastPeriod[];
    pipeline_weighted_forecast: number;
    open_pipeline_value: number;
  };
  ai_insights: CrmInsight[];
  generated_at: string;
  filters: Record<string, unknown>;
}

/** One entry in a scheduled post's audit trail. */
export interface PublishEvent {
  id: string;
  event_type: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PerformanceSignal {
  impressions: number;
  reach: number;
  likes: number;
  comments_count: number;
  saves: number;
  shares: number;
  engagement_rate: number;
  views: number;
  watch_time_seconds: number;
  ctr: number;
  captured_at: string;
}

export interface SocialAsset {
  id: string;
  platform: SocialPlatform;
  platform_post_id: string;
  asset_type: string;
  caption: string | null;
  thumbnail_url: string | null;
  permalink: string | null;
  hashtags: string[];
  posted_at: string | null;
  latest_signal: PerformanceSignal | null;
}

export interface WinningPattern {
  id: string;
  platform: SocialPlatform | null;
  summary: string;
  hook_pattern: string | null;
  visual_pattern: string | null;
  caption_pattern: string | null;
  cta_pattern: string | null;
  format_pattern: string | null;
  posting_time_pattern: string | null;
  performance_score: number;
  source_asset_ids: string[];
  created_at: string;
}

export interface AudiencePattern {
  id: string;
  platform: SocialPlatform;
  pattern_type: string;
  description: string;
  confidence_score: number;
  created_at: string;
}

export interface ManualImportAssetPayload {
  platform_post_id: string;
  asset_type: string;
  caption?: string;
  thumbnail_url?: string;
  permalink?: string;
  hashtags?: string[];
  posted_at?: string;
  impressions?: number;
  reach?: number;
  likes?: number;
  comments_count?: number;
  saves?: number;
  shares?: number;
  views?: number;
  watch_time_seconds?: number;
  ctr?: number;
  raw_json?: Record<string, unknown>;
}

export interface ManualImportPayload {
  platform: SocialPlatform;
  handle?: string;
  assets: ManualImportAssetPayload[];
}

export interface ImportResult {
  connection_id: string;
  inserted_assets: number;
  updated_assets: number;
  inserted_signals: number;
}

export interface AnalyzeResult {
  patterns_created: number;
  audience_patterns_created: number;
  assets_considered: number;
}

// ---------- Campaign Learning Lab (Phase 1B) ----------

export type ExperimentAssetType =
  | "content"
  | "ad"
  | "visual"
  | "landing_page"
  | "bundle";

export type ExperimentStatus =
  | "pending"
  | "live"
  | "completed"
  | "archived";

export type LearningDirection = "positive" | "negative" | "neutral";

export type LearningEventStatus = "active" | "archived" | "superseded";

export type LearningEventSource = "auto" | "manual";

export interface CampaignExperiment {
  id: string;
  user_id: string;
  source_asset_type: ExperimentAssetType;
  source_asset_id: string;
  platform: string | null;
  goal: string | null;
  hypothesis: string | null;
  inherited_patterns: string[];
  variable_choices: Record<string, unknown>;
  context_snapshot: Record<string, unknown>;
  status: ExperimentStatus;
  sample_size: number;
  confidence_score: number;
  evidence: string[];
  created_at: string;
  updated_at: string;
}

export interface ExperimentResult {
  id: string;
  experiment_id: string;
  impressions: number;
  reach: number;
  likes: number;
  comments_count: number;
  saves: number;
  shares: number;
  engagement_rate: number;
  leads: number;
  ctr: number;
  views: number;
  watch_time_seconds: number;
  captured_at: string;
  sample_size: number;
  confidence_score: number;
  evidence: string[];
}

export interface LearningEvent {
  id: string;
  user_id: string;
  variable: string;
  finding: string;
  direction: LearningDirection;
  effect_size: number | null;
  experiment_ids: string[];
  evidence: string[];
  sample_size: number;
  confidence_score: number;
  source: LearningEventSource;
  status: LearningEventStatus;
  created_at: string;
  updated_at: string;
}

export interface ExperimentProvenance {
  experiment: CampaignExperiment;
  matched_events: LearningEvent[];
  latest_result: ExperimentResult | null;
}

export interface LearningRunResult {
  events_created: number;
  events_superseded: number;
  experiments_considered: number;
}

// ---------- Generation Context (Phase 3.0) ----------

export interface WinningAsset {
  source_asset_type: AssetType;
  source_asset_id: string;
  subtype: string;
  platform: string | null;
  goal: string;
  leads: number;
}

export interface WinningPage {
  id: string;
  title: string;
  slug: string;
  submission_count: number;
  conversion_rate: number;
}

export interface ContextPreferences {
  suggested_platform: string | null;
  suggested_tone: string | null;
  suggested_goal: string | null;
  suggested_landing_page_id: string | null;
}

export interface GenerationContext {
  user_id: string;
  business_name: string;
  industry: string;
  target_audience: string;
  brand_tone: string;
  preferred_platforms: string[];
  business_location: string | null;
  current_monthly_leads_band: string | null;
  monthly_budget_band: string | null;
  primary_goal_text: string | null;
  current_state: string | null;
  desired_future_state: string | null;
  growth_bottlenecks: string[];
  recommended_channels: string[];
  current_phase_summary: string | null;
  winning_assets: WinningAsset[];
  winning_page: WinningPage | null;
  social_winning_patterns: string[];
  social_audience_signals: string[];
  learning_findings: string[];
  preferences: ContextPreferences;
  signals_used: string[];
  generated_at: string;
}

// ---------- Coach (Analytics Summary, Phase 2.5) ----------

export interface AnalyticsSummary {
  headline: string;
  what_to_do_next: string;
  overview_blurb: string;
  timeline_blurb: string;
  sources_blurb: string;
  landing_pages_blurb: string;
  top_assets_blurb: string;
  signals_used: string[];
  generated_at: string;
}

// ---------- Analytics types ----------

export type AssetType = "content" | "ad" | "visual" | "campaign";

export interface TopAssetRow {
  source_asset_type: AssetType;
  source_asset_id: string;
  subtype: string; // content_type / ad_type / visual_type / campaign_type
  platform: string | null;
  goal: string;
  leads: number;
  hot_leads: number;
  created_at: string;
}

// ---- Team (Settings → Team) ----
// Mirrors apps/api/aicmo/modules/team/schemas.py. Dates arrive as ISO
// strings over JSON. Owner is never invitable; admin/analyst/viewer are.
export type InviteStatus = "pending" | "accepted" | "revoked" | "expired";
export type InvitableRole = "admin" | "analyst" | "viewer";
export type CanonicalRole = "owner" | "admin" | "analyst" | "viewer";

export interface RoleDescriptor {
  slug: CanonicalRole;
  display_name: string;
  description: string;
  capabilities: string[];
  can_be_invited_as: boolean;
  can_be_granted_by_admin: boolean;
  is_terminal_for_org: boolean;
}

export interface MemberSummary {
  member_id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  role_slugs: string[];
  is_owner: boolean;
  joined_at: string;
  last_active_at: string | null;
}

export interface InviteRead {
  id: string;
  organization_id: string;
  email: string;
  role_slug: InvitableRole;
  status: InviteStatus;
  invited_by_user_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  is_expired: boolean;
}

export interface InviteCreateResponse {
  invite: InviteRead;
  /** Full acceptance URL with the raw token — returned ONCE, never persisted. */
  accept_url: string;
}

export interface TeamOverview {
  members: MemberSummary[];
  pending_invites: InviteRead[];
  roles: RoleDescriptor[];
  member_count: number;
  pending_invite_count: number;
  can_invite: boolean;
  can_revoke_owner: boolean;
}

export interface InvitePreview {
  organization_name: string;
  organization_slug: string;
  role_slug: InvitableRole;
  role_display_name: string;
  invited_email: string;
  expires_at: string;
  is_expired: boolean;
}

export interface InviteAcceptResponse {
  organization_id: string;
  brand_id: string | null;
  role_slugs: string[];
  next_route: string;
}

// ---- System / storage capability ----
// Mirrors GET /api/v1/system/storage. Drives the admin-only object-storage
// notice + disabling of file-producing (image/export) controls.
export interface StorageStatus {
  media_backend: "local" | "s3" | "r2";
  environment: "development" | "staging" | "production";
  media_persistence_available: boolean;
  image_generation_enabled: boolean;
  asset_exports_enabled: boolean;
}

// ---- Competitor intelligence (Market Intelligence → Competitor Watch) ----
// Mirrors apps/api/aicmo/modules/competitors/schemas.py.
export interface CompetitorInsight {
  name: string;
  positioning: string;
  strengths: string[];
  gaps: string[];
  content_angles: string[];
  your_move: string;
  confidence: number;
}

export interface CompetitorAnalysisResponse {
  market_summary: string;
  competitors: CompetitorInsight[];
  recommendation: string;
  reason: string;
  confidence: number;
  expected_result: string;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  /**
   * Identity + tenant bootstrap. Designed never to 4xx for an authed user.
   * `organizationId`/`brandId` overrides are used by `TenantProvider` so
   * the first call after a switch carries the new headers BEFORE the
   * module-level cache is updated.
   */
  me: (opts?: {
    organizationId?: string | null;
    brandId?: string | null;
  }) =>
    // NOTE: users router mounts at /users; combined prefix is /api/v1/users/me.
    // Don't shorten to /api/v1/me — that's a 404.
    request<MeResponse>("/api/v1/users/me", {
      organizationId: opts?.organizationId,
      brandId: opts?.brandId,
    }),
  analytics: {
    overview: () => request<OverviewKpis>("/api/v1/analytics/overview"),
    timeline: (windowDays = 30) =>
      request<TimelineResponse>(
        `/api/v1/analytics/timeline?window_days=${windowDays}`,
      ),
    sources: (limit = 25) =>
      request<{ items: SourceRow[] }>(
        `/api/v1/analytics/sources?limit=${limit}`,
      ),
    landingPages: () =>
      request<{ items: LandingPagePerformanceRow[] }>(
        "/api/v1/analytics/landing-pages",
      ),
    statusDistribution: () =>
      request<StatusDistribution>("/api/v1/analytics/status-distribution"),
    topAssets: (limit = 10) =>
      request<{ items: TopAssetRow[] }>(
        `/api/v1/analytics/top-assets?limit=${limit}`,
      ),
  },
  landingPages: {
    list: async (params: { include_archived?: boolean } = {}): Promise<LandingPage[]> => {
      const qs = new URLSearchParams();
      if (params.include_archived) qs.set("include_archived", "true");
      const suffix = qs.toString() ? `?${qs}` : "";
      const res = await request<{ items: LandingPage[] }>(
        `/api/v1/landing-pages${suffix}`,
      );
      return res.items;
    },
    get: (id: string) =>
      request<LandingPage>(`/api/v1/landing-pages/${id}`),
    create: (payload: CreateLandingPagePayload) =>
      request<LandingPage>("/api/v1/landing-pages", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (id: string, payload: UpdateLandingPagePayload) =>
      request<LandingPage>(`/api/v1/landing-pages/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/landing-pages/${id}`, { method: "DELETE" }),
    /** Public — used by the /p/[slug] route */
    getPublic: (slug: string, preview?: string) =>
      request<PublicLandingPage>(
        `/api/v1/public/landing-pages/${slug}${preview ? `?preview=${preview}` : ""}`,
      ),
  },
  leads: {
    list: async (params: {
      search?: string;
      status?: LeadStatus;
      landing_page_id?: string;
      limit?: number;
      offset?: number;
    } = {}): Promise<{ items: Lead[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.search) qs.set("search", params.search);
      if (params.status) qs.set("status", params.status);
      if (params.landing_page_id)
        qs.set("landing_page_id", params.landing_page_id);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs}` : "";
      return await request<{ items: Lead[]; total: number }>(
        `/api/v1/leads${suffix}`,
      );
    },
    get: (id: string) => request<Lead>(`/api/v1/leads/${id}`),
    update: (id: string, payload: UpdateLeadPayload) =>
      request<Lead>(`/api/v1/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/leads/${id}`, { method: "DELETE" }),
    create: (payload: CreateLeadPayload) =>
      request<Lead>("/api/v1/leads", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    importCsv: (csv: string) =>
      request<LeadImportResult>("/api/v1/leads/import", {
        method: "POST",
        body: JSON.stringify({ csv }),
      }),
    /**
     * Phase 5 — Lead Intelligence.
     *
     * Returns the ranked "who to contact first" advisor card. One LLM
     * call per request server-side; the inbox UI caches via
     * localStorage (mirrors analytics-summary). Returns 409 when
     * business onboarding hasn't been completed.
     */
    intelligence: () =>
      request<LeadIntelligenceReport>("/api/v1/leads/intelligence"),
    /** Returns the absolute URL to the CSV download — the user clicks it. */
    exportUrl: (params: { status?: LeadStatus; landing_page_id?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.status) qs.set("status", params.status);
      if (params.landing_page_id)
        qs.set("landing_page_id", params.landing_page_id);
      const suffix = qs.toString() ? `?${qs}` : "";
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      return `${base}/api/v1/leads/export.csv${suffix}`;
    },
  },
  team: {
    /** GET /team — members + pending invites + role catalog + affordance flags. */
    overview: () => request<TeamOverview>("/api/v1/team"),
    /** POST /team/invites — returns the one-time accept URL. Requires `team.manage`. */
    createInvite: (payload: { email: string; role_slug: InvitableRole }) =>
      request<InviteCreateResponse>("/api/v1/team/invites", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    /** GET /team/invites — list invites; pass true to include terminal history. */
    listInvites: (includeTerminal = false) =>
      request<{ invites: InviteRead[] }>(
        `/api/v1/team/invites${includeTerminal ? "?include_terminal=true" : ""}`,
      ),
    /** POST /team/invites/{id}/revoke — cancel a pending invite. */
    revokeInvite: (inviteId: string) =>
      request<InviteRead>(`/api/v1/team/invites/${inviteId}/revoke`, {
        method: "POST",
      }),
    /** POST /team/invites/{id}/resend — new token + extended expiry. */
    resendInvite: (inviteId: string) =>
      request<InviteCreateResponse>(
        `/api/v1/team/invites/${inviteId}/resend`,
        { method: "POST" },
      ),
    /** GET /invites/{token} — public preview of an invite (acceptance page). */
    previewInvite: (token: string) =>
      request<InvitePreview>(`/api/v1/invites/${encodeURIComponent(token)}`),
    /** POST /invites/accept — consume an invite. Requires a signed-in user. */
    acceptInvite: (token: string) =>
      request<InviteAcceptResponse>("/api/v1/invites/accept", {
        method: "POST",
        body: JSON.stringify({ token }),
      }),
  },
  campaigns: {
    generate: (payload: GenerateCampaignPayload) =>
      request<CampaignPlan>("/api/v1/campaigns/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    list: async (params: {
      saved_only?: boolean;
      campaign_type?: CampaignType;
      limit?: number;
    } = {}): Promise<CampaignPlan[]> => {
      const qs = new URLSearchParams();
      if (params.saved_only) qs.set("saved_only", "true");
      if (params.campaign_type) qs.set("campaign_type", params.campaign_type);
      if (params.limit) qs.set("limit", String(params.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      const res = await request<{ items: CampaignPlan[] }>(
        `/api/v1/campaigns${suffix}`,
      );
      return res.items;
    },
    setSaved: (id: string, is_saved: boolean) =>
      request<CampaignPlan>(`/api/v1/campaigns/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_saved }),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/campaigns/${id}`, { method: "DELETE" }),
  },
  visuals: {
    generate: (payload: GenerateVisualPayload) =>
      request<GeneratedVisual>("/api/v1/visuals/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    list: async (params: {
      saved_only?: boolean;
      visual_type?: VisualType;
      limit?: number;
    } = {}): Promise<GeneratedVisual[]> => {
      const qs = new URLSearchParams();
      if (params.saved_only) qs.set("saved_only", "true");
      if (params.visual_type) qs.set("visual_type", params.visual_type);
      if (params.limit) qs.set("limit", String(params.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      const res = await request<{ items: GeneratedVisual[] }>(
        `/api/v1/visuals${suffix}`,
      );
      return res.items;
    },
    setSaved: (id: string, is_saved: boolean) =>
      request<GeneratedVisual>(`/api/v1/visuals/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_saved }),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/visuals/${id}`, { method: "DELETE" }),
    // Phase 4-A — real image rendering.
    render: (id: string, payload: RenderRequestPayload = {}) =>
      request<RenderedVisual>(`/api/v1/visuals/${id}/render`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    listRenders: async (id: string): Promise<RenderedVisual[]> => {
      const res = await request<{ items: RenderedVisual[] }>(
        `/api/v1/visuals/${id}/renders`,
      );
      return res.items;
    },
    renderQuota: () =>
      request<RenderQuotaStatus>("/api/v1/visuals/render-quota"),
  },
  ads: {
    generate: (payload: GenerateAdPayload) =>
      request<GeneratedAd>("/api/v1/ads/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    list: async (params: {
      saved_only?: boolean;
      ad_type?: AdType;
      objective?: AdObjective;
      limit?: number;
    } = {}): Promise<GeneratedAd[]> => {
      const qs = new URLSearchParams();
      if (params.saved_only) qs.set("saved_only", "true");
      if (params.ad_type) qs.set("ad_type", params.ad_type);
      if (params.objective) qs.set("objective", params.objective);
      if (params.limit) qs.set("limit", String(params.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      const res = await request<{ items: GeneratedAd[] }>(
        `/api/v1/ads${suffix}`,
      );
      return res.items;
    },
    setSaved: (id: string, is_saved: boolean) =>
      request<GeneratedAd>(`/api/v1/ads/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_saved }),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/ads/${id}`, { method: "DELETE" }),
  },
  content: {
    generate: (payload: GenerateContentPayload) =>
      request<GeneratedContent>("/api/v1/content/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    byId: (id: string) =>
      request<GeneratedContent>(`/api/v1/content/${id}`),
    list: async (params: {
      saved_only?: boolean;
      content_type?: ContentType;
      limit?: number;
    } = {}): Promise<GeneratedContent[]> => {
      const qs = new URLSearchParams();
      if (params.saved_only) qs.set("saved_only", "true");
      if (params.content_type) qs.set("content_type", params.content_type);
      if (params.limit) qs.set("limit", String(params.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      const res = await request<{ items: GeneratedContent[] }>(
        `/api/v1/content${suffix}`,
      );
      return res.items;
    },
    setSaved: (id: string, is_saved: boolean) =>
      request<GeneratedContent>(`/api/v1/content/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_saved }),
      }),
    delete: (id: string) =>
      request<null>(`/api/v1/content/${id}`, { method: "DELETE" }),

    // ----- ops (Phase 6.2B) -----
    search: async (params: ContentSearchParams = {}): Promise<ContentSearchResult> => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.content_type) qs.set("content_type", params.content_type);
      if (params.review_status) qs.set("review_status", params.review_status);
      if (params.folder_id) qs.set("folder_id", params.folder_id);
      if (params.campaign_id) qs.set("campaign_id", params.campaign_id);
      if (params.strategy_id) qs.set("strategy_id", params.strategy_id);
      if (params.saved_only) qs.set("saved_only", "true");
      if (params.limit != null) qs.set("limit", String(params.limit));
      if (params.offset != null) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request<ContentSearchResult>(`/api/v1/content/search${suffix}`);
    },
    versions: async (id: string): Promise<ContentVersion[]> => {
      const res = await request<{ items: ContentVersion[] }>(
        `/api/v1/content/${id}/versions`,
      );
      return res.items;
    },
    compareVersions: (id: string, a: number, b: number) =>
      request<VersionCompare>(
        `/api/v1/content/${id}/versions/compare?a=${a}&b=${b}`,
      ),
    restore: (id: string, version_no: number) =>
      request<GeneratedContent>(`/api/v1/content/${id}/restore`, {
        method: "POST",
        body: JSON.stringify({ version_no }),
      }),
    edit: (id: string, output: Record<string, unknown>, change_summary?: string) =>
      request<GeneratedContent>(`/api/v1/content/${id}/edit`, {
        method: "PATCH",
        body: JSON.stringify({ output, change_summary: change_summary ?? null }),
      }),
    review: (id: string, to_status: ReviewStatus, reason?: string) =>
      request<GeneratedContent>(`/api/v1/content/${id}/review`, {
        method: "POST",
        body: JSON.stringify({ to_status, reason: reason ?? null }),
      }),
    reviewHistory: async (id: string): Promise<ReviewEvent[]> => {
      const res = await request<{ items: ReviewEvent[] }>(
        `/api/v1/content/${id}/review/history`,
      );
      return res.items;
    },
    comments: async (id: string): Promise<ContentComment[]> => {
      const res = await request<{ items: ContentComment[] }>(
        `/api/v1/content/${id}/comments`,
      );
      return res.items;
    },
    addComment: (
      id: string,
      body: string,
      opts: { parent_id?: string; mentions?: string[] } = {},
    ) =>
      request<ContentComment>(`/api/v1/content/${id}/comments`, {
        method: "POST",
        body: JSON.stringify({
          body,
          parent_id: opts.parent_id ?? null,
          mentions: opts.mentions ?? [],
        }),
      }),
    resolveComment: (commentId: string, resolved: boolean) =>
      request<ContentComment>(`/api/v1/content/comments/${commentId}`, {
        method: "PATCH",
        body: JSON.stringify({ resolved }),
      }),
    folders: async (): Promise<ContentFolder[]> => {
      const res = await request<{ items: ContentFolder[] }>(
        `/api/v1/content/folders`,
      );
      return res.items;
    },
    createFolder: (
      name: string,
      opts: { kind?: "folder" | "collection"; parent_id?: string } = {},
    ) =>
      request<ContentFolder>(`/api/v1/content/folders`, {
        method: "POST",
        body: JSON.stringify({
          name,
          kind: opts.kind ?? "folder",
          parent_id: opts.parent_id ?? null,
        }),
      }),
    updateFolder: (
      folderId: string,
      patch: { name?: string; pinned?: boolean },
    ) =>
      request<ContentFolder>(`/api/v1/content/folders/${folderId}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    deleteFolder: (folderId: string) =>
      request<null>(`/api/v1/content/folders/${folderId}`, { method: "DELETE" }),
    assignFolder: (content_ids: string[], folder_id: string | null) =>
      request<{ moved: number }>(`/api/v1/content/folders/assign`, {
        method: "POST",
        body: JSON.stringify({ content_ids, folder_id }),
      }),
  },
  trends: {
    get: async (): Promise<TrendReport | null> => {
      try {
        return await request<TrendReport>("/api/v1/trends/report");
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    refresh: () =>
      request<TrendReport>("/api/v1/trends/refresh", { method: "POST" }),
  },
  business: {
    get: async (): Promise<BusinessProfile | null> => {
      try {
        return await request<BusinessProfile>("/api/v1/business/profile");
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    submit: (payload: BusinessProfileSubmitPayload) =>
      request<BusinessProfile>("/api/v1/business/onboarding", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (payload: Partial<BusinessProfileSubmitPayload>) =>
      request<BusinessProfile>("/api/v1/business/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    retryAnalysis: () =>
      request<BusinessProfile>("/api/v1/business/profile/retry-analysis", {
        method: "POST",
      }),
  },
  /**
   * Intelligent Onboarding — the AI reads a real website (or six answers)
   * and proposes a Brand Brain the user reviews before it's applied.
   * Start returns immediately (202); poll `get` for real stage progress.
   */
  discovery: {
    startWebsite: (payload: StartWebsiteDiscoveryPayload) =>
      request<{ id: string; status: string }>("/api/v1/discovery/website", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    startScratch: (payload: StartScratchDiscoveryPayload) =>
      request<{ id: string; status: string }>("/api/v1/discovery/scratch", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    get: (id: string) => request<DiscoveryRun>(`/api/v1/discovery/${id}`),
    apply: (
      id: string,
      payload: {
        draft: DiscoveryDraft;
        business_name?: string;
        industry?: string;
        website?: string;
      },
    ) =>
      request<BusinessProfile>(`/api/v1/discovery/${id}/apply`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  coach: {
    realityCheck: (payload: RealityCheckPayload) =>
      request<RealityCheck>("/api/v1/coach/reality-check", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    weekly: () =>
      dedupeRequest(
        `coach:weekly:${getActiveTenantHeaders().organization_id}:${getActiveTenantHeaders().brand_id}`,
        () => request<WeeklyPlan>("/api/v1/coach/weekly"),
        60_000,
      ),
    analyticsSummary: () =>
      request<AnalyticsSummary>("/api/v1/coach/analytics-summary"),
  },
  system: {
    /** Storage capability — whether durable object storage is configured. */
    storage: () => request<StorageStatus>("/api/v1/system/storage"),
  },
  competitors: {
    /**
     * AI analysis of the competitors in the brand's business profile.
     * One LLM call server-side; cached 30 min client-side (competitor
     * positioning doesn't shift minute-to-minute). Returns 409 when the
     * profile is missing or lists no competitors.
     */
    analysis: () =>
      dedupeRequest(
        `competitors:analysis:${getActiveTenantHeaders().organization_id}:${getActiveTenantHeaders().brand_id}`,
        () =>
          request<CompetitorAnalysisResponse>("/api/v1/competitors/analysis"),
        1_800_000,
      ),
  },
  opportunities: {
    /**
     * Phase 6 — Opportunity Center.
     *
     * Single LLM call server-side; the frontend caches for 30 minutes
     * via localStorage (same pattern as Lead Intelligence + Analytics
     * Summary). Returns 409 when business onboarding is incomplete.
     */
    center: () =>
      dedupeRequest(
        `opportunities:center:${getActiveTenantHeaders().organization_id}:${getActiveTenantHeaders().brand_id}`,
        () => request<OpportunityCenterReport>("/api/v1/opportunities"),
        60_000,
      ),
  },
  advisor: {
    /** Plain-language marketing health, computed from real data (no LLM). */
    health: () => request<MarketingHealth>("/api/v1/advisor/health"),
    history: () =>
      request<{ items: AdvisorHistoryItem[] }>("/api/v1/advisor/history").then(
        (r) => r.items,
      ),
    updateStatus: (recommendationId: string, status: RecommendationStatus) =>
      request<{ id: string; status: RecommendationStatus }>(
        `/api/v1/advisor/recommendations/${recommendationId}`,
        { method: "PATCH", body: JSON.stringify({ status }) },
      ),
    readiness: () =>
      request<{
        ready: boolean;
        message: string | null;
        suggested_setup_steps: string[];
      }>("/api/v1/advisor/readiness"),
    intelligence: () =>
      dedupeRequest(
        `advisor:intelligence:${getActiveTenantHeaders().organization_id}:${getActiveTenantHeaders().brand_id}`,
        () =>
          request<import("@/lib/intelligence-adapter").IntelligenceReport>(
            "/api/v1/advisor/intelligence",
          ),
        60_000,
      ),
    effectiveness: () =>
      request<{
        channels: Array<{
          dimension: string;
          key: string;
          label: string;
          success_rate: number | null;
          avg_effectiveness: number | null;
          sample_size: number;
        }>;
      }>("/api/v1/advisor/effectiveness"),
    brain: () =>
      request<{
        industry: string;
        business_type: string;
        target_audience: string;
        monthly_budget: string | null;
        growth_goal: string | null;
        location: string | null;
        competitors: string[];
        completeness_score: number;
        missing_steps: string[];
      }>("/api/v1/advisor/brain"),
    execute: (recommendationId: string) =>
      request<{
        asset_type: string;
        asset_id: string;
        content_asset_id: string | null;
        status: string;
        preview_url: string | null;
      }>("/api/v1/advisor/execute", {
        method: "POST",
        body: JSON.stringify({ recommendation_id: recommendationId }),
      }),
    schedule: (payload: {
      recommendation_id: string;
      platform: "instagram" | "google_business_profile";
      scheduled_at: string;
    }) =>
      request<ScheduledPost>("/api/v1/advisor/execute/schedule", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    agentReport: (
      reportType:
        | "daily"
        | "weekly"
        | "monthly"
        | "lead_trends"
        | "campaign_performance"
        | "budget",
    ) => request<AgentReport>(`/api/v1/advisor/agent/${reportType}`),
  },
  context: {
    snapshot: () => request<GenerationContext>("/api/v1/context/snapshot"),
  },
  social: {
    availability: async (): Promise<SocialAvailability[]> => {
      const r = await request<{ items: SocialAvailability[] }>(
        "/api/v1/social/availability",
      );
      return r.items;
    },
    connections: async (): Promise<SocialConnection[]> => {
      const r = await request<{ items: SocialConnection[] }>(
        "/api/v1/social/connections",
      );
      return r.items;
    },
    assets: async (
      platform?: SocialPlatform,
      limit = 25,
    ): Promise<SocialAsset[]> => {
      const qs = new URLSearchParams();
      qs.set("limit", String(limit));
      if (platform) qs.set("platform", platform);
      const r = await request<{ items: SocialAsset[] }>(
        `/api/v1/social/assets?${qs}`,
      );
      return r.items;
    },
    patterns: async (
      platform?: SocialPlatform,
    ): Promise<WinningPattern[]> => {
      const qs = new URLSearchParams();
      if (platform) qs.set("platform", platform);
      const suffix = qs.toString() ? `?${qs}` : "";
      const r = await request<{ items: WinningPattern[] }>(
        `/api/v1/social/patterns${suffix}`,
      );
      return r.items;
    },
    audiencePatterns: async (
      platform?: SocialPlatform,
    ): Promise<AudiencePattern[]> => {
      const qs = new URLSearchParams();
      if (platform) qs.set("platform", platform);
      const suffix = qs.toString() ? `?${qs}` : "";
      const r = await request<{ items: AudiencePattern[] }>(
        `/api/v1/social/audience-patterns${suffix}`,
      );
      return r.items;
    },
    import: (payload: ManualImportPayload) =>
      request<ImportResult>("/api/v1/social/import", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    analyze: (platform?: SocialPlatform) =>
      request<AnalyzeResult>("/api/v1/social/analyze", {
        method: "POST",
        body: JSON.stringify({ platform: platform ?? null }),
      }),
    oauthInit: (platform: SocialPlatform) =>
      request<{ authorize_url: string }>(
        `/api/v1/social/oauth/${platform}/init`,
      ),
    disconnect: (platform: SocialPlatform) =>
      request<void>(`/api/v1/social/disconnect/${platform}`, {
        method: "POST",
      }),
    sync: (platform: SocialPlatform, limit = 25) =>
      request<ImportResult>(`/api/v1/social/sync/${platform}?limit=${limit}`, {
        method: "POST",
      }),
  },
  integrations: {
    catalog: async (): Promise<IntegrationCatalogEntry[]> => {
      const r = await request<{ items: IntegrationCatalogEntry[] }>(
        "/api/v1/integrations",
      );
      return r.items;
    },
    connect: (slug: string, redirectUri: string) =>
      request<{
        connection_id: string;
        authorize_url: string;
        state: IntegrationConnectionState;
      }>(
        `/api/v1/integrations/${slug}/connect?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { method: "POST" },
      ),
    sync: (connectionId: string) =>
      request<IntegrationSyncResult>(
        `/api/v1/integrations/${connectionId}/sync`,
        { method: "POST" },
      ),
    disconnect: (connectionId: string) =>
      request<IntegrationConnection>(
        `/api/v1/integrations/${connectionId}/disconnect`,
        { method: "POST" },
      ),
    events: async (q: IntegrationEventQuery = {}): Promise<IntegrationEvent[]> => {
      const params = new URLSearchParams();
      if (q.connection_id) params.set("connection_id", q.connection_id);
      if (q.provider) params.set("provider", q.provider);
      if (q.event_type) params.set("event_type", q.event_type);
      if (q.status) params.set("status", q.status);
      params.set("limit", String(q.limit ?? 200));
      const r = await request<{ items: IntegrationEvent[] }>(
        `/api/v1/integrations/events?${params.toString()}`,
      );
      return r.items;
    },
    analytics: (days = 30) =>
      request<IntegrationAnalytics>(
        `/api/v1/integrations/analytics?days=${days}`,
      ),
  },
  publishing: {
    calendar: async (): Promise<ScheduledPost[]> => {
      const r = await request<{ items: ScheduledPost[] }>("/api/v1/publishing/calendar");
      return r.items;
    },
    schedule: (payload: {
      content_asset_id: string;
      platform: PublishPlatform;
      scheduled_at: string;
    }) =>
      request<ScheduledPost>("/api/v1/publishing/schedule", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    /** Publish a scheduled post immediately. */
    publishNow: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/publish/${id}`, {
        method: "POST",
      }),
    /** Operator retry of a failed post — resets the attempt budget + re-publishes. */
    retry: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/retry`, {
        method: "POST",
      }),
    /** Audit trail for a scheduled post (scheduled / attempts / published / failed). */
    events: async (id: string): Promise<PublishEvent[]> => {
      const r = await request<{ items: PublishEvent[] }>(
        `/api/v1/publishing/posts/${id}/events`,
      );
      return r.items;
    },
    // ----- Phase 6.4 enterprise queue ops -----
    analytics: () => request<QueueAnalytics>("/api/v1/publishing/analytics"),
    cancel: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/cancel`, { method: "POST" }),
    pause: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/pause`, { method: "POST" }),
    resume: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/resume`, { method: "POST" }),
    reschedule: (id: string, scheduled_at: string, schedule_timezone?: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/reschedule`, {
        method: "POST",
        body: JSON.stringify({ scheduled_at, schedule_timezone: schedule_timezone ?? null }),
      }),
    submitForApproval: (id: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/submit`, { method: "POST" }),
    approve: (id: string, reason?: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ reason: reason ?? null }),
      }),
    reject: (id: string, reason?: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: reason ?? null }),
      }),
    requestChanges: (id: string, reason?: string) =>
      request<ScheduledPost>(`/api/v1/publishing/posts/${id}/request-changes`, {
        method: "POST",
        body: JSON.stringify({ reason: reason ?? null }),
      }),
  },
  crm: {
    pipelines: async (): Promise<CrmPipeline[]> => {
      const r = await request<{ items: CrmPipeline[] }>("/api/v1/crm/pipelines");
      return r.items;
    },
    createPipeline: (payload: { name: string; kind?: CrmPipelineKind }) =>
      request<CrmPipeline>("/api/v1/crm/pipelines", {
        method: "POST",
        body: JSON.stringify({ ...payload, stages: [] }),
      }),
    analytics: (pipelineId?: string) =>
      request<CrmAnalytics>(
        `/api/v1/crm/analytics${pipelineId ? `?pipeline_id=${pipelineId}` : ""}`,
      ),
    deals: async (params: {
      pipeline_id?: string;
      status?: CrmDealStatus;
      q?: string;
      limit?: number;
    } = {}): Promise<{ items: CrmDeal[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.pipeline_id) qs.set("pipeline_id", params.pipeline_id);
      if (params.status) qs.set("status", params.status);
      if (params.q) qs.set("q", params.q);
      qs.set("limit", String(params.limit ?? 200));
      return request<{ items: CrmDeal[]; total: number }>(`/api/v1/crm/deals?${qs}`);
    },
    createDeal: (payload: CrmDealCreate) =>
      request<CrmDeal>("/api/v1/crm/deals", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateDeal: (id: string, patch: Partial<CrmDealCreate>) =>
      request<CrmDeal>(`/api/v1/crm/deals/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    moveDeal: (id: string, stage_id: string, note?: string) =>
      request<CrmDeal>(`/api/v1/crm/deals/${id}/move`, {
        method: "POST",
        body: JSON.stringify({ stage_id, note: note ?? null }),
      }),
    closeDeal: (id: string, status: "won" | "lost", lost_reason?: string) =>
      request<CrmDeal>(`/api/v1/crm/deals/${id}/close`, {
        method: "POST",
        body: JSON.stringify({ status, lost_reason: lost_reason ?? null }),
      }),
    deleteDeal: (id: string) =>
      request<null>(`/api/v1/crm/deals/${id}`, { method: "DELETE" }),
    nextAction: (id: string) =>
      request<CrmDeal>(`/api/v1/crm/deals/${id}/next-action`, { method: "POST" }),

    // ----- Slice 2: companies -----
    companies: async (params: { q?: string; limit?: number } = {}): Promise<{ items: CrmCompany[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      qs.set("limit", String(params.limit ?? 100));
      return request<{ items: CrmCompany[]; total: number }>(`/api/v1/crm/companies?${qs}`);
    },
    createCompany: (payload: CrmCompanyCreate) =>
      request<CrmCompany>("/api/v1/crm/companies", { method: "POST", body: JSON.stringify(payload) }),
    company: (id: string) => request<CrmCompanyDetail>(`/api/v1/crm/companies/${id}`),
    updateCompany: (id: string, patch: Partial<CrmCompanyCreate>) =>
      request<CrmCompany>(`/api/v1/crm/companies/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteCompany: (id: string) =>
      request<null>(`/api/v1/crm/companies/${id}`, { method: "DELETE" }),
    companyDuplicates: (id: string) =>
      request<{ items: CrmDuplicate[] }>(`/api/v1/crm/companies/${id}/duplicates`),
    mergeCompany: (survivorId: string, duplicateId: string) =>
      request<CrmCompany>(`/api/v1/crm/companies/${survivorId}/merge`, {
        method: "POST", body: JSON.stringify({ duplicate_id: duplicateId }),
      }),
    companyHealth: (id: string) =>
      request<CrmCompany>(`/api/v1/crm/companies/${id}/health`, { method: "POST" }),
    companySummary: (id: string) =>
      request<CrmCompany>(`/api/v1/crm/companies/${id}/summary`, { method: "POST" }),
    companyActivities: async (id: string): Promise<CrmActivity[]> => {
      const r = await request<{ items: CrmActivity[] }>(`/api/v1/crm/companies/${id}/activities`);
      return r.items;
    },

    // ----- Slice 2: contacts -----
    contacts: async (params: { q?: string; company_id?: string; limit?: number } = {}): Promise<{ items: CrmContact[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.company_id) qs.set("company_id", params.company_id);
      qs.set("limit", String(params.limit ?? 100));
      return request<{ items: CrmContact[]; total: number }>(`/api/v1/crm/contacts?${qs}`);
    },
    createContact: (payload: CrmContactCreate) =>
      request<CrmContact>("/api/v1/crm/contacts", { method: "POST", body: JSON.stringify(payload) }),
    contact: (id: string) => request<CrmContactDetail>(`/api/v1/crm/contacts/${id}`),
    updateContact: (id: string, patch: Partial<CrmContactCreate>) =>
      request<CrmContact>(`/api/v1/crm/contacts/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteContact: (id: string) =>
      request<null>(`/api/v1/crm/contacts/${id}`, { method: "DELETE" }),
    contactDuplicates: (id: string) =>
      request<{ items: CrmDuplicate[] }>(`/api/v1/crm/contacts/${id}/duplicates`),
    mergeContact: (survivorId: string, duplicateId: string) =>
      request<CrmContact>(`/api/v1/crm/contacts/${survivorId}/merge`, {
        method: "POST", body: JSON.stringify({ duplicate_id: duplicateId }),
      }),
    contactSummary: (id: string) =>
      request<CrmContact>(`/api/v1/crm/contacts/${id}/summary`, { method: "POST" }),
    contactActivities: async (id: string): Promise<CrmActivity[]> => {
      const r = await request<{ items: CrmActivity[] }>(`/api/v1/crm/contacts/${id}/activities`);
      return r.items;
    },
    logActivity: (payload: CrmActivityCreate) =>
      request<CrmActivity>("/api/v1/crm/activities", { method: "POST", body: JSON.stringify(payload) }),

    // ----- Slice 3: tasks & calendar -----
    tasks: async (params: {
      queue?: string;
      status?: string;
      activity_type?: string;
      deal_id?: string;
      contact_id?: string;
      company_id?: string;
      q?: string;
      limit?: number;
    } = {}): Promise<{ items: CrmTask[]; total: number }> => {
      const qs = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v != null && v !== "") qs.set(k, String(v));
      });
      return request<{ items: CrmTask[]; total: number }>(`/api/v1/crm/tasks?${qs}`);
    },
    calendar: async (start: string, end: string): Promise<CrmTask[]> => {
      const r = await request<{ items: CrmTask[] }>(
        `/api/v1/crm/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
      );
      return r.items;
    },
    createTask: (payload: CrmTaskCreate) =>
      request<CrmTask>("/api/v1/crm/tasks", { method: "POST", body: JSON.stringify(payload) }),
    task: (id: string) => request<CrmTask>(`/api/v1/crm/tasks/${id}`),
    updateTask: (id: string, patch: Partial<CrmTaskCreate> & { status?: CrmTaskStatus }) =>
      request<CrmTask>(`/api/v1/crm/tasks/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteTask: (id: string) =>
      request<null>(`/api/v1/crm/tasks/${id}`, { method: "DELETE" }),
    completeTask: (id: string, actual_minutes?: number, notes?: string) =>
      request<CrmTask>(`/api/v1/crm/tasks/${id}/complete`, {
        method: "POST",
        body: JSON.stringify({ actual_minutes: actual_minutes ?? null, notes: notes ?? null }),
      }),
    suggestTask: (id: string) =>
      request<CrmTask>(`/api/v1/crm/tasks/${id}/suggest`, { method: "POST" }),

    // ----- Slice 4: email platform -----
    emailTemplates: async (params: { category?: string; q?: string } = {}): Promise<{ items: CrmEmailTemplate[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.category) qs.set("category", params.category);
      if (params.q) qs.set("q", params.q);
      return request<{ items: CrmEmailTemplate[]; total: number }>(`/api/v1/crm/email/templates?${qs}`);
    },
    createEmailTemplate: (payload: CrmEmailTemplateCreate) =>
      request<CrmEmailTemplate>("/api/v1/crm/email/templates", { method: "POST", body: JSON.stringify(payload) }),
    updateEmailTemplate: (id: string, patch: Partial<CrmEmailTemplateCreate> & { edit_summary?: string; is_active?: boolean }) =>
      request<CrmEmailTemplate>(`/api/v1/crm/email/templates/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    deleteEmailTemplate: (id: string) =>
      request<null>(`/api/v1/crm/email/templates/${id}`, { method: "DELETE" }),
    renderEmailTemplate: (id: string, variables: Record<string, string>, contact_id?: string) =>
      request<{ subject: string; body: string; unresolved: string[] }>(`/api/v1/crm/email/templates/${id}/render`, {
        method: "POST", body: JSON.stringify({ variables, contact_id: contact_id ?? null }),
      }),
    emailTemplateVersions: async (id: string): Promise<CrmEmailTemplateVersion[]> => {
      const r = await request<{ items: CrmEmailTemplateVersion[] }>(`/api/v1/crm/email/templates/${id}/versions`);
      return r.items;
    },
    emailSequences: async (): Promise<CrmEmailSequence[]> => {
      const r = await request<{ items: CrmEmailSequence[] }>("/api/v1/crm/email/sequences");
      return r.items;
    },
    createEmailSequence: (payload: { name: string; description?: string; steps: { template_id?: string; delay_hours?: number; stop_on_reply?: boolean; wait_for_open?: boolean }[] }) =>
      request<CrmEmailSequence>("/api/v1/crm/email/sequences", { method: "POST", body: JSON.stringify(payload) }),
    updateEmailSequence: (id: string, patch: { status?: "draft" | "active" | "archived"; name?: string }) =>
      request<CrmEmailSequence>(`/api/v1/crm/email/sequences/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    enrollInSequence: (sequenceId: string, contact_id?: string, to_email?: string) =>
      request<unknown>(`/api/v1/crm/email/sequences/${sequenceId}/enroll`, {
        method: "POST", body: JSON.stringify({ contact_id: contact_id ?? null, to_email: to_email ?? null }),
      }),
    runSequences: () => request<{ processed: number }>("/api/v1/crm/email/sequences/run", { method: "POST" }),
    sendEmail: (payload: { to_email: string; subject: string; body: string; template_id?: string; contact_id?: string; deal_id?: string }) =>
      request<CrmEmail>("/api/v1/crm/email/send", { method: "POST", body: JSON.stringify(payload) }),
    emails: async (params: { contact_id?: string; deal_id?: string } = {}): Promise<{ items: CrmEmail[]; total: number }> => {
      const qs = new URLSearchParams();
      if (params.contact_id) qs.set("contact_id", params.contact_id);
      if (params.deal_id) qs.set("deal_id", params.deal_id);
      return request<{ items: CrmEmail[]; total: number }>(`/api/v1/crm/email/emails?${qs}`);
    },
    emailStats: () => request<CrmEmailStats>("/api/v1/crm/email/stats"),

    // ----- Slice 5: AI Sales Assistant -----
    generateInsight: (subjectType: CrmInsightSubject, subjectId: string, opts: { kind?: string; force?: boolean } = {}) =>
      request<CrmInsight>(`/api/v1/crm/insights/${subjectType}/${subjectId}`, {
        method: "POST",
        body: JSON.stringify({ kind: opts.kind ?? null, force: opts.force ?? false }),
      }),
    insights: async (params: { subject_type?: CrmInsightSubject; subject_id?: string } = {}): Promise<CrmInsight[]> => {
      const qs = new URLSearchParams();
      if (params.subject_type) qs.set("subject_type", params.subject_type);
      if (params.subject_id) qs.set("subject_id", params.subject_id);
      const r = await request<{ items: CrmInsight[] }>(`/api/v1/crm/insights?${qs}`);
      return r.items;
    },

    // ----- Slice 6: executive dashboard -----
    dashboard: (params: { pipeline_id?: string; owner_user_id?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.pipeline_id) qs.set("pipeline_id", params.pipeline_id);
      if (params.owner_user_id) qs.set("owner_user_id", params.owner_user_id);
      return request<CrmExecutiveDashboard>(`/api/v1/crm/dashboard?${qs}`);
    },
    dashboardExportUrl: (params: { pipeline_id?: string; owner_user_id?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.pipeline_id) qs.set("pipeline_id", params.pipeline_id);
      if (params.owner_user_id) qs.set("owner_user_id", params.owner_user_id);
      return `${API_URL}/api/v1/crm/dashboard/export?${qs}`;
    },
  },
  bundles: {
    list: async (limit = 20): Promise<CampaignBundle[]> => {
      const res = await request<{ items: CampaignBundle[] }>(
        `/api/v1/bundles?limit=${limit}`,
      );
      return res.items;
    },
    get: (id: string) =>
      request<CampaignBundle>(`/api/v1/bundles/${id}`),
    generate: (payload: GenerateBundlePayload) =>
      request<CampaignBundle>("/api/v1/bundles/generate", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  learning: {
    experiments: async (opts?: {
      status?: ExperimentStatus;
      platform?: string;
      limit?: number;
    }): Promise<CampaignExperiment[]> => {
      const qs = new URLSearchParams();
      if (opts?.status) qs.set("status", opts.status);
      if (opts?.platform) qs.set("platform", opts.platform);
      qs.set("limit", String(opts?.limit ?? 50));
      const r = await request<{ items: CampaignExperiment[] }>(
        `/api/v1/learning/experiments?${qs}`,
      );
      return r.items;
    },
    results: async (experimentId: string): Promise<ExperimentResult[]> => {
      const r = await request<{ items: ExperimentResult[] }>(
        `/api/v1/learning/experiments/${experimentId}/results`,
      );
      return r.items;
    },
    events: async (opts?: {
      variable?: string;
      only_active?: boolean;
      limit?: number;
    }): Promise<LearningEvent[]> => {
      const qs = new URLSearchParams();
      if (opts?.variable) qs.set("variable", opts.variable);
      qs.set("only_active", String(opts?.only_active ?? true));
      qs.set("limit", String(opts?.limit ?? 50));
      const r = await request<{ items: LearningEvent[] }>(
        `/api/v1/learning/events?${qs}`,
      );
      return r.items;
    },
    archiveEvent: (id: string) =>
      request<LearningEvent>(`/api/v1/learning/events/${id}/archive`, {
        method: "POST",
      }),
    archiveExperiment: (id: string) =>
      request<CampaignExperiment>(
        `/api/v1/learning/experiments/${id}/archive`,
        { method: "POST" },
      ),
    provenance: (sourceAssetId: string) =>
      request<ExperimentProvenance>(
        `/api/v1/learning/provenance/${sourceAssetId}`,
      ),
    analyze: (variable?: string) =>
      request<LearningRunResult>("/api/v1/learning/analyze", {
        method: "POST",
        body: JSON.stringify({ variable: variable ?? null }),
      }),
  },
  /**
   * Single-shot onboarding wizard (W1-15). No tenant headers — this
   * IS the call that creates the tenant. Sends explicit null overrides
   * to suppress any stale cached headers from a previous session.
   */
  onboarding: {
    createWorkspace: (payload: OnboardingWorkspacePayload) =>
      request<OnboardingWorkspaceResult>("/api/v1/orgs/workspace", {
        method: "POST",
        body: JSON.stringify(payload),
        organizationId: null,
        brandId: null,
      }),
  },
  /**
   * Organization danger-zone operations (owner-only on the backend).
   *
   * `reset` wipes all user-provided content (business profile, campaigns,
   * content, leads, creatives, …) but keeps the workspace shell so the
   * founder can start clean without re-creating the org.
   *
   * `purge` HARD-deletes the org and everything in it — irreversible.
   *
   * Both target the ACTIVE org and rely on the cached tenant headers
   * (the backend enforces that the path org_id matches X-Organization-Id).
   */
  orgs: {
    reset: (orgId: string) =>
      request<OrganizationResetResult>(`/api/v1/orgs/${orgId}/reset`, {
        method: "POST",
      }),
    purge: (orgId: string) =>
      request<{ status: string }>(`/api/v1/orgs/${orgId}/purge`, {
        method: "POST",
      }),
    /** Roster for the active org. `includeInactive` also returns suspended
     *  members (for the enterprise Members page). */
    members: (orgId: string, includeInactive = false) =>
      request<{ items: OrgMember[] }>(
        `/api/v1/orgs/${orgId}/members${includeInactive ? "?include_inactive=true" : ""}`,
      ),
    assignMemberRole: (orgId: string, memberId: string, roleSlug: string) =>
      request<{ role_slugs: string[] }>(
        `/api/v1/orgs/${orgId}/members/${memberId}/roles`,
        { method: "POST", body: JSON.stringify({ role_slug: roleSlug }) },
      ),
    removeMemberRole: (orgId: string, memberId: string, roleSlug: string) =>
      request<{ role_slugs: string[] }>(
        `/api/v1/orgs/${orgId}/members/${memberId}/roles/${roleSlug}`,
        { method: "DELETE" },
      ),
    deactivateMember: (orgId: string, memberId: string) =>
      request<OrgMember>(
        `/api/v1/orgs/${orgId}/members/${memberId}/deactivate`,
        { method: "POST" },
      ),
    reactivateMember: (orgId: string, memberId: string) =>
      request<OrgMember>(
        `/api/v1/orgs/${orgId}/members/${memberId}/reactivate`,
        { method: "POST" },
      ),
    removeMember: (orgId: string, memberId: string) =>
      request<{ status: string }>(
        `/api/v1/orgs/${orgId}/members/${memberId}`,
        { method: "DELETE" },
      ),
    /** Hand the workspace Owner role to another member. Owner-only. */
    transferOwnership: (orgId: string, memberId: string) =>
      request<{ status: string }>(
        `/api/v1/orgs/${orgId}/members/${memberId}/transfer-ownership`,
        { method: "POST" },
      ),
  },
  /**
   * Phase 6.6 Slice 4 — org-wide audit log. Read-only; gated on
   * `organization.manage` server-side. Powers the Settings · Audit page.
   */
  audit: {
    list: (orgId: string, query: AuditQuery = {}) => {
      const p = new URLSearchParams();
      for (const a of query.action ?? []) p.append("action", a);
      if (query.actor_user_id) p.set("actor_user_id", query.actor_user_id);
      if (query.target_type) p.set("target_type", query.target_type);
      if (query.since) p.set("since", query.since);
      if (query.until) p.set("until", query.until);
      if (query.search) p.set("search", query.search);
      if (query.limit) p.set("limit", String(query.limit));
      const qs = p.toString();
      return request<AuditEventList>(
        `/api/v1/orgs/${orgId}/audit${qs ? `?${qs}` : ""}`,
      );
    },
  },
  /**
   * Phase 6.6 — Enterprise Role Management.
   *
   * Roles + the permission catalog + the role-scoped audit trail. All
   * role writes gate on `team.manage` server-side. `permissions()` is the
   * catalog every editor renders against — never hardcode permission
   * slugs in the UI; group by the `category` field the backend returns.
   */
  rbac: {
    permissions: () =>
      request<{ items: RbacPermission[] }>("/api/v1/rbac/permissions"),
    listRoles: (orgId: string) =>
      request<{ items: RbacRole[] }>(`/api/v1/orgs/${orgId}/roles`),
    getRole: (orgId: string, roleId: string) =>
      request<RbacRole>(`/api/v1/orgs/${orgId}/roles/${roleId}`),
    createRole: (orgId: string, payload: RoleWritePayload) =>
      request<RbacRole>(`/api/v1/orgs/${orgId}/roles`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    updateRole: (
      orgId: string,
      roleId: string,
      payload: Partial<RoleWritePayload>,
    ) =>
      request<RbacRole>(`/api/v1/orgs/${orgId}/roles/${roleId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    deleteRole: (orgId: string, roleId: string) =>
      request<void>(`/api/v1/orgs/${orgId}/roles/${roleId}`, {
        method: "DELETE",
      }),
    reorderRoles: (orgId: string, items: RoleReorderItem[]) =>
      request<{ items: RbacRole[] }>(`/api/v1/orgs/${orgId}/roles/reorder`, {
        method: "POST",
        body: JSON.stringify({ items }),
      }),
    duplicateRole: (
      orgId: string,
      roleId: string,
      payload: { slug: string; name: string },
    ) =>
      request<RbacRole>(`/api/v1/orgs/${orgId}/roles/${roleId}/duplicate`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    roleAudit: (orgId: string, roleId: string) =>
      request<{ items: RoleAuditEvent[] }>(
        `/api/v1/orgs/${orgId}/roles/${roleId}/audit`,
      ),
  },
  /**
   * LinkedIn Poster Studio — topic → branded announcement poster (image)
   * + a long-form LinkedIn caption. Flag-gated (`poster_enabled`) on the
   * backend; `capabilities()` tells the UI whether to offer it.
   */
  poster: {
    capabilities: () =>
      request<{ enabled: boolean; renderer_available: boolean }>(
        "/api/v1/poster/capabilities",
      ),
    compose: (payload: {
      topic: string;
      goal?: string | null;
      generate_image?: boolean;
    }) =>
      request<LinkedInComposeResult>("/api/v1/poster/linkedin/compose", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    render: (payload: { fields: LinkedInCopy; generate_image?: boolean }) =>
      request<LinkedInComposeResult>("/api/v1/poster/linkedin/render", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  /**
   * Phase 9.1 — Performance Intelligence Engine.
   *
   * CSV-only ingest in Phase 9.1 (no Meta/Google connectors yet).
   * Upload sends a `multipart/form-data` blob; we let the browser
   * set the Content-Type header so the boundary is correct. That's
   * why `upload` builds its own fetch instead of going through
   * `request()` (which forces application/json).
   */
  performance: {
    overview: () =>
      request<PerformanceOverview>("/api/v1/performance/overview"),
    upload: async (file: File): Promise<CsvIngestSummary> => {
      const form = new FormData();
      form.append("file", file);

      const headers = new Headers();
      const token = await getAuthToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const { organization_id, brand_id } = getActiveTenantHeaders();
      if (organization_id) headers.set("X-Organization-Id", organization_id);
      if (brand_id) headers.set("X-Brand-Id", brand_id);

      const res = await fetch(`${API_URL}/api/v1/performance/upload-csv`, {
        method: "POST",
        body: form,
        headers,
      });
      if (!res.ok) {
        const text = await res.text();
        let body: unknown = text;
        try {
          body = JSON.parse(text);
        } catch {
          // not JSON — keep raw text in body
        }
        const detail =
          body && typeof body === "object" && "detail" in body
            ? formatDetail((body as { detail: unknown }).detail)
            : `Upload failed (${res.status})`;
        throw new ApiError(detail, res.status, body);
      }
      return (await res.json()) as CsvIngestSummary;
    },
    dismissDiagnostic: (id: string) =>
      request<void>(`/api/v1/performance/diagnostics/${id}/dismiss`, {
        method: "POST",
      }),
    /**
     * DELETE every ingested CSV row, rollup, and diagnostic for the
     * active brand. Idempotent. Use to clear stale test data or to
     * start over after a bad upload.
     */
    resetData: () =>
      request<void>("/api/v1/performance/data", { method: "DELETE" }),
  },

  /**
   * Creative Studio (CS1) — the outcome layer. Flag-gated behind
   * studio_enabled on the backend (409 when off). Industry is never a
   * parameter here — only the outcome (objective_kind) + a free-text goal.
   */
  growth: {
    objectiveKinds: () =>
      request<ObjectiveKind[]>("/api/v1/growth/objective-kinds"),
    listObjectives: async (): Promise<GrowthObjective[]> => {
      const res = await request<{ items: GrowthObjective[] }>(
        "/api/v1/growth/objectives",
      );
      return res.items;
    },
    createObjective: (payload: {
      objective_kind: string;
      statement: string;
      audience_hypothesis?: string | null;
      budget_cents?: number | null;
    }) =>
      request<GrowthObjective>("/api/v1/growth/objectives", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    // Objective → strategy + a set of editable creatives (poster/carousel/ad/reel).
    buildCampaign: (objectiveId: string) =>
      request<CampaignBuildResponse>(
        `/api/v1/growth/objectives/${objectiveId}/build-campaign`,
        { method: "POST", body: JSON.stringify({}) },
      ),
  },

  /**
   * Creative Studio (CS1) — the editable design model. Every mutating call
   * returns a new design head backed by an immutable revision (Law 3). CS1
   * exposes read + the three write modes; the interactive canvas lands in CS5.
   */
  studio: {
    listDesigns: async (): Promise<DesignSummary[]> => {
      const res = await request<{ items: DesignSummary[] }>(
        "/api/v1/creative/designs",
      );
      return res.items;
    },
    getDesign: (id: string) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}`),
    listRevisions: async (id: string): Promise<RevisionSummary[]> => {
      const res = await request<{ items: RevisionSummary[] }>(
        `/api/v1/creative/designs/${id}/revisions`,
      );
      return res.items;
    },
    createDesign: (payload: {
      name: string;
      media_type?: string;
      format_slug?: string | null;
      growth_objective_id?: string | null;
      headline?: string | null;
      subhead?: string | null;
      cta?: string | null;
    }) =>
      request<DesignResponse>("/api/v1/creative/designs", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    // Guided Mode — AI modifies the design.
    aiEdit: (id: string, payload: { instruction: string; base_revision: number }) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}/ai-edit`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    // Unified NL editor — router decides edit/regenerate/transform/restyle/variant.
    // preview:true plans without committing; preview:false commits via apply_revision.
    nlEdit: (
      id: string,
      payload: { instruction: string; base_revision: number; preview: boolean },
    ) =>
      request<NlEditResponse>(`/api/v1/creative/designs/${id}/nl-edit`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    // Pro Mode — human modifies the design (ops or full doc).
    proEdit: (
      id: string,
      payload: { base_revision: number; ops?: unknown[]; doc?: unknown },
    ) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    transform: (
      id: string,
      payload: {
        kind: "reformat" | "recompose" | "remediate";
        base_revision: number;
        target_format_slug?: string | null;
      },
    ) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}/transform`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    restyle: (id: string, payload: { style: string; base_revision: number }) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}/restyle`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    revert: (
      id: string,
      payload: { target_revision: number; base_revision: number },
    ) =>
      request<DesignResponse>(`/api/v1/creative/designs/${id}/revert`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    // Brand asset library (logos / product / team / icons / illustrations).
    brandAssets: {
      list: async (
        params: { kind?: string; q?: string; favorites?: boolean } = {},
      ): Promise<BrandAsset[]> => {
        const qs = new URLSearchParams();
        if (params.kind) qs.set("kind", params.kind);
        if (params.q) qs.set("q", params.q);
        if (params.favorites) qs.set("favorites", "true");
        const suffix = qs.toString() ? `?${qs}` : "";
        const res = await request<{ items: BrandAsset[] }>(
          `/api/v1/creative/brand-assets${suffix}`,
        );
        return res.items;
      },
      upload: async (file: File, kind = "image", label?: string): Promise<BrandAsset> => {
        const form = new FormData();
        form.append("file", file);
        form.append("kind", kind);
        if (label) form.append("label", label);
        const headers = new Headers();
        const token = await getAuthToken();
        if (token) headers.set("Authorization", `Bearer ${token}`);
        const { organization_id, brand_id } = getActiveTenantHeaders();
        if (organization_id) headers.set("X-Organization-Id", organization_id);
        if (brand_id) headers.set("X-Brand-Id", brand_id);
        const res = await fetch(`${API_URL}/api/v1/creative/brand-assets/upload`, {
          method: "POST",
          body: form,
          headers,
        });
        if (!res.ok) throw new Error((await res.text()) || "Upload failed");
        return res.json();
      },
      favorite: (id: string) =>
        request<BrandAsset>(`/api/v1/creative/brand-assets/${id}/favorite`, { method: "POST" }),
      removeBg: (id: string) =>
        request<BrandAsset>(`/api/v1/creative/brand-assets/${id}/remove-bg`, { method: "POST" }),
      stock: (q: string) =>
        request<StockResult[]>(`/api/v1/creative/brand-assets/stock?q=${encodeURIComponent(q)}`),
    },

    // CS6 — render a reel design into an MP4 (async), poll status, export.
    renderVideo: (id: string) =>
      request<VideoRenderResponse>(`/api/v1/creative/designs/${id}/render-video`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    videoStatus: (id: string) =>
      request<VideoStatus>(`/api/v1/creative/designs/${id}/video`),
    createExports: (assetId: string, platforms: string[]) =>
      request<{ items: VideoExport[] }>(`/api/v1/creative/assets/${assetId}/exports`, {
        method: "POST",
        body: JSON.stringify({ platforms }),
      }).then((r) => r.items),
    listExports: (assetId: string) =>
      request<{ items: VideoExport[] }>(`/api/v1/creative/assets/${assetId}/exports`).then(
        (r) => r.items,
      ),

    // Phase 6.3 — AI Creative Brief, grounded in real context.
    brief: {
      generate: (payload: GenerateBriefPayload) =>
        request<CreativeBrief>("/api/v1/creative/brief", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
      list: async (): Promise<CreativeBrief[]> => {
        const res = await request<{ items: CreativeBrief[] }>("/api/v1/creative/briefs");
        return res.items;
      },
      byId: (id: string) => request<CreativeBrief>(`/api/v1/creative/briefs/${id}`),
    },
  },
};

// ---------- Performance Intelligence (Phase 9.1) ----------

export type PerformanceImpactCategory =
  | "revenue"
  | "lead"
  | "customer"
  | "time"
  | "cost";

export type PerformanceDiagnosticKind =
  // 9.1 baseline
  | "winner"
  | "loser"
  | "fatigue"
  | "audience_shift"
  | "budget_reallocation"
  // 9.1.5 — Performance Marketer Brain (keep in lock-step with
  // apps/api/aicmo/modules/performance/schemas.py and migration 0021)
  | "audience_winner"
  | "audience_loser"
  | "concept_winner"
  | "emotion_winner"
  | "funnel_winner"
  | "pattern_winner"
  | "offer_winner"
  | "offer_pricing_sensitivity"
  | "scale_candidate"
  | "budget_waste"
  | "creative_dna";

export type PerformanceDiagnosticStatus =
  | "open"
  | "acted_on"
  | "dismissed"
  | "expired";

export interface PerformanceDiagnosticCard {
  id: string;
  kind: PerformanceDiagnosticKind;
  impact_category: PerformanceImpactCategory;
  what_happened: string;
  why: string;
  recommendation: string;
  expected_result: string;
  reason: string;
  confidence: number;
  evidence: Record<string, unknown>;
  status: PerformanceDiagnosticStatus;
  created_at: string;
}

export interface PerformanceOverview {
  has_data: boolean;
  rows_ingested: number;
  creatives_tracked: number;
  last_upload_at: string | null;
  diagnostics: PerformanceDiagnosticCard[];
}

export interface CsvParseError {
  row_number: number;
  raw: Record<string, string>;
  error: string;
}

export interface CsvIngestSummary {
  upload_id: string;
  rows_accepted: number;
  rows_rejected: number;
  creatives_matched: number;
  creatives_unmatched: number;
  date_range: [string, string] | null;
  currency: string | null;
  errors: CsvParseError[];
}

// ---------- Onboarding wizard (W1-15 + A4 + P-series) ----------

export type OnboardingPersona =
  | "solo_founder"
  | "in_house_marketer"
  | "agency"
  | "freelancer"
  | "consultant"
  | "other";

export interface OnboardingWorkspacePayload {
  organization_name: string;
  organization_slug: string;
  brand_name: string;
  brand_slug: string;
  display_name?: string | null;
  // A4 — optional business-profile bundle. Backend creates a
  // BusinessProfile in the same TX when all required-for-profile fields
  // are present; otherwise skips.
  industry?: string | null;
  website?: string | null;
  brand_description?: string | null;
  target_audience?: string | null;
  primary_goal?: string | null;
  preferred_platforms?: string[];
  brand_tone?: string | null;
  // P-series — optional persona segmentation. NOT an authorization
  // role. Keep allowed values in sync with the backend's Literal in
  // apps/api/aicmo/modules/orgs/schemas.py and the wizard's PERSONAS
  // constant in onboarding-wizard.tsx.
  persona?: OnboardingPersona | null;
}

export interface OnboardingWorkspaceResult {
  organization_id: string;
  organization_slug: string;
  organization_name: string;
  brand_id: string;
  brand_slug: string;
  brand_name: string;
  member_id: string;
  role_slugs: string[];
}

/** Result of POST /orgs/{id}/reset — what the danger-zone reset cleared. */
export interface OrganizationResetResult {
  organization_id: string;
  tables_cleared: number;
  rows_deleted: number;
  details: Record<string, number>;
}

// ---- Phase 6.6 — Enterprise Role Management ----

/** One entry in the permission catalog (GET /rbac/permissions). */
export interface RbacPermission {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  category: string;
}

/**
 * A role with its embedded grants. `permission_slugs` is the ALLOW set,
 * `deny_slugs` the explicit-DENY set; a permission in neither is INHERIT.
 */
export interface RbacRole {
  id: string;
  organization_id: string | null;
  slug: string;
  name: string;
  description: string | null;
  is_system: boolean;
  priority: number;
  color: string | null;
  permission_slugs: string[];
  deny_slugs: string[];
  member_count: number;
  created_at: string;
  updated_at: string;
}

/** Create/update payload for a role. All fields optional on PATCH. */
export interface RoleWritePayload {
  slug: string;
  name: string;
  description?: string | null;
  priority?: number;
  color?: string | null;
  permission_slugs?: string[];
  deny_slugs?: string[];
}

export interface RoleReorderItem {
  role_id: string;
  priority: number;
}

/** One role-scoped audit row (GET /orgs/{id}/roles/{id}/audit). */
export interface RoleAuditEvent {
  id: string;
  action: string;
  actor_user_id: string;
  actor_email: string | null;
  actor_name: string | null;
  target_type: string | null;
  target_id: string | null;
  summary: string | null;
  occurred_at: string;
}

/** A member of the active org (GET /orgs/{id}/members). */
export interface OrgMember {
  id: string;
  user_id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  role_slugs: string[];
  last_active_brand_id: string | null;
  joined_at: string;
  status: string;
  last_active_at: string | null;
  is_owner: boolean;
}

/** One row in the org-wide audit log (GET /orgs/{id}/audit). */
export interface AuditEvent {
  id: string;
  action: string;
  actor_user_id: string;
  actor_email: string | null;
  actor_name: string | null;
  target_type: string | null;
  target_id: string | null;
  brand_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  occurred_at: string;
}

export interface AuditEventList {
  items: AuditEvent[];
  /** Distinct action slugs present in this org's log — for the filter UI. */
  actions: string[];
}

/** Filters for the org audit log. All optional. */
export interface AuditQuery {
  action?: string[];
  actor_user_id?: string;
  target_type?: string;
  since?: string;
  until?: string;
  search?: string;
  limit?: number;
}

// ---- LinkedIn Poster Studio ----
export type PosterLayout = "editorial" | "split" | "banner";
export type PosterPalette = "warm" | "cool" | "bold" | "mono";
export type PosterImageStyle = "photo" | "illustration";
export interface LinkedInCopy {
  layout: PosterLayout;
  palette: PosterPalette;
  image_style: PosterImageStyle;
  image_concept: string;
  eyebrow: string;
  headline_lead: string;
  headline_accent: string;
  subheadline: string;
  cta: string;
  bullets: string[];
  post_body: string;
  hashtags: string[];
}
export interface LinkedInComposeResult {
  image_url: string;
  width: number;
  height: number;
  post_body: string;
  hashtags: string[];
  fields: LinkedInCopy;
  rendered_id: string | null;
  used_ai_image: boolean;
}
