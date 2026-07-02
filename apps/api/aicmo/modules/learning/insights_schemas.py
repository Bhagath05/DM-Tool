"""Module 6 — Learning Engine schemas.

`LearningInsightDraft` / `SynthesisOutput` are the LLM's structured output.
`LearningInsightResponse` is the API/DB shape. Every insight carries the full
recommendation contract (recommendation + expected_result + confidence + the
observation as its reason) so nothing user-facing ships without it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The four reasoning modules a lesson can improve. Kept a closed set so the
# feedback layer can route each insight to the right prompt.
AffectedModule = Literal[
    "business_understanding", "strategy", "planner", "decision"
]

# What kind of lesson. Mirrors the spec's "learn: best posting times, channels,
# campaign types, creatives, formats, audiences, budget, seasonal, conversion,
# winning/failed strategies".
InsightCategory = Literal[
    "posting_time",
    "channel",
    "campaign_type",
    "creative",
    "content_format",
    "audience_segment",
    "budget",
    "seasonal",
    "conversion",
    "winning_strategy",
    "failed_strategy",
]

Direction = Literal["positive", "negative", "neutral"]


class LearningInsightDraft(BaseModel):
    """One lesson the LLM proposes from the real evidence. No row is persisted
    unless it clears the trust floor (confidence + at least one evidence item)."""

    category: InsightCategory
    observation: str = Field(
        description="The lesson in one plain line, grounded in the evidence (e.g. 'Instagram brings cheaper leads than email for this brand')."
    )
    evidence: list[str] = Field(
        description="The specific real signals this stands on — quote the numbers/facts from the snapshot. Must be non-empty; if you cannot cite real evidence, do not emit the insight."
    )
    recommendation: str = Field(
        description="The forward-looking action this lesson implies (a human decides/executes — nothing auto-runs)."
    )
    expected_result: str = Field(
        description="Plain-language outcome if acted on — always a range, never a single fabricated number."
    )
    confidence: int = Field(
        ge=0, le=100, description="Calibrate to evidence strength: strong recent data high; one data point low."
    )
    direction: Direction = "positive"
    affected_modules: list[AffectedModule] = Field(
        default_factory=list,
        description="Which reasoning modules this should improve. Choose only where it genuinely applies.",
    )
    lifespan_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="For time-bound lessons (seasonal, short-lived wins) how many days it stays valid; null for stable lessons that don't expire on their own.",
    )


class SynthesisOutput(BaseModel):
    """The engine's full output for one run."""

    insights: list[LearningInsightDraft] = Field(
        default_factory=list,
        description="Evidence-backed lessons. Fewer, well-grounded lessons beat many weak ones. Empty is correct when history is too thin.",
    )
    data_sufficiency: str = Field(
        description="Honest one-paragraph note on how much real history was available and what's missing to learn more."
    )


class LearningInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    category: str
    observation: str
    evidence: list[str]
    recommendation: str
    expected_result: str
    confidence: int
    direction: str
    affected_modules: list[str]
    learned_at: datetime
    expires_at: datetime | None
    source: str
    status: str


class LearningInsightList(BaseModel):
    items: list[LearningInsightResponse]


class SynthesisRunResult(BaseModel):
    """Returned by POST /learning/synthesize — counts + honest sufficiency note.

    `note` carries the literal "Not enough historical evidence." when the
    workspace has too little real history to learn from."""

    insights_created: int
    insights_superseded: int
    insights_expired: int
    signals_considered: int
    data_sufficiency: str
    note: str | None = None
