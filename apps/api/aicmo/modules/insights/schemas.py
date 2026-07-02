"""Module 7 — Insights Feed schemas (the normalised, unified insight shape)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low"]
Urgency = Literal["now", "this_week", "this_month", "monitor"]
# Reuses the Constitution's 5-category business-impact taxonomy.
ImpactCategory = Literal["revenue", "lead", "customer", "time", "cost"]


class FeedItem(BaseModel):
    """One insight in the unified feed, normalised from whatever module produced
    it. Carries the recommendation contract (recommendation + expected_result +
    confidence) plus feed metadata (why it surfaced, where it came from)."""

    id: str = Field(description="Stable dedupe key (source + category + normalised title).")
    source_module: str = Field(description="Canonical id of the producing module (e.g. 'learning').")
    source_label: str = Field(description="Human label, e.g. 'Learning Engine'.")
    link: str = Field(description="Deep link back to the originating module's surface.")

    category: str = Field(description="Normalised category for grouping/filtering.")
    title: str
    detail: str = Field(description="What happened / the observation, in plain language.")
    why_surfaced: str = Field(description="Why this insight appears in the feed right now.")

    recommendation: str | None = None
    expected_result: str | None = None
    evidence: list[str] = Field(default_factory=list)

    confidence: int | None = Field(default=None, ge=0, le=100)
    severity: Severity = "medium"
    urgency: Urgency | None = None
    impact_category: ImpactCategory | None = None
    business_objective: str | None = None
    channels: list[str] = Field(default_factory=list)

    priority_score: float = Field(description="0-1 composite ranking (severity·urgency·confidence·impact).")
    group_key: str = Field(description="Key items are grouped by (category).")
    related_ids: list[str] = Field(
        default_factory=list,
        description="Ids of near-duplicate items merged into this one.",
    )


class FeedGroup(BaseModel):
    """Related items collected under one heading."""

    key: str
    label: str
    top_severity: Severity
    item_ids: list[str]


class SourceStatus(BaseModel):
    """Per-source contribution — transparency about what fed the feed."""

    module: str
    label: str
    contributed: int
    ok: bool = True
    note: str | None = None


class LiveSurface(BaseModel):
    """A generative module we deliberately did NOT re-run (no new intelligence).
    Surfaced as a link the user can open to generate on demand."""

    module: str
    label: str
    description: str
    link: str


class InsightFeedResponse(BaseModel):
    items: list[FeedItem]
    groups: list[FeedGroup]
    total: int
    sources: list[SourceStatus]
    live_surfaces: list[LiveSurface]
    filters_applied: dict[str, str | None]
    generated_at: str
    note: str | None = Field(
        default=None,
        description="Set to an honest message (e.g. 'Not enough...') when nothing surfaced.",
    )
