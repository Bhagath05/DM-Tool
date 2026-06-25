"""Campaign orchestrator — Objective → Strategy → editable designs.

This is the spine of the priority flow: a user states an outcome ("I need 50
qualified cybersecurity leads") and gets a strategy + a set of editable
creatives (poster / carousel / ad / reel). Each asset is composed into a
`creative_design` through the ONE write path (apply_revision, AI Mode), so
every result is immediately editable, versioned, metered, and audited.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.creative.design import composers
from aicmo.modules.creative.design import service as design_service
from aicmo.modules.growth import strategy as strategy_engine
from aicmo.modules.growth.models import GrowthObjective
from aicmo.modules.growth.strategy_schemas import AssetSpec, CampaignStrategy
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


class BuiltAsset:
    """A composed asset + its persisted design (in-memory pairing for the router)."""

    __slots__ = ("spec", "design")

    def __init__(self, spec: AssetSpec, design) -> None:
        self.spec = spec
        self.design = design


async def build_campaign(
    session: AsyncSession, *, tenant: TenantContext, objective: GrowthObjective
) -> tuple[CampaignStrategy, list[BuiltAsset]]:
    """Plan the campaign and compose every asset into an editable design.
    Each design goes through the design service (apply_revision + meter +
    audit). Returns the strategy and the built assets."""
    strategy = await strategy_engine.plan_campaign(session, tenant=tenant, objective=objective)

    built: list[BuiltAsset] = []
    for spec in strategy.asset_plan:
        # Generate a real hero image for the creative (best-effort — if image
        # gen is unavailable/slow we fall back to a clean text-on-brand layout).
        bg_asset_id: str | None = None
        try:
            img_prompt = (
                f"Professional marketing background photo for a {spec.creative_type}. "
                f"Theme: {spec.headline}. {spec.subhead or ''} "
                f"Audience: {strategy.audience}. Cinematic lighting, high quality, "
                f"on-brand, photographic. No text, no words, no logos."
            )
            asset = await design_service.generate_image_asset(
                session, tenant=tenant, prompt=img_prompt, aspect=spec.aspect
            )
            await session.flush()  # so apply_revision's owned-asset check sees it
            bg_asset_id = str(asset.id)
        except Exception as e:  # noqa: BLE001 — image gen must never sink the campaign
            log.warning("growth.campaign.image_skipped", creative_type=spec.creative_type, error=str(e))

        try:
            full_doc = composers.compose(spec, background_asset_id=bg_asset_id)
        except Exception as e:  # noqa: BLE001 — a bad single asset shouldn't sink the campaign
            log.warning("growth.campaign.compose_failed", creative_type=spec.creative_type, error=str(e))
            continue
        design = await design_service.create_design_from_doc(
            session, tenant=tenant,
            name=f"{spec.creative_type.title()} · {objective.objective_kind}",
            media_type=composers.media_type_for(spec.creative_type),
            full_doc=full_doc, growth_objective_id=objective.id,
            edit_summary=f"AI campaign: {spec.creative_type}", meter=True,
        )
        built.append(BuiltAsset(spec, design))

    log.info(
        "growth.campaign.built", objective_id=str(objective.id),
        assets=len(built), planned=len(strategy.asset_plan),
    )
    return strategy, built
