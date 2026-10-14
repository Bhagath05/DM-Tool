"""Phase 7.11/2 — provider SELECTION verification (deterministic, no real calls).

Confirms the staging decision (OpenAI + gpt-5.6, no task overrides) is what the
code actually does: the router resolves to openai/gpt-5.6, never silently falls
back to another provider, rejects a disallowed provider, fails safely with only
the ENV-VAR NAME when the key is missing, and that the API and worker production
guards both require the SAME key for the selected provider.

Mocks only — no paid provider call is made.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from aicmo.llm.providers.base import LLMMessage, LLMResult, LLMUsage


class _Tiny(BaseModel):
    answer: str


def _settings_stub(provider="openai", model="gpt-5.6", task_models=""):
    return SimpleNamespace(
        llm_default_provider=provider,
        llm_default_model=model,
        llm_task_models=task_models,
    )


class _FakeProvider:
    def __init__(self, sink: dict):
        self._sink = sink

    async def generate_structured(self, *, model, **_kw):
        self._sink["model"] = model
        return LLMResult(data=_Tiny(answer="ok"), model=model, usage=LLMUsage(1, 1))


async def _run(monkeypatch, *, settings, provider=None, model=None, task=None):
    """Drive LLMRouter.generate with a captured _provider; returns what it chose."""
    from aicmo.llm import router as router_mod

    sink: dict = {}
    r = router_mod.LLMRouter()
    monkeypatch.setattr(router_mod, "get_settings", lambda: settings)

    def _fake_provider(name: str):
        sink["provider"] = name
        return _FakeProvider(sink)

    monkeypatch.setattr(r, "_provider", _fake_provider)
    await r.generate(
        response_schema=_Tiny, system=None,
        messages=[LLMMessage(role="user", content="hi")],
        task=task, provider=provider, model=model,
    )
    return sink


@pytest.mark.asyncio
async def test_defaults_select_openai_gpt56(monkeypatch):
    sink = await _run(monkeypatch, settings=_settings_stub())
    assert sink["provider"] == "openai"
    assert sink["model"] == "gpt-5.6"


@pytest.mark.asyncio
async def test_empty_task_models_use_global_default_no_fallback(monkeypatch):
    # A known task with NO task-model mapping must resolve to the global default
    # (openai/gpt-5.6), not to anthropic/google.
    sink = await _run(monkeypatch, settings=_settings_stub(), task="intelligence")
    assert sink["provider"] == "openai"
    assert sink["model"] == "gpt-5.6"


@pytest.mark.asyncio
async def test_missing_openai_key_fails_safely_without_leaking(monkeypatch):
    # Real OpenAIProvider __init__ with an empty key: raises naming the ENV VAR
    # only — no key value, and no fallback to another provider.
    from aicmo.config import get_settings
    from aicmo.llm.providers.openai import OpenAIProvider

    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError) as exc:
            OpenAIProvider()
    finally:
        get_settings.cache_clear()
    msg = str(exc.value)
    assert "OPENAI_API_KEY" in msg
    assert "sk-" not in msg and "secret" not in msg.lower()


@pytest.mark.asyncio
async def test_no_silent_fallback_when_default_provider_errors(monkeypatch):
    # If the selected (openai) provider construction fails, the router surfaces
    # it and never instantiates anthropic/google instead.
    from aicmo.llm import router as router_mod

    r = router_mod.LLMRouter()
    monkeypatch.setattr(router_mod, "get_settings", lambda: _settings_stub())
    seen: list[str] = []

    def _boom(name: str):
        seen.append(name)
        raise RuntimeError("OPENAI_API_KEY is not set")

    monkeypatch.setattr(r, "_provider", _boom)
    with pytest.raises(RuntimeError):
        await r.generate(
            response_schema=_Tiny, system=None,
            messages=[LLMMessage(role="user", content="hi")], task=None,
        )
    assert seen == ["openai"]  # only the selected provider was attempted


@pytest.mark.asyncio
async def test_disallowed_provider_override_is_rejected(monkeypatch):
    from aicmo.llm import router as router_mod

    r = router_mod.LLMRouter()
    monkeypatch.setattr(router_mod, "get_settings", lambda: _settings_stub())
    with pytest.raises(ValueError, match="Disallowed LLM provider"):
        await r.generate(
            response_schema=_Tiny, system=None,
            messages=[LLMMessage(role="user", content="hi")],
            task=None, provider="cohere",
        )


def test_gpt5_model_is_handled_by_openai_provider():
    from aicmo.llm.providers.openai import _model_requires_default_temperature

    # gpt-5.x needs the default-temperature + max_completion_tokens handling that
    # the provider implements — i.e. gpt-5.6 is a supported model shape.
    assert _model_requires_default_temperature("gpt-5.6") is True
    assert _model_requires_default_temperature("gpt-4o-mini") is False


def _prod_settings(**over):
    """A production Settings built WITHOUT the repo .env, so only our overrides
    and field defaults apply."""
    from aicmo.config import Settings

    base = dict(
        api_env="production",
        llm_default_provider="openai",
        openai_api_key="",  # the one we assert is flagged
        anthropic_api_key="real-anthropic-key-value",
        google_api_key="real-google-key-value",
    )
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]  # pydantic-settings kwarg


def test_api_and_worker_require_the_same_openai_key():
    from aicmo.config import validate_production_secrets, validate_worker_secrets

    s = _prod_settings()

    with pytest.raises(SystemExit) as api_exc:
        validate_production_secrets(s)
    api_msg = str(api_exc.value)
    assert "OPENAI_API_KEY" in api_msg
    assert "ANTHROPIC_API_KEY" not in api_msg and "GOOGLE_API_KEY" not in api_msg

    with pytest.raises(SystemExit) as wk_exc:
        validate_worker_secrets(s)
    wk_msg = str(wk_exc.value)
    assert "OPENAI_API_KEY" in wk_msg
    assert "ANTHROPIC_API_KEY" not in wk_msg and "GOOGLE_API_KEY" not in wk_msg
