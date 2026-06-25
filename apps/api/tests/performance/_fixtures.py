"""Shared rollup fixtures for the 9.1.5 intelligence tests.

Kept here so each layer's test file can build cubes consistently
without re-deriving the same dataclass kwargs."""

from __future__ import annotations

from datetime import date

from aicmo.modules.performance.schemas import CreativeRollup


def rollup(
    *,
    creative_ref: str,
    conversions: int = 10,
    spend: int = 1_000,
    impressions: int = 5_000,
    clicks: int = 100,
    conversion_value: int = 0,
    audience: str | None = None,
    concept_family: str | None = None,
    emotion: str | None = None,
    funnel_stage: str | None = None,
    offer_type: str | None = None,
    currency: str = "INR",
    sample_state: str = "sufficient",
    platform: str = "meta",
) -> CreativeRollup:
    return CreativeRollup(
        creative_ref=creative_ref,
        platform=platform,
        matched_asset_type=None,
        matched_asset_id=None,
        concept_family=concept_family,
        emotion=emotion,
        audience=audience,
        funnel_stage=funnel_stage,  # type: ignore[arg-type]
        business_goal=None,
        offer_type=offer_type,  # type: ignore[arg-type]
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        spend_micros=spend * 1_000_000,
        conversion_value_micros=conversion_value * 1_000_000,
        currency=currency,
        first_seen=date(2026, 5, 1),
        last_seen=date(2026, 5, 31),
        sample_state=sample_state,  # type: ignore[arg-type]
    )
