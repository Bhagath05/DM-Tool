"""Regression: OpenAI chat completions must use max_completion_tokens.

GPT-5.x rejects `max_tokens` with HTTP 400. The provider abstraction still
accepts `max_tokens=`; only the wire parameter sent to OpenAI changes.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from aicmo.llm.providers.base import LLMMessage
from aicmo.llm.providers.openai import OpenAIProvider


class _TinySchema(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_generate_structured_sends_max_completion_tokens_not_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    from aicmo.config import get_settings

    get_settings.cache_clear()

    captured: dict = {}

    async def _fake_create(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        message = SimpleNamespace(content='{"answer":"ok"}', refusal=None)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        return SimpleNamespace(
            choices=[choice],
            model=kwargs.get("model", "gpt-5"),
            usage=usage,
        )

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=_fake_create)

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._client = fake_client

    result = await provider.generate_structured(
        model="gpt-5",
        system="sys",
        messages=[LLMMessage(role="user", content="hi")],
        response_schema=_TinySchema,
        temperature=0.7,
        max_tokens=2200,
    )

    assert result.data.answer == "ok"
    assert "max_completion_tokens" in captured
    assert captured["max_completion_tokens"] == 2200
    assert "max_tokens" not in captured

    get_settings.cache_clear()
