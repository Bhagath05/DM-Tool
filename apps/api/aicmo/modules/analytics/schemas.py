from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


# ---------- overview ----------


class OverviewKpis(BaseModel):
    """Top-of-page KPIs. Everything a lead-gen operator wants to see in <5s."""

    total_leads: int
    leads_7d: int
    leads_30d: int
    hot_leads: int
    landing_pages_published: int
    total_views: int
    total_submissions: int
    conversion_rate: float  # submissions / views, 0.0-1.0
    top_landing_page_title: str | None
    top_landing_page_slug: str | None
    top_landing_page_submissions: int


# ---------- timeline ----------


class TimelinePoint(BaseModel):
    day: date
    leads: int


class TimelineResponse(BaseModel):
    days: list[TimelinePoint]
    total: int
    window_days: int


# ---------- sources ----------


class SourceRow(BaseModel):
    source_asset_type: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    leads: int
    hot_leads: int


class SourcesResponse(BaseModel):
    items: list[SourceRow]


# ---------- landing-page performance ----------


class LandingPagePerformanceRow(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    status: str
    view_count: int
    submission_count: int
    conversion_rate: float
    hot_leads: int


class LandingPagePerformanceResponse(BaseModel):
    items: list[LandingPagePerformanceRow]


# ---------- status distribution (for the inbox triage donut) ----------


class StatusDistribution(BaseModel):
    new: int
    hot: int
    warm: int
    cold: int
    archived: int


# ---------- top-converting assets ----------


class TopAssetRow(BaseModel):
    """One asset (content / ad / visual / campaign) that captured leads.

    Polymorphic — `source_asset_type` tells you which table to deep-link to.
    Fields are flattened so the frontend doesn't need 4 different renderers.
    """

    source_asset_type: str  # "content" | "ad" | "visual" | "campaign"
    source_asset_id: uuid.UUID
    subtype: str  # content_type / ad_type / visual_type / campaign_type
    platform: str | None  # campaigns span multiple platforms — may be null
    goal: str
    leads: int
    hot_leads: int
    created_at: datetime


class TopAssetsResponse(BaseModel):
    items: list[TopAssetRow]
