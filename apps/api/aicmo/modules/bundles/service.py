"""Bundle orchestrator. Post W1-12: brand-scoped.

Single public surface: `generate_bundle()`. Composes existing generators
in parallel via asyncio.gather. Each generation call gets its own DB
session because SQLAlchemy async sessions are NOT safe for concurrent use.
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.db.session import SessionLocal
from aicmo.modules.ads import service as ads_service
from aicmo.modules.ads.schemas import AdType, GenerateAdRequest
from aicmo.modules.ai_audit.service import (
    ACTION_GENERATE_BUNDLE,
    record_ai_generation,
)
from aicmo.modules.bundles.models import Bundle
from aicmo.modules.bundles.schemas import (
    BundlePiece,
    BundleResponse,
    GenerateBundleRequest,
)
from aicmo.modules.campaigns import service as campaigns_service
from aicmo.modules.campaigns.schemas import (
    CampaignType,
    GenerateCampaignRequest,
)
from aicmo.modules.content import service as content_service
from aicmo.modules.content.schemas import ContentType, GenerateRequest
from aicmo.modules.context.builder import build_generation_context
from aicmo.modules.learning.recorder import record_generation
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.visuals import service as visuals_service
from aicmo.modules.visuals.schemas import GenerateVisualRequest
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def generate_bundle(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    profile: BusinessProfileResponse,
    payload: GenerateBundleRequest,
    suggested_landing_page_id: uuid.UUID | None,
) -> BundleResponse:
    platforms = profile.preferred_platforms or []
    if not platforms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pick at least one preferred platform before building a bundle.",
        )

    landing_page_id = payload.landing_page_id or suggested_landing_page_id

    primary_platform = platforms[0]
    ad_type = _pick_ad_type(platforms)
    campaign_type = _campaign_type_for_objective(payload.objective)

    specs: list[tuple[str, str, str | None, str | None, _Spec]] = [
        (
            "campaign",
            f"{payload.duration_days}-day {campaign_type.replace('_', ' ')} plan",
            None,
            campaign_type,
            _campaign_spec(
                tenant=tenant,
                payload=payload,
                profile=profile,
                campaign_type=campaign_type,
                landing_page_id=landing_page_id,
            ),
        ),
        (
            "content",
            f"Social post for {primary_platform}",
            primary_platform,
            "social_post",
            _content_spec(
                tenant=tenant,
                payload=payload,
                content_type="social_post",
                platform=primary_platform,
                landing_page_id=landing_page_id,
            ),
        ),
        (
            "content",
            f"Reel for {primary_platform}",
            primary_platform,
            "reel",
            _content_spec(
                tenant=tenant,
                payload=payload,
                content_type="reel",
                platform=primary_platform,
                landing_page_id=landing_page_id,
            ),
        ),
        (
            "ad",
            f"{ad_type.replace('_', ' ').title()} ad",
            primary_platform,
            ad_type,
            _ad_spec(
                tenant=tenant,
                payload=payload,
                ad_type=ad_type,
                landing_page_id=landing_page_id,
            ),
        ),
        (
            "visual",
            f"Ad creative brief for {primary_platform}",
            primary_platform,
            "ad_creative",
            _visual_spec(
                tenant=tenant,
                payload=payload,
                platform=primary_platform,
                landing_page_id=landing_page_id,
            ),
        ),
    ]

    results = await asyncio.gather(
        *(spec() for _kind, _label, _plat, _sub, spec in specs),
        return_exceptions=True,
    )

    pieces: list[BundlePiece] = []
    for (kind, label, plat, subtype, _spec), outcome in zip(
        specs, results, strict=True
    ):
        if isinstance(outcome, Exception):
            log.warning(
                "bundles.piece_failed", kind=kind, error=str(outcome)
            )
            pieces.append(
                BundlePiece(
                    kind=kind,  # type: ignore[arg-type]
                    id=None,
                    label=label,
                    platform=plat,
                    subtype=subtype,
                    is_error=True,
                    error_message=_friendly_error(outcome),
                )
            )
            continue
        pieces.append(
            BundlePiece(
                kind=kind,  # type: ignore[arg-type]
                id=outcome.id,
                label=label,
                platform=plat,
                subtype=subtype,
            )
        )

    row = Bundle(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        business_profile_id=profile.id,
        landing_page_id=landing_page_id,
        theme=payload.theme,
        objective=payload.objective,
        duration_days=payload.duration_days,
        pieces=[p.model_dump(mode="json") for p in pieces],
    )
    session.add(row)
    bundle_context = None
    try:
        bundle_context = await build_generation_context(
            session, profile=profile, brand_id=tenant.brand_id
        )
    except Exception:
        bundle_context = None
    await record_generation(
        session,
        tenant=tenant,
        source_asset_type="bundle",
        source_asset_id=row.id,
        platform=primary_platform,
        goal=payload.objective,
        variable_choices={
            "theme": payload.theme,
            "objective": payload.objective,
            "duration_days": payload.duration_days,
            "primary_platform": primary_platform,
            "piece_count": len(pieces),
            "has_landing_page": landing_page_id is not None,
        },
        context=bundle_context,
    )
    # Phase S-AI-AUDIT — security/compliance audit row.
    await record_ai_generation(
        session,
        tenant=tenant,
        action_type=ACTION_GENERATE_BUNDLE,
        asset_id=row.id,
        model_used=get_settings().llm_default_model,
        metadata={
            "theme": payload.theme,
            "objective": payload.objective,
            "duration_days": payload.duration_days,
            "primary_platform": primary_platform,
            "piece_count": len(pieces),
            "has_landing_page": landing_page_id is not None,
        },
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


async def list_bundles(
    session: AsyncSession, *, tenant: TenantContext, limit: int = 20
) -> list[BundleResponse]:
    limit = max(1, min(limit, 100))
    stmt = (
        select(Bundle)
        .where(Bundle.brand_id == tenant.brand_id)
        .order_by(desc(Bundle.created_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


async def get_bundle(
    session: AsyncSession, *, tenant: TenantContext, bundle_id: uuid.UUID
) -> BundleResponse:
    stmt = select(Bundle).where(
        Bundle.id == bundle_id, Bundle.brand_id == tenant.brand_id
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bundle not found"
        )
    return _to_response(row)


# ---------------------------------------------------------------------
#  Per-asset spec builders — each returns an async callable.
# ---------------------------------------------------------------------


_Spec = "Any"


def _content_spec(
    *,
    tenant: TenantContext,
    payload: GenerateBundleRequest,
    content_type: ContentType,
    platform: str,
    landing_page_id: uuid.UUID | None,
):
    request = GenerateRequest(
        content_type=content_type,
        platform=platform,
        goal=payload.theme,
        landing_page_id=landing_page_id,
    )

    async def run():
        async with SessionLocal() as s:
            return await content_service.generate(
                s, tenant=tenant, payload=request
            )

    return run


def _ad_spec(
    *,
    tenant: TenantContext,
    payload: GenerateBundleRequest,
    ad_type: AdType,
    landing_page_id: uuid.UUID | None,
):
    request = GenerateAdRequest(
        ad_type=ad_type,
        objective=payload.objective,
        goal=payload.theme,
        landing_page_id=landing_page_id,
    )

    async def run():
        async with SessionLocal() as s:
            return await ads_service.generate(
                s, tenant=tenant, payload=request
            )

    return run


def _visual_spec(
    *,
    tenant: TenantContext,
    payload: GenerateBundleRequest,
    platform: str,
    landing_page_id: uuid.UUID | None,
):
    request = GenerateVisualRequest(
        visual_type="ad_creative",
        platform=platform,
        goal=payload.theme,
        landing_page_id=landing_page_id,
    )

    async def run():
        async with SessionLocal() as s:
            return await visuals_service.generate(
                s, tenant=tenant, payload=request
            )

    return run


def _campaign_spec(
    *,
    tenant: TenantContext,
    payload: GenerateBundleRequest,
    profile: BusinessProfileResponse,
    campaign_type: CampaignType,
    landing_page_id: uuid.UUID | None,
):
    request = GenerateCampaignRequest(
        campaign_type=campaign_type,
        duration_days=payload.duration_days,
        platforms=list(profile.preferred_platforms),
        goal=payload.theme,
        landing_page_id=landing_page_id,
    )

    async def run():
        async with SessionLocal() as s:
            return await campaigns_service.generate(
                s, tenant=tenant, payload=request
            )

    return run


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _pick_ad_type(platforms: list[str]) -> AdType:
    lowered = [p.lower() for p in platforms]
    if any("linkedin" in p for p in lowered):
        return "linkedin"
    if any("instagram" in p for p in lowered):
        return "instagram_promo"
    if any("facebook" in p or "meta" in p for p in lowered):
        return "meta"
    if any("google" in p or "search" in p for p in lowered):
        return "google_search"
    return "meta"


def _campaign_type_for_objective(objective: str) -> CampaignType:
    if objective in ("leads",):
        return "lead_generation"
    if objective in ("conversions", "sales"):
        return "product_launch"
    if objective == "awareness":
        return "brand_awareness"
    if objective == "engagement":
        return "engagement_growth"
    return "lead_generation"


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if "503" in msg or "UNAVAILABLE" in msg:
        return "The AI was briefly under heavy load — regenerate this piece in a moment."
    if "429" in msg or "rate" in msg.lower():
        return "Rate-limited by the AI provider — try again in 30 seconds."
    if "truncated" in msg.lower() or "max_tokens" in msg.lower():
        return "The AI's response was too long for one piece — regenerate from the studio."
    if "409" in msg or "onboarding" in msg.lower():
        return "Couldn't generate — finish onboarding to fix this."
    return msg[:140]


def _to_response(row: Bundle) -> BundleResponse:
    return BundleResponse(
        id=row.id,
        user_id=row.user_id,
        business_profile_id=row.business_profile_id,
        landing_page_id=row.landing_page_id,
        theme=row.theme,
        objective=row.objective,
        duration_days=row.duration_days,
        pieces=[BundlePiece.model_validate(p) for p in (row.pieces or [])],
        created_at=row.created_at,
    )
