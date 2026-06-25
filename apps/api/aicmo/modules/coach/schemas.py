"""Reality Engine schemas.

Two Pydantic surfaces:
- `_RealityNarrative` — what the LLM produces. Private; not exposed to clients.
- `RealityCheck` — the full advisory result. Combines the deterministic
  heuristic score with the LLM narrative.

Tone enforcement (no buzzwords, no harshness) lives in the prompt, not in
the schema — keep the schema mechanically simple so Gemini's structured
output doesn't run into "too many states" constraint errors.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FeasibilityLabel = Literal[
    "Highly achievable",
    "Achievable with strong execution",
    "Aggressive but possible",
    "High-risk target",
    "Unrealistic under current constraints",
]

RiskKind = Literal[
    "timeline",
    "budget",
    "saturation",
    "execution",
    "acquisition",
    "stage",
    "channel",
]

RiskSeverity = Literal["info", "watch", "blocker"]


class RealityMilestone(BaseModel):
    """One realistic checkpoint along the path to the user's goal."""

    timeframe: str = Field(
        description="Time horizon, e.g. 'Month 1', 'Weeks 1-2', 'Quarter 2'."
    )
    target: str = Field(
        description="The concrete outcome to aim for in this window."
    )
    why_realistic: str = Field(
        description="One short sentence on why this is achievable for this business RIGHT NOW."
    )


class PhasedStep(BaseModel):
    """A focus area in a sequenced plan — what comes before what."""

    phase: str = Field(
        description="Position label, e.g. 'First', 'Next', 'Then', or a timeframe."
    )
    focus: str = Field(
        description="What to do or build in this phase. Concrete, not vague."
    )
    rationale: str = Field(
        description="Why this comes before the next phase. Tie to budget / traction / stage."
    )


class RiskFlag(BaseModel):
    """A specific constraint the founder should know about."""

    kind: RiskKind = Field(
        description="Category — timeline / budget / saturation / execution / acquisition / stage / channel."
    )
    note: str = Field(
        description="One-sentence explanation. Calm, specific, never harsh."
    )
    severity: RiskSeverity = Field(
        description="info (worth knowing) | watch (could become a blocker) | blocker (must address first)."
    )


class _RealityNarrative(BaseModel):
    """Private — what the LLM is asked to produce. Combined with the
    deterministic score to form the final RealityCheck."""

    headline: str = Field(
        description="One or two sentences that ACKNOWLEDGE the founder's ambition and set the tone. Never starts with 'No' or 'You can't'."
    )
    realistic_milestones: list[RealityMilestone] = Field(
        description="3 sequential milestones. Calibrated to budget + stage."
    )
    phased_growth_path: list[PhasedStep] = Field(
        description="3-4 focus areas in execution order. Each rationale ties back to the constraint that made it come first."
    )
    risk_flags: list[RiskFlag] = Field(
        description="2-5 specific constraints. Use 'blocker' sparingly — only when the goal CANNOT be reached without addressing it."
    )
    strategic_notes: list[str] = Field(
        description="2-4 observations a real strategist would mention. Tradeoffs, industry realities, things the founder may not have considered. Never generic."
    )


class RealityCheck(BaseModel):
    """Final advisory payload returned by the Reality Engine."""

    model_config = ConfigDict(from_attributes=True)

    feasibility_score: int = Field(
        ge=0,
        le=100,
        description="0 (fantasy) → 100 (already done). Computed deterministically from profile + goal signals; the LLM does not move this number.",
    )
    feasibility_label: FeasibilityLabel
    headline: str
    realistic_milestones: list[RealityMilestone]
    phased_growth_path: list[PhasedStep]
    risk_flags: list[RiskFlag]
    strategic_notes: list[str]
    # Why the score landed where it did. Lets the frontend tooltip-explain
    # without needing another LLM call.
    score_signals: list[str] = Field(
        default_factory=list,
        description="Plain-English reasons that fed the heuristic score.",
    )


# ---------- request shape ----------


class RealityCheckRequest(BaseModel):
    goal_text: str = Field(min_length=2, max_length=500)
    timeline_hint: str | None = Field(
        default=None,
        max_length=64,
        description="Optional explicit timeframe, e.g. '30 days', '3 months'. If omitted, we parse the goal_text.",
    )


# ===================================================================
# Phase 2.4 — Weekly Action Rollup
# ===================================================================

ActionTarget = Literal[
    "content",
    "ads",
    "visuals",
    "campaigns",
    "lead_pages",
    "trends",
    "analytics",
    "profile",
]

ActionPriority = Literal["focus", "important", "stretch"]

# Constitution: every recommendation must declare which of these 5 outcome
# categories it drives. Keep in sync with the BusinessMetric/AiRecommendation
# components on the frontend.
ImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]


