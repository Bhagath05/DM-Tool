"""Phase B — task-based LLM policy routing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from aicmo.config import Settings
from aicmo.llm.policy import (
    LLMTaskPolicy,
    LLMTaskPolicyError,
    describe_task_policy,
    parse_llm_task_models,
    resolve_task_route,
)
from aicmo.llm.providers.base import LLMMessage, LLMResult, LLMUsage
from aicmo.llm.router import LLMRouter
from aicmo.llm.tasks import KNOWN_LLM_TASKS


class _TinyOut(BaseModel):
    ok: bool = True


def test_parse_empty_config():
    assert parse_llm_task_models("") == {}
    assert parse_llm_task_models("   ") == {}


def test_parse_valid_entries():
    raw = "business_research:google/gemini-2.5-flash,intelligence:openai/gpt-5.6"
    got = parse_llm_task_models(raw)
    assert got["business_research"] == ("google", "gemini-2.5-flash")
    assert got["intelligence"] == ("openai", "gpt-5.6")


@pytest.mark.parametrize(
    "raw",
    [
        "not_a_task:openai/gpt-4o",
        "intelligence:openai",  # missing model slash
        "intelligence:azure/gpt-4o",  # disallowed provider
        "intelligence:openai/bad model",  # whitespace in model
        ":openai/gpt-4o",
        "intelligence:",
    ],
)
def test_parse_malformed_fails_closed(raw: str):
    with pytest.raises(LLMTaskPolicyError):
        parse_llm_task_models(raw)


def test_settings_rejects_malformed_llm_task_models():
    with pytest.raises(ValidationError):
        Settings(llm_task_models="intelligence:not-a-provider/gpt-x")


def test_unknown_task_fails_safely():
    with pytest.raises(LLMTaskPolicyError, match="Unknown LLM task"):
        resolve_task_route(
            "hack_the_planet",  # type: ignore[arg-type]
            task_models_raw="",
            default_provider="openai",
            default_model="gpt-5.6",
        )


def test_no_task_returns_no_policy_override():
    assert resolve_task_route(
        None,
        task_models_raw="intelligence:google/gemini-2.5-flash",
        default_provider="openai",
        default_model="gpt-5.6",
    ) == (None, None)


def test_unmapped_known_task_uses_global_default():
    assert resolve_task_route(
        "intelligence",
        task_models_raw="",
        default_provider="openai",
        default_model="gpt-5.6",
    ) == ("openai", "gpt-5.6")


def test_task_policy_overrides_global_default():
    assert resolve_task_route(
        "business_research",
        task_models_raw="business_research:google/gemini-2.5-flash",
        default_provider="openai",
        default_model="gpt-5.6",
    ) == ("google", "gemini-2.5-flash")


def test_describe_policy_exposes_no_secrets():
    from dataclasses import fields

    policy = describe_task_policy(
        "intelligence",
        task_models_raw="intelligence:anthropic/claude-sonnet-4-6",
        default_provider="openai",
        default_model="gpt-5.6",
    )
    assert isinstance(policy, LLMTaskPolicy)
    blob = repr(policy)
    assert "api_key" not in blob.lower()
    assert "sk-" not in blob
    assert {f.name for f in fields(policy)} == {"task", "provider", "model"}


@pytest.mark.asyncio
async def test_router_default_behavior_unchanged_without_task():
    """No task → still LLM_DEFAULT_PROVIDER / MODEL (existing path)."""
    router = LLMRouter()
    captured: dict[str, Any] = {}

    async def _fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return LLMResult(
            data=_TinyOut(),
            model=kwargs["model"],
            usage=LLMUsage(input_tokens=1, output_tokens=1),
        )

    fake_provider = MagicMock()
    fake_provider.generate_structured = AsyncMock(side_effect=_fake_generate_structured)
    settings = SimpleNamespace(
        llm_default_provider="openai",
        llm_default_model="gpt-5.6",
        llm_task_models="intelligence:google/gemini-2.5-flash",
    )
    with (
        patch("aicmo.llm.router.get_settings", return_value=settings),
        patch.object(router, "_provider", return_value=fake_provider) as prov,
    ):
        await router.generate(
            response_schema=_TinyOut,
            system=None,
            messages=[LLMMessage(role="user", content="hi")],
        )
    prov.assert_called_once_with("openai")
    assert captured["model"] == "gpt-5.6"


@pytest.mark.asyncio
async def test_router_task_selects_configured_provider_model():
    router = LLMRouter()
    captured: dict[str, Any] = {}

    async def _fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return LLMResult(
            data=_TinyOut(),
            model=kwargs["model"],
            usage=LLMUsage(input_tokens=1, output_tokens=1),
        )

    fake_provider = MagicMock()
    fake_provider.generate_structured = AsyncMock(side_effect=_fake_generate_structured)
    settings = SimpleNamespace(
        llm_default_provider="openai",
        llm_default_model="gpt-5.6",
        llm_task_models="business_research:google/gemini-2.5-flash",
    )
    with (
        patch("aicmo.llm.router.get_settings", return_value=settings),
        patch.object(router, "_provider", return_value=fake_provider) as prov,
    ):
        await router.generate(
            response_schema=_TinyOut,
            system=None,
            messages=[LLMMessage(role="user", content="hi")],
            task="business_research",
        )
    prov.assert_called_once_with("google")
    assert captured["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_explicit_override_wins_over_task_and_default():
    router = LLMRouter()
    captured: dict[str, Any] = {}

    async def _fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return LLMResult(
            data=_TinyOut(),
            model=kwargs["model"],
            usage=LLMUsage(input_tokens=1, output_tokens=1),
        )

    fake_provider = MagicMock()
    fake_provider.generate_structured = AsyncMock(side_effect=_fake_generate_structured)
    settings = SimpleNamespace(
        llm_default_provider="openai",
        llm_default_model="gpt-5.6",
        llm_task_models="intelligence:google/gemini-2.5-flash",
    )
    with (
        patch("aicmo.llm.router.get_settings", return_value=settings),
        patch.object(router, "_provider", return_value=fake_provider) as prov,
    ):
        await router.generate(
            response_schema=_TinyOut,
            system=None,
            messages=[LLMMessage(role="user", content="hi")],
            task="intelligence",
            provider="anthropic",
            model="claude-sonnet-4-6",
        )
    prov.assert_called_once_with("anthropic")
    assert captured["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_partial_explicit_override_merges_with_task_policy():
    """Explicit provider only → model still from task policy."""
    router = LLMRouter()
    captured: dict[str, Any] = {}

    async def _fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return LLMResult(
            data=_TinyOut(),
            model=kwargs["model"],
            usage=LLMUsage(input_tokens=1, output_tokens=1),
        )

    fake_provider = MagicMock()
    fake_provider.generate_structured = AsyncMock(side_effect=_fake_generate_structured)
    settings = SimpleNamespace(
        llm_default_provider="openai",
        llm_default_model="gpt-5.6",
        llm_task_models="creative_generation:openai/gpt-4o-mini",
    )
    with (
        patch("aicmo.llm.router.get_settings", return_value=settings),
        patch.object(router, "_provider", return_value=fake_provider) as prov,
    ):
        await router.generate(
            response_schema=_TinyOut,
            system=None,
            messages=[LLMMessage(role="user", content="hi")],
            task="creative_generation",
            provider="anthropic",
        )
    prov.assert_called_once_with("anthropic")
    assert captured["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_router_unknown_task_does_not_call_provider():
    router = LLMRouter()
    settings = SimpleNamespace(
        llm_default_provider="openai",
        llm_default_model="gpt-5.6",
        llm_task_models="",
    )
    with (
        patch("aicmo.llm.router.get_settings", return_value=settings),
        patch.object(router, "_provider") as prov,
    ):
        with pytest.raises(LLMTaskPolicyError):
            await router.generate(
                response_schema=_TinyOut,
                system=None,
                messages=[LLMMessage(role="user", content="hi")],
                task="not_a_real_task",  # type: ignore[arg-type]
            )
    prov.assert_not_called()


def test_known_tasks_are_closed_set():
    assert "business_research" in KNOWN_LLM_TASKS
    assert "user_supplied_anything" not in KNOWN_LLM_TASKS


def test_provider_selection_stays_behind_router_abstraction():
    """Policy module must not import vendor SDKs."""
    import inspect

    import aicmo.llm.policy as policy_mod

    src = inspect.getsource(policy_mod)
    assert "AsyncOpenAI" not in src
    assert "AsyncAnthropic" not in src
    assert "google.genai" not in src
    assert "from openai" not in src
    assert "from anthropic" not in src
    assert "from google" not in src
