"""Single Gemini call for the entire campaign plan.

No per-day calls. No chains. No retries. The plan comes back in one shot —
strategy envelope + funnel sequence + every calendar day — and we
post-validate the day count server-side.
"""

from __future__ import annotations

import structlog

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.campaigns.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.campaigns.schemas import (
    CalendarDay,
    CampaignCalendar,
    CampaignType,
    split_payload,
)
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).
_TEMPERATURE = 0.75
# 30-day plans: ~150 tok/day output × 30 + envelope (strategy/platforms/sequence/visual) overhead.
_MAX_TOKENS = 5500


class CampaignDayCountMismatch(ValueError):
    """The model returned a number of days that doesn't match the requested duration."""


async def generate_campaign(
    *,
    campaign_type: CampaignType,
    duration_days: int,
    platforms: list[str],
    goal: str,
    tone_override: str | None,
    audience_override: str | None,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    context: GenerationContext | None = None,
) -> tuple[dict, list[CalendarDay], int, int]:
    """Returns (strategy-envelope dict, calendar day list, input_tokens, output_tokens).

    Raises CampaignDayCountMismatch if `len(days) != duration_days` — caller
    surfaces this so the user can regenerate.

    Phase 3.0 — pass `context` to inherit prior strategist analysis +
    winning patterns. Old callers unchanged.
    """
    user_prompt = build_user_prompt(
        campaign_type=campaign_type,
        duration_days=duration_days,
        platforms=platforms,
        goal=goal,
        tone_override=tone_override,
        audience_override=audience_override,
        profile=profile,
        trend_analysis=trend_analysis,
        context=context,
    )

    router = get_llm_router()
    result = await router.generate(
        response_schema=CampaignCalendar,
        system=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_prompt)],
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
    )

    payload: CampaignCalendar = result.data
    if len(payload.days) != duration_days:
        raise CampaignDayCountMismatch(
            f"Model returned {len(payload.days)} days, expected {duration_days}"
        )

    strategy_envelope, days_serialised = split_payload(payload)
    days_typed = [CalendarDay.model_validate(d) for d in days_serialised]

    log.info(
        "campaigns.generated",
        campaign_type=campaign_type,
        duration_days=duration_days,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return (
        strategy_envelope,
        days_typed,
        result.usage.input_tokens,
        result.usage.output_tokens,
    )
