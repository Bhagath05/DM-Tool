"""Single entry point for every LLM call in the codebase.

Feature modules must use this router rather than instantiating provider SDKs
directly. This lets us add caching, telemetry, retries, A/B routing, and
cross-provider failover in one place.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.providers.anthropic import AnthropicProvider
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult
from aicmo.llm.providers.google import GoogleProvider
from aicmo.llm.providers.openai import OpenAIProvider

T = TypeVar("T", bound=BaseModel)


class LLMRouter:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def _provider(self, name: str) -> LLMProvider:
        if name in self._providers:
            return self._providers[name]

        if name == "anthropic":
            provider: LLMProvider = AnthropicProvider()
        elif name == "google":
            provider = GoogleProvider()
        elif name == "openai":
            provider = OpenAIProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {name}")

        self._providers[name] = provider
        return provider

    async def generate(
        self,
        *,
        response_schema: type[T],
        system: str | None,
        messages: list[LLMMessage],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResult[T]:
        settings = get_settings()
        chosen_provider = provider or settings.llm_default_provider
        chosen_model = model or settings.llm_default_model

        return await self._provider(chosen_provider).generate_structured(
            model=chosen_model,
            system=system,
            messages=messages,
            response_schema=response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )


@lru_cache
def get_llm_router() -> LLMRouter:
    return LLMRouter()
