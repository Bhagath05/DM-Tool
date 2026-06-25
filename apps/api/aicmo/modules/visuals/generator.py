"""Single Gemini call for visual briefs.

Same one-shot discipline as content/ads. No retries, no chains, no fallbacks.
Failed parses surface to the user — they hit regenerate.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis
from aicmo.modules.visuals.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.visuals.schemas import (
    SCHEMA_BY_TYPE,
    VisualStrategy,
    VisualType,
    split_payload,
)

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).
# Slightly higher temperature than ads — creative direction benefits from variance.
_TEMPERATURE = 0.8
# Higher headroom — carousel briefs can have up to 10 slide_designs.
_MAX_TOKENS_BY_TYPE: dict[VisualType, int] = {
    "ad_creative": 3600,
    "carousel": 4000,
    "reel": 3600,
    "thumbnail": 2800,
}


async def generate_visual(
    *,
    visual_type: VisualType,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    platform: str,
    goal: str,
    tone_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> tuple[VisualStrategy, dict, int, int]:
    """Returns (strategy, type-specific output dict, input_tokens, output_tokens).

    Phase 3.0 — `context` is optional. When provided, the prompt inherits
    winning patterns + strategist recommendations. Old callers unaffected.
    """
    schema: type[BaseModel] = SCHEMA_BY_TYPE[visual_type]
    user_prompt = build_user_prompt(
        visual_type=visual_type,
        profile=profile,
        trend_analysis=trend_analysis,
        platform=platform,
        goal=goal,
        tone_override=tone_override,
        context=context,
        recommendation_context=recommendation_context,
    )

    router = get_llm_router()
    result = await router.generate(
        response_schema=schema,
        system=SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_prompt)],
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS_BY_TYPE.get(visual_type, 2800),
    )

    strategy, output = split_payload(result.data)
    log.info(
        "visuals.generated",
        visual_type=visual_type,
        platform=platform,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return (
        strategy,
        output,
        result.usage.input_tokens,
        result.usage.output_tokens,
    )
