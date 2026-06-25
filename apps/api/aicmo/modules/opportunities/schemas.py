"""Opportunity Center schemas — Phase 6.

The Opportunity Center is the AI growth advisor's recommendation layer:
it turns inbox + analytics + trends + profile signals into concrete
content and ad opportunities the founder can act on in ONE click.

Every Opportunity carries the full Constitution contract (what's
happening, why it matters, recommended action, expected result,
confidence, reason). Pydantic refuses to ship an Opportunity that's
missing any of these — the contract is enforced at the API boundary,
not just by the UI.

`generator` is the deep-link spec: it tells the frontend which generator
to open (content vs ads) and how to pre-fill the form so a single click
becomes a single generated piece of content / ad.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrored from coach.schemas / business-metric.tsx. Keep in sync.
OpportunityImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]

# Two surfaces in Phase 6. Extensible — 'lead' + 'growth' come later.
OpportunityKind = Literal["content", "ad"]

# Content formats — superset of content.schemas.ContentType plus a few
# longer-form formats the user spec calls out explicitly. The frontend
# maps these to either /content (uses ContentType) or /ads (uses AdType)
# depending on `GeneratorHint.target`.
ContentFormat = Literal[
    "social_post",
    "reel",
    "carousel",
    "ad_copy",
    "blog_outline",
    "short_video_script",
]

# Ad formats — mirror ads.schemas.AdType so the deep-link pre-fills the
# ads studio with a known-good value.
AdFormat = Literal[
    "meta",
    "google_search",
    "instagram_promo",
    "linkedin",
]

# Ad objective — mirror ads.schemas.AdObjective.
AdObjective = Literal[
    "awareness",
    "traffic",
    "engagement",
    "leads",
    "app_installs",
    "conversions",
    "sales",
]


class GeneratorHint(BaseModel):
    """How the frontend should deep-link this opportunity into a generator.

    `target` switches which generator (and which query-param schema):
        'content' → /content?type=<format>&platform=<platform>&goal=<goal>
        'ad'      → /ads?ad_type=<format>&objective=<objective>&goal=<goal>

    The pre-fill is intentionally minimal — we don't try to one-shot a
    full prompt, because the founder still wants to see + tweak the
    generator's options before generating. The pre-fill removes the
    "which dropdown do I pick?" friction.
    """

    target: Literal["content", "ad", "visual"]
    # When target='content' this is a ContentFormat. When 'ad' this is an AdFormat.
    format: str = Field(min_length=2, max_length=64)
    platform: str | None = Field(default=None, max_length=64)
    goal: str = Field(min_length=2, max_length=120)
    # Ad-only — None on content opportunities.
    objective: AdObjective | None = None


class OpportunityHeroRecommendation(BaseModel):
    """The "what should I do FIRST today" card at the top of /opportunities.

    Field names match the frontend's `<AiRecommendation>` props. Straight
    pass-through, no translator needed. REQUIRED across the board.
    """

    what_is_happening: str = Field(
        min_length=10,
        description="ONE-line plain-English description of the founder's RIGHT-NOW situation across content + ads. Reference real signals. Example: 'You have a clear winning channel (Instagram) and 3 fresh leads, but no content shipped this week.'",
    )
    impact_category: OpportunityImpactCategory = Field(
        description="Pick the category that best matches the outcome. Usually 'revenue' or 'lead' for the hero — opportunities exist to drive more of those."
    )
    recommendation: str = Field(
        min_length=10,
        description="The SINGLE most important opportunity to act on TODAY. Verb-led. Example: 'Ship one Instagram reel riding the \"specialty coffee guides\" trend before Friday.'",
    )
    expected_result: str = Field(
        min_length=5,
        description="What success looks like, ranged. Example: 'Likely 5-12 new visitors and 1-2 leads over the following 7 days.'",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="0-100 confidence. 80+ = strong signal stack. 60-79 = reasonable. 40-59 = thin sample, frame as worth trying. Don't default high.",
    )
    reason: str = Field(
        min_length=5,
        max_length=200,
        description="ONE-line citation of WHAT DATA drove this. Example: 'Based on Instagram producing 60% of leads and trends showing rising interest in specialty guides.'",
    )
    task_status: Literal[
        "not_started", "in_progress", "completed", "skipped"
    ] | None = None


class Opportunity(BaseModel):
    """One ranked opportunity card.

    `id` is deterministic — a uuid5 derived from kind + format + action
    so the same opportunity coming back from a refresh keeps its ID.
    Lets us add 'dismiss' / 'saved' state later without churning IDs.
    """

    id: uuid.UUID
    kind: OpportunityKind

    # The headline a founder sees BEFORE the body. Short, scannable.
    # Example: "People are asking about pricing".
    headline: str = Field(
        min_length=4,
        max_length=120,
        description="Scannable headline — 4-10 words. Names the OPPORTUNITY, not the action. Example: 'People are asking about pricing'.",
    )

    # The Constitution 4-question contract — every field REQUIRED.
    what_is_happening: str = Field(
        min_length=10,
        description="Plain-English statement of the signal. Example: 'Pricing-related questions appeared 3x in this week's lead messages.'",
    )
    why_it_matters: str = Field(
        min_length=10,
        description="ONE sentence on the business impact if the founder DOESN'T act. Example: 'Pricing confusion is the #1 reason a hot lead goes cold.'",
    )
    recommended_action: str = Field(
        min_length=8,
        description="Verb-led, specific. Example: 'Create a 60-second pricing comparison video for Instagram.'",
    )
    expected_result: str = Field(
        min_length=5,
        description="Ranged when uncertain. Example: 'Could surface 10-20 qualified leads over the following month.'",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="0-100. Calibrate honestly. Strong signal stack (trend + lead messages + matching channel) = 75+. Thin signal = 40-60.",
    )
    reason: str = Field(
        min_length=5,
        max_length=200,
        description="ONE-line citation. Example: 'Pricing search volume +22%, 3 lead messages mention price, Instagram is your winning channel.'",
    )
    impact_category: OpportunityImpactCategory = Field(
        description="Pick the closest. Most content/ad opportunities are 'lead' or 'revenue'."
    )

    # Professional Mode surfaces — Simple Mode HIDES these.
    evidence: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="Up to 6 plain-English supporting signals shown ONLY in Professional Mode. Example: 'Top channel: Instagram (4 of 6 recent leads).'",
    )

    # Deep-link spec — drives the "Generate this" button on the card.
    generator: GeneratorHint

    # Advisor memory — persisted task status (Phase 1).
    task_status: Literal[
        "not_started", "in_progress", "completed", "skipped"
    ] | None = None


class _NarrativeOpportunity(BaseModel):
    """LLM-side opportunity. Same Constitution contract; the orchestrator
    derives the deterministic `id` server-side after the LLM returns."""

    kind: OpportunityKind
    headline: str = Field(min_length=4, max_length=120)
    what_is_happening: str = Field(min_length=10)
    why_it_matters: str = Field(min_length=10)
    recommended_action: str = Field(min_length=8)
    expected_result: str = Field(min_length=5)
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=5, max_length=200)
    impact_category: OpportunityImpactCategory
    evidence: list[str] = Field(default_factory=list, max_length=6)
    generator: GeneratorHint


class _OpportunityCenterNarrative(BaseModel):
    """Private — what the LLM produces. The orchestrator wraps this into
    the public `OpportunityCenterReport` with derived ids + signals."""

    headline: str = Field(
        min_length=5,
        description="ONE sentence framing the opportunity landscape for this founder. Reference real signals.",
    )
    hero_recommendation: OpportunityHeroRecommendation
    # Each list capped to 5 — the founder should NEVER face 20 cards.
    content_opportunities: list[_NarrativeOpportunity] = Field(
        default_factory=list, max_length=5
    )
    ad_opportunities: list[_NarrativeOpportunity] = Field(
        default_factory=list, max_length=5
    )
    skip_for_now: list[str] = Field(default_factory=list, max_length=3)


class OpportunityCenterReport(BaseModel):
    """Final response payload returned by GET /api/v1/opportunities."""

    model_config = ConfigDict(from_attributes=True)

    headline: str
    hero_recommendation: OpportunityHeroRecommendation
    content_opportunities: list[Opportunity]
    ad_opportunities: list[Opportunity]
    skip_for_now: list[str]
    # Transparency — the deterministic signals the report was built from.
    # Surfaced in a "How this was built" disclosure on the frontend.
    signals_used: list[str] = Field(default_factory=list)
    # ISO timestamp for client-side cache decisions.
    generated_at: str
    # Advisor readiness — when false, opportunities list is intentionally empty.
    advisor_ready: bool = True
    advisor_setup_steps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------
#  Deterministic id derivation
# ---------------------------------------------------------------------

# A stable UUID namespace for opportunity ids. Hard-coded so a refresh
# generating the "same" opportunity returns the same id, which lets the
# frontend dedupe and (later) attach dismiss / save state.
_OPPORTUNITY_NAMESPACE = uuid.UUID("c1a4b1c0-6f6a-4d3b-9a8e-9f5e9c2a5d61")


def derive_opportunity_id(
    *,
    kind: OpportunityKind,
    generator: GeneratorHint,
    recommended_action: str,
) -> uuid.UUID:
    """Stable id from the action shape. Same recommendation across two
    refreshes → same id."""
    payload = "|".join(
        [
            kind,
            generator.target,
            generator.format,
            (generator.platform or "").lower(),
            (generator.objective or "").lower(),
            # Action is normalised (collapsed whitespace, lowercased) so
            # casing or padding differences don't churn ids.
            " ".join(recommended_action.lower().split()),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return uuid.uuid5(_OPPORTUNITY_NAMESPACE, digest)
