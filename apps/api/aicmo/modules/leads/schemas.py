from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

LeadStatus = Literal["new", "hot", "warm", "cold", "archived"]
LEAD_STATUSES: tuple[LeadStatus, ...] = ("new", "hot", "warm", "cold", "archived")

SourceAssetType = Literal[
    "content", "ad", "visual", "campaign", "direct", "import"
]


# ---------- public capture (no auth) ----------


class LeadCapturePayload(BaseModel):
    """What the public lead form POSTs.

    Slug isn't here — it's in the URL path. landing_page_id resolves
    server-side from the slug to avoid clients spoofing attribution.
    """

    email: EmailStr
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    company: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=2000)
    extra_data: dict[str, Any] = Field(default_factory=dict)

    # Attribution from URL query params (passed through the form as hidden fields)
    source_asset_type: SourceAssetType | None = None
    source_asset_id: str | None = Field(default=None, max_length=64)
    utm_source: str | None = Field(default=None, max_length=128)
    utm_medium: str | None = Field(default=None, max_length=128)
    utm_campaign: str | None = Field(default=None, max_length=128)
    utm_term: str | None = Field(default=None, max_length=128)
    utm_content: str | None = Field(default=None, max_length=128)

    # Captcha + browser metadata
    turnstile_token: str | None = Field(default=None, max_length=2048)
    referrer: str | None = Field(default=None, max_length=512)


class LeadCaptureResponse(BaseModel):
    """Minimal response — never expose internal IDs to anonymous traffic."""

    success: bool = True
    redirect_url: str | None = None


# ---------- auth'd inbox surfaces ----------


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)


class LeadCreatePayload(BaseModel):
    """Manual lead entry from the inbox."""

    email: EmailStr
    name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    company: str | None = Field(default=None, max_length=255)
    message: str | None = Field(default=None, max_length=2000)
    status: LeadStatus = "new"
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_asset_type: SourceAssetType = "direct"
    notes: str | None = Field(default=None, max_length=5000)


class LeadImportPayload(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


class LeadImportResult(BaseModel):
    inserted: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    business_profile_id: uuid.UUID
    email: str
    name: str | None
    phone: str | None
    company: str | None
    message: str | None
    extra_data: dict[str, Any]
    landing_page_id: uuid.UUID | None
    source_asset_type: str | None
    source_asset_id: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_term: str | None
    utm_content: str | None
    status: LeadStatus
    tags: list[str]
    notes: str | None
    referrer: str | None
    created_at: datetime
    updated_at: datetime


class LeadList(BaseModel):
    items: list[LeadResponse]
    total: int


# ===================================================================
# Phase 5 — Lead Intelligence
# ===================================================================
#
# Every recommendation must carry the full Constitution contract:
# `recommendation`, `expected_result`, `confidence`, `reason`.
# Refusing to render without those four lives in `<AiRecommendation>` on
# the frontend; the schema below refuses to ship without them by
# making every field REQUIRED.
#
# Two surfaces:
#   1. `LeadHeroRecommendation` — single "where to start" card at the
#      top of the inbox. Same shape the frontend's `<AiRecommendation>`
#      consumes — straight pass-through, no translator needed.
#   2. `LeadPriority` — one per ranked lead the founder should contact
#      first. Carries display fields lifted from the row (email/name/
#      company) so the frontend never has to cross-reference a separate
#      list to render a row.

# Mirrored from coach.schemas / business-metric.tsx. Keep in sync.
LeadImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]

# Priority bucket — drives row badge colour. "focus" is the SINGLE most
# important lead this week. The rest are tiered.
LeadPriorityBucket = Literal["focus", "hot", "warm", "cold"]

# Plain-language deal-size hint. Never a hardcoded currency amount —
# the LLM picks a band based on profile signals + lead richness.
EstimatedValueBand = Literal["high", "medium", "low", "unknown"]


class LeadHeroRecommendation(BaseModel):
    """The "where to start" card at the top of /leads.

    Field names match the frontend's `<AiRecommendation>` props (camelCase
    converted at the JSON boundary by FastAPI). REQUIRED across the board
    — the Constitution refuses to ship without these four.
    """

    what_is_happening: str = Field(
        min_length=10,
        description="ONE-line plain-English description of the inbox state RIGHT NOW. Reference real counts. Example: 'You have 8 new leads from the past week — 3 marked hot, but none contacted yet.'",
    )
    impact_category: LeadImpactCategory = Field(
        description="Pick the category that best matches the outcome of taking this action. Usually 'revenue' or 'customer' for the hero — leads exist to become customers."
    )
    recommendation: str = Field(
        min_length=10,
        description="The single most important action the founder should take TODAY based on the inbox. Verb-led. Example: 'Reply to the 3 leads who arrived in the last 48 hours, starting with the one who left a phone number.'",
    )
    expected_result: str = Field(
        min_length=5,
        description="What success looks like if they take this action. Ranged when uncertain. Example: 'Likely 1-2 quick conversations booked this week, with 1 of them turning into a paying customer.'",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="0-100 confidence. 80+ = strong signal. 60-79 = reasonable. 40-59 = thin sample, frame as worth trying. Don't default to 90 — be honest about thin data.",
    )
    reason: str = Field(
        min_length=5,
        max_length=200,
        description="ONE-line citation of WHAT DATA drove this recommendation. Example: 'Based on 3 new leads from the past 48 hours with no follow-up recorded yet.'",
    )


