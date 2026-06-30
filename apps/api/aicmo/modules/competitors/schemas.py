"""Pydantic schemas for competitor intelligence.

`CompetitorAnalysisResponse` is BOTH the LLM structured-output schema and
the API response model — one definition, no drift. Every recommendation
carries the Constitution's four required fields (recommendation, reason,
confidence, expected_result); the model refuses to ship without them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompetitorInsight(BaseModel):
    """One competitor, analysed. No fabricated metrics — every field is
    qualitative, plain-language reasoning the founder can act on."""

    name: str = Field(description="The competitor's name as the founder listed it.")
    positioning: str = Field(
        description=(
            "One plain-language sentence: how this competitor appears to "
            "present itself to customers."
        ),
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="What this competitor appears to do well (1-4 bullets).",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description=(
            "Weaknesses or openings the founder can exploit (1-4 bullets). "
            "No invented facts — reason from positioning + audience fit."
        ),
    )
    content_angles: list[str] = Field(
        default_factory=list,
        description="Content themes or formats this competitor tends to lean on.",
    )
    your_move: str = Field(
        description=(
            "The single most effective way for the founder to differentiate "
            "or win against this competitor. Imperative voice, no jargon."
        ),
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description=(
            "How confident this read is given only the competitor's name + "
            "the founder's context. Reserve 80+ for well-known players with "
            "a clean industry fit; 40-60 when reasoning from the name alone."
        ),
    )


class CompetitorAnalysisResponse(BaseModel):
    """The full competitor-intelligence payload. Doubles as the LLM
    response schema and the API response model."""

    market_summary: str = Field(
        description=(
            "2-3 plain sentences on the competitive landscape this founder "
            "operates in — what customers are choosing between."
        ),
    )
    competitors: list[CompetitorInsight] = Field(
        description="One insight per competitor the founder listed.",
    )

    # ---- Constitution AI recommendation contract (all four required) ----
    recommendation: str = Field(
        description="The single highest-leverage competitive move to make next.",
    )
    reason: str = Field(
        max_length=200,
        description="One line: what this recommendation draws on.",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in the recommendation (0-100).",
    )
    expected_result: str = Field(
        description=(
            "Plain-language outcome if the founder acts. Always a range, "
            "never a single magic number."
        ),
    )
