"""AI analysis for a freshly-onboarded business.

Cost decisions:
- Uses Gemini 2.5 Flash (~40x cheaper than Claude Sonnet on input).
- Single LLM call per onboarding submission. No retries, no chains.
- Runs as a FastAPI BackgroundTask (in-process), so no Redis/Arq required.
"""

from __future__ import annotations

import structlog
from sqlalchemy import update

from aicmo.db.session import SessionLocal
from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.onboarding.models import BusinessProfile
from aicmo.modules.onboarding.prompts import SYSTEM_PROMPT, build_analysis_user_prompt
from aicmo.modules.onboarding.schemas import BusinessAnalysis, BusinessProfileResponse

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).


async def run_analysis(profile_id: str, snapshot: BusinessProfileResponse) -> None:
    """Background entry point. Owns its own DB session so it survives the
    request that triggered it. Failures are recorded on the profile row,
    not re-raised."""
    router = get_llm_router()
    try:
        result = await router.generate(
            response_schema=BusinessAnalysis,
            system=SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=build_analysis_user_prompt(snapshot))],
            temperature=0.6,
            # Phase 2.1 — the v2 BusinessAnalysis adds 3 narrative paragraphs
            # + 3 milestone objects + 3 channel objects + 2 bullet lists, so
            # ~1300 extra tokens of output vs. v1. 4500 leaves headroom for
            # verbose audience descriptions without truncating the JSON tail.
            max_tokens=4500,
        )
    except Exception as e:  # noqa: BLE001 — analyzer must never crash the worker
        log.warning(
            "onboarding.analysis_failed", profile_id=profile_id, error=str(e)
        )
        await _mark_failed(profile_id, str(e))
        return

    await _mark_completed(profile_id, result.data)
    log.info(
        "onboarding.analysis_completed",
        profile_id=profile_id,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )


async def _mark_completed(profile_id: str, analysis: BusinessAnalysis) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(BusinessProfile)
            .where(BusinessProfile.id == profile_id)
            .values(
                analysis_status="completed",
                analysis=analysis.model_dump(mode="json"),
                analysis_error=None,
            )
        )
        await session.commit()


async def _mark_failed(profile_id: str, error: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(BusinessProfile)
            .where(BusinessProfile.id == profile_id)
            .values(analysis_status="failed", analysis_error=error[:1000])
        )
        await session.commit()
