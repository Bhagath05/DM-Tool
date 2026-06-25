"""Anthropic provider — Claude Sonnet 4.6 is our MVP default.

Structured outputs are obtained via tool-use: we expose a single tool whose
input schema is the target Pydantic model, and force the model to call it.
"""

from __future__ import annotations

from typing import TypeVar, cast

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)

_STRUCTURED_TOOL_NAME = "respond"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate_structured(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[LLMMessage],
        response_schema: type[T],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResult[T]:
        tool = {
            "name": _STRUCTURED_TOOL_NAME,
            "description": (
                f"Return a structured response matching the {response_schema.__name__} schema."
            ),
            "input_schema": response_schema.model_json_schema(),
        }

        anthropic_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        resp = await self._client.messages.create(
            model=model,
            system=system or "",
            messages=anthropic_messages,
            tools=[tool],
            tool_choice={"type": "tool", "name": _STRUCTURED_TOOL_NAME},
            temperature=temperature,
            max_tokens=max_tokens,
        )

        tool_block = next(
            (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if tool_block is None:
            raise RuntimeError("Anthropic response missing tool_use block")

        data = response_schema.model_validate(tool_block.input)
        return LLMResult(
            data=cast(T, data),
            model=resp.model,
            usage=LLMUsage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            ),
        )
