"""Regression tests for the OpenAI provider's Chat Completions wire params.

GPT-5.x has two incompatibilities the provider must handle at the API boundary,
without changing the provider's abstraction (callers still pass `max_tokens=` and
`temperature=`):

1. `max_tokens` is rejected -> send `max_completion_tokens`.
2. a custom `temperature` is rejected (only the default of 1 is allowed) -> omit
   it (NOT_GIVEN) for GPT-5.x so the API applies its default.

Non-GPT-5 OpenAI models must keep the caller-supplied temperature (backwards
compatible).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import NOT_GIVEN
from pydantic import BaseModel

from aicmo.llm.providers.base import LLMMessage
from aicmo.llm.providers.openai import OpenAIProvider


class _TinySchema(BaseModel):
    answer: str


def _provider_with_capture() -> tuple[OpenAIProvider, dict]:
    """A provider wired to a fake OpenAI client that records the create() kwargs.

    Bypasses __init__ (which requires OPENAI_API_KEY) since these tests exercise
    only the request-construction logic, not client auth."""
    captured: dict = {}

    async def _fake_create(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        message = SimpleNamespace(content='{"answer":"ok"}', refusal=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(
            choices=[choice], model=kwargs.get("model", "unknown"), usage=usage
        )

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=_fake_create)

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._client = fake_client
    return provider, captured


@pytest.mark.asyncio
async def test_generate_structured_sends_max_completion_tokens_not_max_tokens() -> None:
    provider, captured = _provider_with_capture()

    result = await provider.generate_structured(
        model="gpt-5",
        system="sys",
        messages=[LLMMessage(role="user", content="hi")],
        response_schema=_TinySchema,
        temperature=0.7,
        max_tokens=2200,
    )

    assert result.data.answer == "ok"
    assert captured["max_completion_tokens"] == 2200
    assert "max_tokens" not in captured


@pytest.mark.asyncio
async def test_gpt5_request_omits_custom_temperature() -> None:
    """GPT-5.6 must NOT send temperature=0.85; it must still send model,
    messages, and max_completion_tokens."""
    provider, captured = _provider_with_capture()

    await provider.generate_structured(
        model="gpt-5.6",
        system="sys",
        messages=[LLMMessage(role="user", content="hi")],
        response_schema=_TinySchema,
        temperature=0.85,
        max_tokens=2048,
    )

    # The unsupported custom temperature is not sent as a real value.
    assert captured["temperature"] is NOT_GIVEN
    assert captured["temperature"] != 0.85
    # The rest of the request is intact.
    assert captured["model"] == "gpt-5.6"
    assert captured["messages"]  # non-empty
    assert captured["max_completion_tokens"] == 2048


@pytest.mark.asyncio
async def test_non_gpt5_request_keeps_custom_temperature() -> None:
    """Backwards compatibility: a model that accepts custom sampling still
    receives the caller-supplied temperature."""
    provider, captured = _provider_with_capture()

    await provider.generate_structured(
        model="gpt-4o-mini",
        system="sys",
        messages=[LLMMessage(role="user", content="hi")],
        response_schema=_TinySchema,
        temperature=0.85,
        max_tokens=2048,
    )

    assert captured["temperature"] == 0.85
