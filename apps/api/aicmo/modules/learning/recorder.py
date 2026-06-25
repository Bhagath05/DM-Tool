"""Thin call-site helper for generators.

Generators import `record_generation` and call it inline right after the
asset row is persisted. The helper:

- builds the variable_choices dict from `(platform, goal, tone, *extras)`
- pulls the inherited_patterns + a trimmed context_snapshot from the
  GenerationContext (when one was used)
- swallows ALL exceptions so a slow / failing recorder never blocks the
  user's generation. The Learning Lab is an enrichment, not a hard dep.

Post W1-12: takes `tenant: TenantContext` so the experiment row gets
populated with both `user_id` (legacy column) and `organization_id` +
`brand_id` (tenant scope).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.learning import service
from aicmo.modules.learning.schemas import (
    ExperimentAssetType,
    RecordExperimentInput,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


def _trim_context(ctx: GenerationContext | None) -> dict:
    if ctx is None:
        return {}
    return {
        "industry": ctx.industry,
        "preferred_platforms": list(ctx.preferred_platforms or []),
        "primary_goal_text": ctx.primary_goal_text,
        "current_phase_summary": ctx.current_phase_summary,
        "social_winning_patterns": list(ctx.social_winning_patterns or [])[:5],
        "social_audience_signals": list(ctx.social_audience_signals or [])[:3],
        "recommended_channels": list(ctx.recommended_channels or [])[:5],
    }


def _inherited_patterns(ctx: GenerationContext | None) -> list[str]:
    if ctx is None:
        return []
    return [s for s in (ctx.social_winning_patterns or []) if s][:8]


async def record_generation(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    source_asset_type: ExperimentAssetType,
    source_asset_id: uuid.UUID,
    platform: str | None = None,
    goal: str | None = None,
    variable_choices: dict[str, Any] | None = None,
    hypothesis: str | None = None,
    context: GenerationContext | None = None,
) -> None:
    """Best-effort record. Never raises — failures log + skip."""
    try:
        payload = RecordExperimentInput(
            source_asset_type=source_asset_type,
            source_asset_id=source_asset_id,
            platform=platform,
            goal=goal,
            hypothesis=hypothesis,
            inherited_patterns=_inherited_patterns(context),
            variable_choices={
                k: v
                for k, v in (variable_choices or {}).items()
                if v is not None
            },
            context_snapshot=_trim_context(context),
        )
        await service.record_experiment(
            session, tenant=tenant, payload=payload
        )
        await session.flush()
    except Exception as e:
        log.warning(
            "learning.recorder_failed",
            error=str(e),
            asset_type=source_asset_type,
            asset_id=str(source_asset_id),
        )
