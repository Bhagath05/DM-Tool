"""Planner service — profile + latest strategy → today's plan.

`generate_daily_plan` is the pure, testable core. `plan_today` is the thin DB
glue that loads the (brand-scoped) profile + latest completed strategy. Nothing
is persisted and nothing is executed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.learning import feedback as learning_feedback
from aicmo.modules.onboarding import service as onboarding_service
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.planner import prompts
from aicmo.modules.planner.schemas import DailyPlan, DailyPlanResponse
from aicmo.modules.strategist import service as strategist_service
from aicmo.modules.strategist.schemas import MarketingStrategy


class ProfileMissing(Exception):
    """No business profile for this brand yet."""


async def generate_daily_plan(
    profile: BusinessProfileResponse,
    strategy: MarketingStrategy | None,
    learning_block: str = "",
) -> DailyPlan:
    """Pure of the DB so it can be unit-tested with a mocked LLM router.

    `learning_block` (Module 6) injects the brand's learned lessons so the plan
    reflects what has actually worked."""
    router = get_llm_router()
    result = await router.generate(
        response_schema=DailyPlan,
        system=prompts.SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                content=prompts.build_plan_prompt(profile, strategy, learning_block),
            ),
        ],
        max_tokens=2048,
    )
    return result.data


async def plan_today(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> DailyPlanResponse:
    profile_row = await onboarding_service.get_profile_or_none(session, brand_id)
    if profile_row is None:
        raise ProfileMissing()
    profile = BusinessProfileResponse.model_validate(profile_row)

    strategy: MarketingStrategy | None = None
    record = await strategist_service.latest(session, brand_id=brand_id)
    if record is not None and record.status == "completed" and record.strategy:
        strategy = MarketingStrategy.model_validate(record.strategy)

    # Module 6 — today's plan reflects what has actually worked for this brand.
    learning_block = await learning_feedback.learning_context_block(
        session, brand_id=brand_id, module="planner"
    )
    plan = await generate_daily_plan(profile, strategy, learning_block)
    return DailyPlanResponse(plan=plan, grounded_in_strategy=strategy is not None)
