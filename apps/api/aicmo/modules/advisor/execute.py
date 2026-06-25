"""Auto-execution — map recommendations to existing generators."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.advisor.schemas import ExecuteRecommendationResponse
from aicmo.modules.advisor import service as advisor_service
from aicmo.modules.content.schemas import GenerateRequest
from aicmo.modules.content import service as content_service
from aicmo.modules.publishing import assets as publishing_assets
from aicmo.modules.opportunities.schemas import GeneratorHint
from aicmo.tenancy.context import TenantContext


def _recommendation_context(row) -> str | None:
    parts: list[str] = []
    if row.observation:
        parts.append(f"Observation: {row.observation[:280]}")
    if row.root_cause:
        parts.append(f"Root cause: {row.root_cause[:280]}")
    if row.description:
        parts.append(f"Action: {row.description[:280]}")
    if not parts:
        return None
    return "\n".join(parts)[:600]


async def execute_recommendation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    recommendation_id: uuid.UUID,
) -> ExecuteRecommendationResponse:
    row = await advisor_service.get_recommendation(
        session, brand_id=tenant.brand_id, recommendation_id=recommendation_id
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recommendation not found",
        )

    hint_raw = row.generator_hint
    if not hint_raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This recommendation has no executable generator hint",
        )

    hint = GeneratorHint.model_validate(hint_raw)
    rec_context = _recommendation_context(row)

    if hint.target == "content":
        platform = hint.platform or "Instagram"
        payload = GenerateRequest(
            content_type=hint.format,  # type: ignore[arg-type]
            platform=platform,
            goal=hint.goal,
            recommendation_context=rec_context,
        )
        result = await content_service.generate(
            session, tenant=tenant, payload=payload
        )
        content_asset = await publishing_assets.register_from_content(
            session,
            tenant=tenant,
            content_id=result.id,
            content_type=payload.content_type,
            platform=platform,
            output=result.output,
            recommendation_id=recommendation_id,
        )
        row.linked_asset_type = "content"
        row.linked_asset_id = result.id
        row.status = "in_progress"
        await session.commit()
        return ExecuteRecommendationResponse(
            asset_type="content",
            asset_id=result.id,
            content_asset_id=content_asset.id,
            status="created",
            preview_url=None,
        )

    if hint.target == "ad":
        from aicmo.modules.ads.schemas import GenerateAdRequest
        from aicmo.modules.ads import service as ads_service

        payload = GenerateAdRequest(
            ad_type=hint.format,  # type: ignore[arg-type]
            objective=hint.objective or "leads",
            goal=hint.goal,
            recommendation_context=rec_context,
        )
        result = await ads_service.generate(session, tenant=tenant, payload=payload)
        content_asset = await publishing_assets.register_from_ad(
            session,
            tenant=tenant,
            ad_id=result.id,
            ad_type=payload.ad_type,
            output=result.output,
            recommendation_id=recommendation_id,
        )
        row.linked_asset_type = "ad"
        row.linked_asset_id = result.id
        row.status = "in_progress"
        await session.commit()
        return ExecuteRecommendationResponse(
            asset_type="ad",
            asset_id=result.id,
            content_asset_id=content_asset.id,
            status="created",
            preview_url=None,
        )

    if hint.target == "visual":
        from aicmo.modules.visuals.schemas import GenerateVisualRequest
        from aicmo.modules.visuals import service as visuals_service

        platform = hint.platform or "Instagram"
        visual_type = hint.format if hint.format in (
            "ad_creative",
            "carousel",
            "reel",
            "thumbnail",
        ) else "ad_creative"
        payload = GenerateVisualRequest(
            visual_type=visual_type,  # type: ignore[arg-type]
            platform=platform,
            goal=hint.goal,
            recommendation_context=rec_context,
        )
        result = await visuals_service.generate(
            session, tenant=tenant, payload=payload
        )
        content_asset = await publishing_assets.register_from_visual(
            session,
            tenant=tenant,
            visual_id=result.id,
            visual_type=payload.visual_type,
            output=result.output,
            recommendation_id=recommendation_id,
        )
        row.linked_asset_type = "visual"
        row.linked_asset_id = result.id
        row.status = "in_progress"
        await session.commit()
        return ExecuteRecommendationResponse(
            asset_type="visual",
            asset_id=result.id,
            content_asset_id=content_asset.id,
            status="created",
            preview_url=result.primary_signed_url,
        )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unsupported generator target: {hint.target}",
    )
