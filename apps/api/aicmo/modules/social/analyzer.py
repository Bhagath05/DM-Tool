"""Pattern extractor.

Reads the user's recent SocialAsset rows + the latest PerformanceSignal
per asset, flattens them into a markdown-ish table, asks Gemini to find
2-5 winning patterns, then persists those patterns to `winning_patterns`
+ `audience_patterns`.

One Gemini call. No chains, no per-pattern follow-up calls. The result
shows up on /social/insights and — more importantly — feeds the
GenerationContext that every studio inherits.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.social.models import (
    AudiencePattern,
    PerformanceSignal,
    SocialAsset,
    WinningPattern,
)
from aicmo.modules.social.prompts import (
    ANALYZER_SYSTEM_PROMPT,
    build_analyzer_user_prompt,
)
from aicmo.modules.social.schemas import AnalyzeResult, _AnalysisOutput
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()

# Analyzer was originally pinned to Gemini Flash for cost. Now uses the
# platform-default provider so a single API key powers everything.
_MAX_TOKENS = 3200


async def run_analyzer(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    platform: str | None = None,
    max_assets: int = 50,
) -> AnalyzeResult:
    """Public entry point. Returns counts; the rows themselves land in
    `winning_patterns` + `audience_patterns` for the frontend to read."""
    brand_id = tenant.brand_id
    # 1) Pull recent assets + their latest signal.
    asset_stmt = (
        select(SocialAsset)
        .where(SocialAsset.brand_id == brand_id)
        .order_by(desc(SocialAsset.posted_at))
        .limit(max(5, min(max_assets, 200)))
    )
    if platform:
        asset_stmt = asset_stmt.where(SocialAsset.platform == platform)
    assets = list((await session.execute(asset_stmt)).scalars().all())

    if len(assets) < 3:
        return AnalyzeResult(
            patterns_created=0,
            audience_patterns_created=0,
            assets_considered=len(assets),
        )

    latest_signal_by_asset: dict[uuid.UUID, PerformanceSignal] = {}
    sig_stmt = (
        select(PerformanceSignal)
        .where(PerformanceSignal.asset_id.in_([a.id for a in assets]))
        .order_by(desc(PerformanceSignal.captured_at))
    )
    for sig in (await session.execute(sig_stmt)).scalars():
        if sig.asset_id not in latest_signal_by_asset:
            latest_signal_by_asset[sig.asset_id] = sig

    # 2) Look up profile for business context in the prompt.
    profile_row = await onboarding_service.get_profile_or_none(
        session, brand_id
    )
    business_name = (
        getattr(profile_row, "business_name", None) or "this business"
    )
    industry = getattr(profile_row, "industry", None) or "unspecified industry"

    # 3) Flatten into a stable index table the LLM can reference.
    assets_block = _render_assets_block(assets, latest_signal_by_asset)

    # 4) Single Gemini call.
    router = get_llm_router()
    user_prompt = build_analyzer_user_prompt(
        business_name=business_name,
        industry=industry,
        platform_focus=platform,
        assets_block=assets_block,
    )

    try:
        result = await router.generate(
            response_schema=_AnalysisOutput,
            system=ANALYZER_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_prompt)],
            temperature=0.45,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as e:  # noqa: BLE001 — analyzer must degrade, not crash
        log.warning("social.analyzer_failed", error=str(e))
        return AnalyzeResult(
            patterns_created=0,
            audience_patterns_created=0,
            assets_considered=len(assets),
        )

    output = result.data

    # 5) Persist. Replace any prior patterns for this brand+platform first.
    await _delete_prior_patterns(session, brand_id=brand_id, platform=platform)

    created_winning = 0
    for w in output.winning_patterns:
        source_ids: list[uuid.UUID] = []
        for idx in w.source_asset_indices:
            if 0 <= idx < len(assets):
                source_ids.append(assets[idx].id)
        session.add(
            WinningPattern(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                platform=platform,
                hook_pattern=w.hook_pattern,
                visual_pattern=w.visual_pattern,
                caption_pattern=w.caption_pattern,
                cta_pattern=w.cta_pattern,
                format_pattern=w.format_pattern,
                posting_time_pattern=w.posting_time_pattern,
                summary=w.summary,
                performance_score=float(w.performance_score),
                source_asset_ids=[str(i) for i in source_ids],
            )
        )
        created_winning += 1

    created_audience = 0
    for a in output.audience_patterns:
        if platform is None:
            continue
        session.add(
            AudiencePattern(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                platform=platform,
                pattern_type=a.pattern_type,
                description=a.description,
                confidence_score=float(a.confidence_score),
            )
        )
        created_audience += 1

    await session.commit()
    log.info(
        "social.analyzer_completed",
        brand_id=str(brand_id),
        platform=platform,
        assets=len(assets),
        winning=created_winning,
        audience=created_audience,
    )
    return AnalyzeResult(
        patterns_created=created_winning,
        audience_patterns_created=created_audience,
        assets_considered=len(assets),
    )


# ---------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------


def _render_assets_block(
    assets: list[SocialAsset],
    latest_signal_by_asset: dict[uuid.UUID, PerformanceSignal],
) -> str:
    """Compact, stable index → row table the LLM can reference by integer.

    Format chosen so Gemini reliably parses it AND we keep token count low
    even at max_assets=50.
    """
    lines: list[str] = [
        "Index | Platform | Type | Posted | Caption (first 80 chars) | Impressions | Reach | Likes | Comments | Saves | Shares | Views | Engagement%",
        "----- | -------- | ---- | ------ | ----------------------- | ----------- | ----- | ----- | -------- | ----- | ------ | ----- | ----------",
    ]
    for i, a in enumerate(assets):
        s = latest_signal_by_asset.get(a.id)
        caption_short = (a.caption or "(no caption)")[:80].replace(
            "\n", " "
        ).replace("|", "/")
        posted = a.posted_at.isoformat()[:10] if a.posted_at else "—"
        eng_pct = f"{(s.engagement_rate * 100):.1f}%" if s else "—"
        if s is None:
            metrics = "— | — | — | — | — | — | —"
        else:
            metrics = (
                f"{s.impressions} | {s.reach} | {s.likes} | "
                f"{s.comments_count} | {s.saves} | {s.shares} | {s.views}"
            )
        lines.append(
            f"{i} | {a.platform} | {a.asset_type} | {posted} | {caption_short} | {metrics} | {eng_pct}"
        )
    return "\n".join(lines)


async def _delete_prior_patterns(
    session: AsyncSession, *, brand_id: uuid.UUID, platform: str | None
) -> None:
    """Soft-replace: we treat the analyzer as 'rewrite the latest read'
    rather than 'append'. Otherwise the dashboard fills with stale
    duplicates as users re-run analysis."""
    # Use raw deletes (small N expected — patterns are 2-5 per analysis).
    wp_q = select(WinningPattern).where(WinningPattern.brand_id == brand_id)
    ap_q = select(AudiencePattern).where(AudiencePattern.brand_id == brand_id)
    if platform:
        wp_q = wp_q.where(WinningPattern.platform == platform)
        ap_q = ap_q.where(AudiencePattern.platform == platform)

    for r in (await session.execute(wp_q)).scalars():
        await session.delete(r)
    for r in (await session.execute(ap_q)).scalars():
        await session.delete(r)
    await session.flush()
