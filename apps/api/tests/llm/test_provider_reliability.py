"""Phase 7.6 — LLM provider reliability policy (deterministic, no real calls).

Verifies every agent/advisor/brain LLM client is built with an explicit bounded
timeout and a single bounded retry layer (backoff/jitter/Retry-After handled by
the SDK), that only transient statuses are retried, and that the provider adds no
second retry layer of its own (so retries cannot multiply).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from aicmo.llm.providers.base import LLMMessage
from aicmo.llm.reliability import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_SECONDS,
    LLM_RETRYABLE_STATUS,
    google_http_options,
)


class _Tiny(BaseModel):
    answer: str


def test_retry_policy_retries_only_transient_statuses():
    # Permanent failures must never be retried — retrying cannot help and wastes quota.
    for perm in (400, 401, 403, 404, 422):
        assert perm not in LLM_RETRYABLE_STATUS
    # Transient failures are retried.
    for transient in (429, 500, 502, 503, 504):
        assert transient in LLM_RETRYABLE_STATUS
    assert LLM_MAX_RETRIES >= 1
    assert 0 < LLM_REQUEST_TIMEOUT_SECONDS <= 120


def _dummy_env(monkeypatch):
    from aicmo.config import get_settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    get_settings.cache_clear()
    return get_settings


def test_anthropic_client_has_bounded_timeout_and_retries(monkeypatch):
    get_settings = _dummy_env(monkeypatch)
    try:
        from aicmo.llm.providers.anthropic import AnthropicProvider

        client = AnthropicProvider()._client
        assert client.timeout == LLM_REQUEST_TIMEOUT_SECONDS
        assert client.max_retries == LLM_MAX_RETRIES
    finally:
        get_settings.cache_clear()


def test_openai_client_has_bounded_timeout_and_retries(monkeypatch):
    get_settings = _dummy_env(monkeypatch)
    try:
        from aicmo.llm.providers.openai import OpenAIProvider

        client = OpenAIProvider()._client
        assert client.timeout == LLM_REQUEST_TIMEOUT_SECONDS
        assert client.max_retries == LLM_MAX_RETRIES
    finally:
        get_settings.cache_clear()


def test_google_client_has_bounded_timeout_and_transient_only_retries(monkeypatch):
    get_settings = _dummy_env(monkeypatch)
    try:
        from aicmo.llm.providers.google import GoogleProvider

        ho = GoogleProvider()._client._api_client._http_options
        assert ho.timeout == int(LLM_REQUEST_TIMEOUT_SECONDS * 1000)
        assert ho.retry_options.attempts == 1 + LLM_MAX_RETRIES
        # transient-only + jittered exponential backoff
        assert 400 not in ho.retry_options.http_status_codes
        assert 422 not in ho.retry_options.http_status_codes
        assert 429 in ho.retry_options.http_status_codes
        assert ho.retry_options.jitter and ho.retry_options.exp_base
    finally:
        get_settings.cache_clear()


def test_google_http_options_builder_is_consistent():
    ho = google_http_options()
    assert ho.timeout == int(LLM_REQUEST_TIMEOUT_SECONDS * 1000)
    assert list(ho.retry_options.http_status_codes) == list(LLM_RETRYABLE_STATUS)


@pytest.mark.asyncio
async def test_provider_adds_no_second_retry_layer_on_transient_error():
    """A transient provider error must surface after exactly ONE call from our
    code — the SDK owns retries; we never wrap a second loop around it."""
    from aicmo.llm.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    create = AsyncMock(side_effect=RuntimeError("503 service unavailable"))
    fake = MagicMock()
    fake.messages.create = create
    provider._client = fake

    with pytest.raises(RuntimeError):
        await provider.generate_structured(
            model="claude", system="s",
            messages=[LLMMessage(role="user", content="hi")],
            response_schema=_Tiny, max_tokens=256,
        )
    assert create.await_count == 1  # our layer called the client exactly once


@pytest.mark.asyncio
async def test_provider_returns_validated_result_on_success():
    from aicmo.llm.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    tool_block = SimpleNamespace(type="tool_use", input={"answer": "ok"})
    resp = SimpleNamespace(
        content=[tool_block], model="claude-x",
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    )
    fake = MagicMock()
    fake.messages.create = AsyncMock(return_value=resp)
    provider._client = fake

    result = await provider.generate_structured(
        model="claude", system="s",
        messages=[LLMMessage(role="user", content="hi")],
        response_schema=_Tiny, max_tokens=256,
    )
    assert result.data.answer == "ok"
    assert fake.messages.create.await_count == 1
