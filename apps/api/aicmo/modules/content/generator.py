"""The actual Gemini call.

Stays simple by design: one provider, one model, one call. No retries,
no chains, no fallbacks. If the call fails the route returns the error
to the user immediately so they can hit regenerate.
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel

from aicmo.llm import get_llm_router
from aicmo.llm.providers.base import LLMMessage
from aicmo.modules.content.prompts import SYSTEM_PROMPT, build_user_prompt
from aicmo.modules.content.schemas import (
    SCHEMA_BY_TYPE,
    ContentStrategy,
    ContentType,
    split_strategy,
)
from aicmo.modules.context.schemas import GenerationContext
from aicmo.modules.onboarding.schemas import BusinessProfileResponse
from aicmo.modules.trends.schemas import TrendAnalysis

log = structlog.get_logger()

# Uses platform-default LLM provider (see config.llm_default_provider).
# Higher temperature than analysis — creative work benefits from variance.
_TEMPERATURE = 0.85
_MAX_TOKENS_BY_TYPE: dict[ContentType, int] = {
    "social_post": 2200,
    "reel": 3600,
    "carousel": 4000,
    "ad_copy": 2400,
    "landing_page_copy": 3200,
    # Phase 6.2 — long-form written types need more headroom.
    "blog_article": 4500,
    "email": 2600,
    "product_description": 2600,
    "press_release": 3200,
    # Part 2 — larger structured types (micro-copy types fall back to 2200).
    "case_study": 3200,
    "customer_story": 3200,
    "product_comparison": 3200,
    "faq": 3200,
    "website_copy": 3400,
    "homepage_copy": 3400,
    "about_us": 3000,
    "service_page": 3400,
    "sales_page": 4200,
    "email_newsletter": 2600,
    "cold_email": 2200,
    "followup_email": 2200,
    "promo_email": 2400,
    "youtube_description": 2600,
    "video_script": 3600,
    "shorts_script": 3000,
    "tiktok_script": 3000,
    "x_thread": 3200,
    "keyword_ideas": 2600,
}


async def generate_content(
    *,
    content_type: ContentType,
    profile: BusinessProfileResponse,
    trend_analysis: TrendAnalysis | None,
    platform: str,
    goal: str,
    tone_override: str | None,
    context: GenerationContext | None = None,
    recommendation_context: str | None = None,
) -> tuple[ContentStrategy, dict, int, int]:
    """Returns (strategy, type-specific output dict, input_tokens, output_tokens).

    Phase 3.0 — when `context` is supplied, the prompt inherits winning-pattern
    hints, recommended channels, and current strategy phase. Old call sites
    that omit `context` get exactly the same prompt as before.
    """
    schema: type[BaseModel] = SCHEMA_BY_TYPE[content_type]
    user_prompt = build_user_prompt(
        content_type=content_type,
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
        max_tokens=_MAX_TOKENS_BY_TYPE.get(content_type, 2200),
    )

    strategy, output = split_strategy(content_type, result.data)
    log.info(
        "content.generated",
        content_type=content_type,
        platform=platform,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return strategy, output, result.usage.input_tokens, result.usage.output_tokens
