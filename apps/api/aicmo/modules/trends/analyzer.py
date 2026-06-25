"""Collects raw trends and runs the single Gemini analysis call.

Stays inside FastAPI's BackgroundTasks. Owns its own DB session so the
HTTP request that triggered it can return immediately.
"""

from __future__ import annotations

import structlog
from sqlalchemy import update

from aicmo.db.session import SessionLocal
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.collector import collect
from aicmo.modules.trends.models import TrendReport
from aicmo.modules.trends.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.trends.schemas import RawTrends, TrendAnalysis

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).


async def run_refresh(report_id: str, profile: BusinessProfileResponse) -> None:
    keywords = _seed_keywords(profile)
    reddit_query = profile.industry

    try:
        raw = await collect(keywords=keywords, reddit_query=reddit_query)
    except Exception as e:  # noqa: BLE001
        log.warning("trends.collect_failed", report_id=report_id, error=str(e))
        await _mark_failed(report_id, f"collector failed: {e}", raw=None)
        return

    if not raw.google_trends and not raw.reddit_posts:
        await _mark_failed(report_id, "all trend sources returned empty", raw=raw)
        return

    router = get_llm_router()
    try:
        result = await router.generate(
            response_schema=TrendAnalysis,
            system=SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=build_user_prompt(profile, raw))],
            temperature=0.6,
            # TrendAnalysis is rich (up to 8 topics + 8 content ideas + 5
            # hashtag clusters + marketing angles, each with explanations).
            # 4000 turned out to be tight — Gemini sometimes produces verbose
            # `why_it_matters` / `description` text and runs past the ceiling,
            # truncating the JSON mid-stream. 8000 fits the worst-case schema
            # fully populated. Flash output is cheap (~$0.0006/refresh extra).
            max_tokens=8000,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("trends.analysis_failed", report_id=report_id, error=str(e))
        await _mark_failed(report_id, f"analyzer failed: {e}", raw=raw)
        return

    await _mark_completed(report_id, raw=raw, analysis=result.data)
    log.info(
        "trends.analysis_completed",
        report_id=report_id,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )


def _seed_keywords(profile: BusinessProfileResponse) -> list[str]:
    """Pick the keywords we feed to Google Trends. Industry first (the
    primary signal), then business name as a tiebreaker. Competitors are
    deliberately excluded to keep us under pytrends' rate ceiling."""
    seeds = [profile.industry, profile.business_name]
    return [s for s in seeds if s and s.strip()]


async def _mark_completed(
    report_id: str, *, raw: RawTrends, analysis: TrendAnalysis
) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(TrendReport)
            .where(TrendReport.id == report_id)
            .values(
                status="completed",
                raw_trends=raw.model_dump(mode="json"),
                analysis=analysis.model_dump(mode="json"),
                analysis_error=None,
            )
        )
        await session.commit()


async def _mark_failed(
    report_id: str, error: str, *, raw: RawTrends | None
) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(TrendReport)
            .where(TrendReport.id == report_id)
            .values(
                status="failed",
                raw_trends=raw.model_dump(mode="json") if raw else None,
                analysis_error=error[:1000],
            )
        )
        await session.commit()
