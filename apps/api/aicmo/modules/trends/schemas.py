from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- Raw collector output ----------


class GoogleTrendItem(BaseModel):
    keyword: str
    related_queries: list[str] = Field(default_factory=list)
    rising_queries: list[str] = Field(default_factory=list)


class RedditTrendItem(BaseModel):
    subreddit: str
    title: str
    score: int
    num_comments: int
    url: str


class RawTrends(BaseModel):
    google_trends: list[GoogleTrendItem] = Field(default_factory=list)
    reddit_posts: list[RedditTrendItem] = Field(default_factory=list)
    sources_attempted: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


# ---------- AI structured output ----------


class TrendingTopic(BaseModel):
    """A trend mapped onto the Constitution's advisory contract.

    Founder Experience Audit (Batch 3 / C6): each trend must answer the
    same four questions every other AI surface does — what's happening,
    what should I do, what should I expect, and why does the AI believe it.

    The four advisory fields (``recommended_action``, ``expected_result``,
    ``confidence``, ``reason``) are *optional* at the schema layer so old
    reports already persisted in Postgres still hydrate without raising.
    The prompt (see ``prompts.SYSTEM_PROMPT``) requires the LLM to
    populate all four for every new report — the frontend renders the
    full advisory card when they're present and falls back gracefully
    when they aren't.

    ``relevance_score`` is the legacy numeric score (1-100). It's kept
    optional purely so old DB rows still deserialize; the founder UI
    no longer renders it (we now show ``confidence`` as a tier instead).
    """

    topic: str = Field(description="Short noun-phrase for the trend.")
    why_it_matters: str = Field(
        description="One sentence on why this is relevant to THIS business specifically."
    )
    suggested_angles: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Distinct content angles a marketer could use for this trend.",
    )
    relevance_score: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Legacy: AI confidence the trend fits the business (1-100).",
    )

    # Constitution contract — populated for every new trend report.
    recommended_action: str | None = Field(
        default=None,
        min_length=10,
        max_length=300,
        description=(
            "The single concrete thing the founder should do this week to "
            "ride this trend. Imperative sentence, no jargon."
        ),
    )
    expected_result: str | None = Field(
        default=None,
        min_length=10,
        max_length=300,
        description=(
            "Plain-language outcome to expect within 7-14 days "
            "(e.g. '5-12 extra visitors, 1-2 new leads')."
        ),
    )
    confidence: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description=(
            "AI confidence the action will deliver the expected result "
            "(1-100). Calibrated against the strength of the trend signal "
            "and how well it matches the business."
        ),
    )
    reason: str | None = Field(
        default=None,
        min_length=10,
        max_length=300,
        description=(
            "One sentence citing the specific trend signal or business "
            "fit driving the confidence above."
        ),
    )


class ContentIdea(BaseModel):
    platform: str = Field(description="One of the user's preferred platforms.")
    format: str = Field(
        description="Concrete format: reel, carousel, short, tweet, thread, email, blog…"
    )
    hook: str = Field(description="First-second/first-line attention hook.")
    description: str = Field(description="2-3 sentences on what the piece covers.")


class HashtagCluster(BaseModel):
    theme: str
    hashtags: list[str] = Field(min_length=3, max_length=12)


class TrendAnalysis(BaseModel):
    summary: str = Field(
        description="One short paragraph framing the trend landscape for this business."
    )
    # Floors deliberately permissive — when a signal source is unavailable
    # (e.g. Reddit down) the LLM may legitimately only find 1-2 strong
    # topics. Better to surface a sparse report than fail the whole
    # request. Max stays tight so the UI doesn't drown.
    trending_topics: list[TrendingTopic] = Field(min_length=1, max_length=8)
    content_ideas: list[ContentIdea] = Field(min_length=1, max_length=8)
    hashtag_clusters: list[HashtagCluster] = Field(min_length=1, max_length=5)
    marketing_angles: list[str] = Field(
        min_length=1,
        max_length=6,
        description="High-level positioning angles to lean into right now.",
    )


# ---------- API responses ----------


class TrendReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    status: Literal["pending", "completed", "failed"]
    raw_trends: RawTrends | None
    analysis: TrendAnalysis | None
    analysis_error: str | None
    created_at: datetime
    updated_at: datetime