class LeadPriority(BaseModel):
    """One ranked lead the founder should act on now.

    `lead_id` is filled server-side after the LLM returns — the prompt
    uses 1-based indices to refer to leads, and the orchestrator resolves
    them back into UUIDs so the LLM cannot hallucinate IDs.
    """

    # Display fields — populated by the orchestrator from the actual row,
    # NOT trusted from the LLM. The LLM only references a lead by index.
    lead_id: uuid.UUID
    email: str
    name: str | None = None
    company: str | None = None

    # Ranking + bucket — `rank` is 1-based; rank=1 is always priority=focus.
    rank: int = Field(ge=1, description="1-based ordering, lowest = most urgent.")
    priority: LeadPriorityBucket = Field(
        description="Single 'focus' across the report — the one lead to contact first. The rest are hot/warm/cold."
    )

    # The Constitution contract — every field REQUIRED.
    why_now: str = Field(
        min_length=10,
        description="ONE sentence on why THIS lead is worth the founder's time RIGHT NOW. Tie to a real signal: recency, has phone, came from paid campaign, hot status, etc. NOT generic.",
    )
    recommended_action: str = Field(
        min_length=5,
        description="Verb-led action the founder should take. Example: 'Call within 24 hours', 'Send a personalised intro email referencing their company', 'Mark cold — emailed 3 times no reply'.",
    )
    expected_result: str = Field(
        min_length=5,
        description="What success looks like, ranged when uncertain. Example: 'A reply within 48h, with a 1-in-3 chance of converting to paying.'",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="0-100. Calibrate to signal strength. A new hot lead with a phone number from a paid campaign is high (75-90). An old cold lead from organic with no contact info is low (30-50).",
    )
    reason: str = Field(
        min_length=5,
        max_length=200,
        description="ONE-line citation of the row signals that drove this. Example: 'Hot status, came in 36h ago via paid Instagram campaign, left a phone number.'",
    )
    impact_category: LeadImpactCategory = Field(
        description="Usually 'revenue' (lead becomes paying) or 'customer' (relationship deepening). Pick the closest match."
    )
    estimated_value_band: EstimatedValueBand = Field(
        description="Plain-language deal-size hint based on profile + signals. NEVER a hardcoded amount — use the band. 'high' = top-tier deal for this business, 'low' = small but worth the touch, 'unknown' = not enough signal."
    )
    cta_label: str = Field(
        min_length=2,
        max_length=24,
        description="Button text the founder will click. ≤4 words. Example: 'Call now', 'Send email', 'Mark cold'.",
    )


class _LeadIntelligenceNarrative(BaseModel):
    """Private — what the LLM produces. Combined with composer signals to
    form the final `LeadIntelligenceReport`.

    The LLM references leads by 1-based `lead_index`. The orchestrator
    rebuilds full `LeadPriority` rows server-side so the LLM cannot
    fabricate UUIDs or invent leads that don't exist in this brand.
    """

    headline: str = Field(
        min_length=5,
        description="ONE sentence framing the inbox for this founder. Reference real counts. Example: 'You've got 8 leads to work through — start with the warmest ones from this week.'",
    )
    hero_recommendation: LeadHeroRecommendation = Field(
        description="The single most important action across the entire inbox."
    )
    priorities: list[_NarrativeLeadPriority] = Field(
        description="0-5 ranked leads the founder should act on. Empty list is valid when there are no leads to act on."
    )
    skip_for_now: list[str] = Field(
        default_factory=list,
        description="0-3 things the founder might be tempted to do but shouldn't right now. Example: 'Don't bulk-email — your inbox is small enough to write 1:1 replies.'",
    )


class _NarrativeLeadPriority(BaseModel):
    """LLM-side priority — references the lead by 1-based index. The
    orchestrator resolves `lead_index` → actual UUID + display fields and
    returns the full `LeadPriority` to the client."""

    lead_index: int = Field(
        ge=1,
        description="1-based index into the leads list provided in the prompt.",
    )
    priority: LeadPriorityBucket
    why_now: str = Field(min_length=10)
    recommended_action: str = Field(min_length=5)
    expected_result: str = Field(min_length=5)
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=5, max_length=200)
    impact_category: LeadImpactCategory
    estimated_value_band: EstimatedValueBand
    cta_label: str = Field(min_length=2, max_length=24)


class LeadCountsSnapshot(BaseModel):
    """Counts the inbox card surfaces above the hero so the founder sees
    'where they are' in one glance. Same numbers analytics shows; copied
    in so the inbox can render without a second roundtrip."""

    total: int = Field(ge=0)
    new_count: int = Field(ge=0)
    hot_count: int = Field(ge=0)
    last_7d: int = Field(ge=0)
    last_24h: int = Field(ge=0)


class LeadIntelligenceReport(BaseModel):
    """Final response payload returned by GET /api/v1/leads/intelligence."""

    model_config = ConfigDict(from_attributes=True)

    headline: str
    hero_recommendation: LeadHeroRecommendation
    priorities: list[LeadPriority]
    skip_for_now: list[str]
    counts: LeadCountsSnapshot
    # Transparency — the deterministic signals the report was built from.
    # Frontend tucks these into a "How this was built" expander.
    signals_used: list[str] = Field(default_factory=list)
    # ISO timestamp for client-side cache decisions.
    generated_at: str
