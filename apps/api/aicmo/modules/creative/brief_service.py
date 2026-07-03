"""Phase 6.3 — AI creative brief service (spec #6).

Generates a creative brief GROUNDED in real persisted context — business
profile + active strategy + campaign + content — via the one LLM router, and
persists it (tenant-scoped + audited). Every source that actually fed the
brief is recorded in `grounded_in`; absent sources are simply omitted, never
fabricated. Reuses existing services (onboarding profile fetch, strategist
records, campaign plans, generated content) — no data duplication.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm.providers.base import LLMMessage
from aicmo.llm.router import get_llm_router
from aicmo.modules.audit import service as audit_service
from aicmo.modules.campaigns.models import CampaignPlan
from aicmo.modules.content.models import GeneratedContent
from aicmo.modules.creative import brief_prompts
from aicmo.modules.creative.brief_schemas import CreativeBriefResult
from aicmo.modules.creative.models import CreativeBrief
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.strategist.models import MarketingStrategyRecord
from aicmo.tenancy.context import TenantContext


def _profile_block(profile) -> str:
    """Build a context block from whatever real profile fields are present."""
    parts: list[str] = []
    add = lambda label, val: parts.append(f"{label}: {val}") if val else None  # noqa: E731
    add("Business", getattr(profile, "business_name", None))
    add("Industry", getattr(profile, "industry", None))
    add("Audience", getattr(profile, "target_audience", None))
    add("Brand tone", getattr(profile, "brand_tone", None))
    add("Location", getattr(profile, "business_location", None))
    usps = getattr(profile, "unique_selling_points", None) or []
    add("USPs", ", ".join(usps) if usps else None)
    services = getattr(profile, "services", None) or getattr(profile, "products", None) or []
    add("Offering", ", ".join(services) if services else None)
    platforms = getattr(profile, "preferred_platforms", None) or []
    add("Platforms", ", ".join(platforms) if platforms else None)
    add("Primary goal", getattr(profile, "primary_goal_text", None))
    return "BUSINESS PROFILE\n" + "\n".join(parts)


async def _latest_strategy(
    session: AsyncSession, *, brand_id: uuid.UUID, strategy_id: uuid.UUID | None
) -> MarketingStrategyRecord | None:
    stmt = select(MarketingStrategyRecord).where(
        MarketingStrategyRecord.brand_id == brand_id,
        MarketingStrategyRecord.strategy.isnot(None),
    )
    if strategy_id is not None:
        stmt = stmt.where(MarketingStrategyRecord.id == strategy_id)
    stmt = stmt.order_by(desc(MarketingStrategyRecord.created_at)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


def _strategy_block(rec: MarketingStrategyRecord) -> str:
    s = rec.strategy or {}
    keep = {k: s[k] for k in ("audience", "positioning", "core_message", "channels", "themes") if k in s}
    body = "\n".join(f"{k}: {v}" for k, v in keep.items()) or str(s)[:600]
    return "ACTIVE STRATEGY\n" + body


def _campaign_block(c: CampaignPlan) -> str:
    parts = [f"Goal: {c.goal}", f"Type: {c.campaign_type}", f"Tone: {c.tone}"]
    return "CAMPAIGN\n" + "\n".join(parts)


def _content_block(c: GeneratedContent) -> str:
    out = c.output or {}
    snippet = " ".join(str(v) for v in out.values() if isinstance(v, str))[:400]
    return (
        "SOURCE CONTENT\n"
        f"Type: {c.content_type}\nPlatform: {c.platform}\nGoal: {c.goal}\n"
        f"Copy: {snippet}"
    )


async def generate_brief(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    objective: str | None = None,
    campaign_id: uuid.UUID | None = None,
    content_id: uuid.UUID | None = None,
    strategy_id: uuid.UUID | None = None,
) -> CreativeBrief:
    if tenant.brand_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A brand is required.")

    context_blocks: list[str] = []
    grounded_in: list[str] = []

    profile = await onboarding_service.get_profile_or_none(session, tenant.brand_id)
    if profile is None:
        # A brief with zero grounding would be fabrication — refuse.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Add your business profile first — a creative brief must be grounded in real context.",
        )
    context_blocks.append(_profile_block(profile))
    grounded_in.append("business profile")

    strategy = await _latest_strategy(session, brand_id=tenant.brand_id, strategy_id=strategy_id)
    if strategy is not None:
        context_blocks.append(_strategy_block(strategy))
        grounded_in.append("active strategy")

    campaign: CampaignPlan | None = None
    if campaign_id is not None:
        campaign = await session.scalar(
            select(CampaignPlan).where(
                CampaignPlan.id == campaign_id, CampaignPlan.brand_id == tenant.brand_id
            )
        )
        if campaign is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found.")
        context_blocks.append(_campaign_block(campaign))
        grounded_in.append("campaign")

    content: GeneratedContent | None = None
    if content_id is not None:
        content = await session.scalar(
            select(GeneratedContent).where(
                GeneratedContent.id == content_id, GeneratedContent.brand_id == tenant.brand_id
            )
        )
        if content is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Content not found.")
        context_blocks.append(_content_block(content))
        grounded_in.append("content")

    result = await get_llm_router().generate(
        response_schema=CreativeBriefResult,
        system=brief_prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                content=brief_prompts.build_brief_prompt(
                    objective=objective, context_blocks=context_blocks
                ),
            ),
        ],
        max_tokens=1600,
    )
    data: CreativeBriefResult = result.data

    row = CreativeBrief(
        id=uuid.uuid4(),
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        user_id=tenant.user_id,
        campaign_id=campaign_id,
        content_id=content_id,
        strategy_id=strategy.id if strategy is not None else None,
        title=(objective or data.objective)[:200],
        objective=(objective or data.objective)[:120],
        brief=data.model_dump(),
        grounded_in=grounded_in,
        confidence=data.confidence,
        reason=data.reason,
    )
    session.add(row)
    await audit_service.record(
        session,
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user_uuid,
        action="creative.brief_generated",
        brand_id=tenant.brand_id,
        target_type="creative_brief",
        target_id=row.id,
        metadata={"grounded_in": grounded_in, "confidence": data.confidence},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def list_briefs(
    session: AsyncSession, *, tenant: TenantContext, limit: int = 50
) -> list[CreativeBrief]:
    stmt = (
        select(CreativeBrief)
        .where(CreativeBrief.brand_id == tenant.brand_id)
        .order_by(desc(CreativeBrief.created_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_brief(
    session: AsyncSession, *, tenant: TenantContext, brief_id: uuid.UUID
) -> CreativeBrief:
    row = await session.scalar(
        select(CreativeBrief).where(
            CreativeBrief.id == brief_id, CreativeBrief.brand_id == tenant.brand_id
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brief not found.")
    return row
