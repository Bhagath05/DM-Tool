"""The actual Gemini call.

Same one-shot pattern as content: dispatch to the per-platform schema,
single LLM call, no retries, no chains. Failed parses surface to the
user immediately — they hit regenerate.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.ads.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.ads.schemas import (
    SCHEMA_BY_TYPE,
    AdObjective,
    AdStrategy,
    AdTargeting,
    AdType,
    split_payload,
)
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).
# Slightly cooler than content generation. Ads want crispness over flair.
_TEMPERATURE = 0.75
# Google Search variant emits up to 15 headlines + 4 descriptions — needs the headroom.
_MAX_TOKENS = 3200


async def generate_ad(
    *,
    ad_type: AdType,
    objective: AdObjective,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    goal: str,
    tone_override: str | None,
    audience_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> tuple[AdStrategy, AdTargeting, dict, int, int]:
    """Returns (strategy, targeting, output dict, input_tokens, output_tokens).

    Phase 3.0 — pass `context` to inherit winning-pattern hints + strategist
    recommendations. Old callers omit it for unchanged behavior.
    """
    schema: type[BaseModel] = SCHEMA_BY_TYPE[ad_type]
    user_prompt = build_user_prompt(
        ad_type=ad_type,
        objective=objective,
        profile=profile,
        trend_analysis=trend_analysis,
        goal=goal,
        tone_override=tone_override,
        audience_override=audience_override,
        context=context,
        recommendation_context=recommendation_context,
    )

    router = get_llm_router()
    result = await router.generate(
        response_schema=schema,
        system=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_prompt)],
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
    )

    strategy, targeting, output = split_payload(result.data)
    log.info(
        "ads.generated",
        ad_type=ad_type,
        objective=objective,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return (
        strategy,
        targeting,
        output,
        result.usage.input_tokens,
        result.usage.output_tokens,
    )
