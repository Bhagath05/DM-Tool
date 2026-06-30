"""Competitor-intelligence service.

`analyze` is the pure, testable core (validated profile in → LLM →
response out). `analyze_competitors` is the thin DB glue that loads the
brand's business profile and enforces the two precondition errors the
router maps to 409s.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.competitors import prompts
from aicmo.modules.competitors.schemas import CompetitorAnalysisResponse
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse


class ProfileMissing(Exception):
    """The brand has no business profile yet."""


class NoCompetitors(Exception):
    """The business profile lists no competitors to analyse."""


async def analyze(profile: BusinessProfileResponse) -> CompetitorAnalysisResponse:
    """Run the competitor analysis for an already-validated profile.

    Pure of the database so it can be unit-tested with a mocked LLM router.
    """
    router = get_llm_router()
    result = await router.generate(
        response_schema=CompetitorAnalysisResponse,
        system=prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(role="user", content=prompts.build_user_prompt(profile)),
        ],
        max_tokens=3072,
    )
    return result.data


async def analyze_competitors(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> CompetitorAnalysisResponse:
    """Load the brand's profile and analyse the competitors it lists.

    Raises ProfileMissing / NoCompetitors so the router can return clear,
    actionable 409s instead of an empty or fabricated payload.
    """
    profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    if profile_row is None:
        raise ProfileMissing()
    profile = BusinessProfileResponse.model_validate(profile_row)
    if not profile.competitors:
        raise NoCompetitors()
    return await analyze(profile)