class WeeklyAction(BaseModel):
    """One concrete task the founder can do this week.

    Fully Constitution-compliant: every field below is REQUIRED. The LLM
    that produces these is told to fill every one. If any is missing,
    Pydantic validation fails and the deterministic fallback (which also
    fills every field) takes over — the user-facing contract never
    breaks.
    """

    # NOTE: deliberately NOT named `title` — Gemini's structured-output
    # mode treats `title` as a JSON-Schema meta-keyword and silently
    # drops it as a field. `action_title` sidesteps the collision.
    action_title: str = Field(
        min_length=3,
        description="The recommendation itself — short verb-led imperative. Example: 'Publish your first lead page'.",
    )
    why: str = Field(
        min_length=10,
        description="ONE sentence on why this matters this week — tie to a real signal (traction band, trend, gap, channel rec).",
    )
    business_impact: str = Field(
        min_length=5,
        description="Plain-language business impact line — what the founder gets from doing this. Example: 'More leads this week' / 'Lower cost per lead'.",
    )
    impact_category: ImpactCategory = Field(
        description="Which of the 5 outcome categories this action drives. Drives icon + accent colour in the UI."
    )
    expected_result: str = Field(
        min_length=5,
        description="What success looks like, RANGED when uncertain. Example: 'Likely 8-15 additional leads this week'.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="0-100 confidence in this recommendation. 80+ = High (ship as CTA). 60-79 = Medium. 40-59 = Low (frame as experiment). <40 = Speculative (don't ship as instruction).",
    )
    reason: str = Field(
        min_length=5,
        max_length=200,
        description="ONE-line explanation of WHAT DATA drove this recommendation. Example: 'Based on the lead-page gap — no captured leads possible without one'.",
    )
    cta_label: str = Field(
        min_length=2,
        description="Button text, ≤4 words. Example: 'Build a page', 'Draft a reel', 'Plan a campaign'.",
    )
    cta_target: ActionTarget = Field(
        description="Which studio / surface this action deep-links to."
    )
    priority: ActionPriority = Field(
        description="focus = the single most important thing | important = high-value | stretch = bonus if time allows."
    )
    estimated_time: str = Field(
        description="Rough time commitment, e.g. '15 min', '1 hour', 'half a day'. Be honest."
    )


class _WeeklyPlanNarrative(BaseModel):
    """Private — what the LLM produces. Combined with composer signals to
    form the final WeeklyPlan."""

    headline: str = Field(
        description="One sentence that frames the week — calm, specific, never generic. Example: 'You're pre-traction with a published page — this week is about driving the first trickle of visitors to it.'"
    )
    week_focus: str = Field(
        description="The SINGLE most important outcome to aim for this week. One sentence. Avoid lists."
    )
    actions: list[WeeklyAction] = Field(
        description="3-5 actions in priority order. Exactly ONE is priority='focus'."
    )
    skip_this_week: list[str] = Field(
        description="0-3 things explicitly NOT worth doing this week. Helps the founder say no to noise."
    )


class WeeklyPlan(BaseModel):
    """Final advisory payload returned by the Weekly Action Rollup."""

    model_config = ConfigDict(from_attributes=True)

    headline: str
    week_focus: str
    actions: list[WeeklyAction]
    skip_this_week: list[str]
    # Transparency — which signals the plan was built from. The frontend
    # tucks these into a "How this was assembled" expander.
    signals_used: list[str] = Field(default_factory=list)
    # ISO timestamp for client-side cache decisions.
    generated_at: str


# ===================================================================
# Phase 2.5 — AI Analytics Explanation Layer
# ===================================================================


class AnalyticsSummary(BaseModel):
    """One Gemini call worth of analytics narration.

    The hero card on the analytics dashboard reads `headline` +
    `what_to_do_next`. The five per-section blurbs are passed down as
    optional props to the existing cards — so the founder reads each
    chart with a one-sentence English explanation right above it.
    """

    model_config = ConfigDict(from_attributes=True)

    headline: str = Field(
        description="ONE sentence that captures the story of the week — specific to this founder's actual numbers."
    )
    what_to_do_next: str = Field(
        description="ONE sentence on the single highest-leverage next action based on what the data is saying."
    )
    overview_blurb: str = Field(
        description="1-2 sentences narrating the top-of-page KPIs (total leads / weekly leads / hot leads / conversion). Plain English, no jargon."
    )
    timeline_blurb: str = Field(
        description="1-2 sentences on whether leads are trending up, flat, or down — and what that means."
    )
    sources_blurb: str = Field(
        description="1-2 sentences on which channels brought customers in, and which channels are missing."
    )
    landing_pages_blurb: str = Field(
        description="1-2 sentences on which pages are converting and which are getting traffic but not signups."
    )
    top_assets_blurb: str = Field(
        description="1-2 sentences on which generated piece drove the most leads, and the pattern the founder should clone."
    )
    # Transparency: same provenance pattern as WeeklyPlan.
    signals_used: list[str] = Field(default_factory=list)
    generated_at: str
