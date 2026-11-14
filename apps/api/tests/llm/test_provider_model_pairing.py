"""Phase 7.19B — provider/model pairing robustness.

Resolution must be deterministic and never silently pair an explicitly selected
provider with another provider's default model (the 7.19A edge case that sent an
OpenAI model name to Ollama). Pure-function tests pin every resolution path;
router tests confirm the end-to-end behaviour and that capability gates + fallback
are preserved.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from aicmo.llm.policy import (
    ProviderModelResolutionError,
    resolve_model_for_provider,
)
from aicmo.llm.providers.base import LLMMessage, LLMResult, LLMUsage
from aicmo.llm.providers.ollama import OllamaModelNotFoundError, OllamaUnavailableError
from aicmo.llm.router import LLMRouter

DEFAULT_PROVIDER = "openai"


def _pdm(name: str) -> str | None:
    """Stub: a provider's OWN configured default model (none for others)."""
    return {"ollama": "llama3:latest", "openai": "gpt-4o-mini"}.get(name)


def _resolve(chosen, *, model=None, pp=None, pm=None):
    return resolve_model_for_provider(
        chosen, explicit_model=model, policy_provider=pp, policy_model=pm,
        default_provider=DEFAULT_PROVIDER, provider_default_model=_pdm,
    )


# ---------------------------------------------------------------------
#  Pure resolution — all paths
# ---------------------------------------------------------------------


def test_explicit_ollama_provider_and_model():
    assert _resolve("ollama", model="llama3:latest") == "llama3:latest"


def test_explicit_ollama_provider_missing_model_uses_ollama_default():
    # The bug: task policy would hand over the external default model.
    assert _resolve("ollama", pp="openai", pm="gpt-4o-mini") == "llama3:latest"
    # And with no task policy at all.
    assert _resolve("ollama") == "llama3:latest"


def test_explicit_default_provider_missing_model_uses_default_model():
    assert _resolve("openai") == "gpt-4o-mini"


def test_explicit_non_default_provider_missing_model_raises():
    with pytest.raises(ProviderModelResolutionError):
        _resolve("anthropic")  # no configured default model for anthropic


def test_no_override_uses_policy_model_when_provider_matches():
    # Task mapped to google/gemini; chosen provider is google → use gemini.
    assert _resolve("google", pp="google", pm="gemini-2.5-flash") == "gemini-2.5-flash"


def test_override_provider_does_not_inherit_other_providers_policy_model():
    # Overriding to openai while the task policy picked google/gemini must NOT
    # yield gemini — it yields openai's own default.
    assert _resolve("openai", pp="google", pm="gemini-2.5-flash") == "gpt-4o-mini"


def test_explicit_model_override_is_honoured():
    assert _resolve("openai", model="custom-model") == "custom-model"


def test_incompatible_explicit_pair_passed_through():
    # An explicit (incompatible) model is honoured; the provider validates it at
    # call time (surfaces a typed model-not-found), never silently swapped.
    assert _resolve("ollama", model="gpt-4o-mini") == "gpt-4o-mini"


def test_unknown_model_passed_through():
    assert _resolve("ollama", model="ghost-model:1b") == "ghost-model:1b"


# ---------------------------------------------------------------------
#  Router integration
# ---------------------------------------------------------------------


class Sentiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sentiment: str


class _CaptureProvider:
    name = "cap"

    def __init__(self, *, result: Any = None, exc: BaseException | None = None) -> None:
        self._result: Any = result
        self._exc = exc
        self.model_seen: str | None = None
        self.calls = 0

    async def generate_structured(
        self, *, model, system, messages, response_schema, temperature=0.7, max_tokens=2048
    ) -> LLMResult[Any]:
        self.calls += 1
        self.model_seen = model
        if self._exc is not None:
            raise self._exc
        return self._result


def _result() -> LLMResult[Sentiment]:
    return LLMResult(data=Sentiment(sentiment="ok"), model="x", usage=LLMUsage(0, 0))


async def _run(router: LLMRouter, **kw):
    return await router.generate(
        response_schema=Sentiment, system=None,
        messages=[LLMMessage(role="user", content="x")],
        temperature=0, max_tokens=50, **kw,
    )


@pytest.mark.asyncio
async def test_router_ollama_missing_model_pins_ollama_default(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    r = LLMRouter()
    cap = _CaptureProvider(result=_result())
    r._providers["ollama"] = cap
    await _run(r, provider="ollama", task="creative_generation")
    # The ollama provider received its OWN default model, never an external name.
    assert cap.model_seen == "llama3:latest"
    assert cap.calls == 1


@pytest.mark.asyncio
async def test_router_ollama_honours_custom_ollama_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    r = LLMRouter()
    cap = _CaptureProvider(result=_result())
    r._providers["ollama"] = cap
    await _run(r, provider="ollama", task="creative_generation")
    assert cap.model_seen == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_router_unknown_ollama_model_surfaces_controlled_error(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.delenv("OLLAMA_FALLBACK_TASKS", raising=False)
    r = LLMRouter()
    # Simulate the provider rejecting an unknown model.
    r._providers["ollama"] = _CaptureProvider(exc=OllamaModelNotFoundError("no such model"))
    with pytest.raises(OllamaUnavailableError):  # local-only, no silent egress
        await _run(r, provider="ollama", model="ghost-model:1b", task="creative_generation")


@pytest.mark.asyncio
async def test_router_no_override_regression(monkeypatch):
    # Regression: the default path (no provider/model override) is unchanged — it
    # routes to the global default provider with its default model.
    from aicmo.config import get_settings

    r = LLMRouter()
    cap = _CaptureProvider(result=_result())
    settings = get_settings()
    r._providers[settings.llm_default_provider] = cap
    await _run(r)  # no task, no overrides
    assert cap.model_seen == settings.llm_default_model
    assert cap.calls == 1
