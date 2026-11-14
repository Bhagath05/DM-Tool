"""Single entry point for every LLM call in the codebase.

Feature modules must use this router rather than instantiating provider SDKs
directly. This lets us add caching, telemetry, retries, A/B routing, and
cross-provider failover in one place.

Provider/model selection precedence (Phase B)::

    explicit ``provider`` / ``model`` kwargs
        >
    task policy (``task=`` + ``LLM_TASK_MODELS`` / global default for that task)
        >
    ``LLM_DEFAULT_PROVIDER`` / ``LLM_DEFAULT_MODEL``

``provider`` / ``model`` kwargs are trusted *internal* call-site overrides only
— never bind them to untrusted HTTP request fields.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.ollama_config import get_ollama_config
from aicmo.llm.policy import resolve_model_for_provider, resolve_task_route
from aicmo.llm.providers.anthropic import AnthropicProvider
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult
from aicmo.llm.providers.google import GoogleProvider
from aicmo.llm.providers.ollama import (
    OllamaError,
    OllamaProvider,
    OllamaUnavailableError,
)
from aicmo.llm.providers.openai import OpenAIProvider
from aicmo.llm.tasks import ALLOWED_LLM_PROVIDERS, OLLAMA_ELIGIBLE_TASKS, LLMTask

log = structlog.get_logger()

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
        elif name == "ollama":
            provider = OllamaProvider()
        else:
            raise ValueError(f"Unknown LLM provider: {name}")

        self._providers[name] = provider
        return provider

    def _provider_default_model(self, name: str) -> str | None:
        """The configured default model that belongs to ``name`` — never another
        provider's. Consulted only when a provider is selected without a model.
        ``ollama`` resolves to OLLAMA_MODEL (read lazily, so a bad Ollama config
        never affects non-Ollama calls); the global default provider resolves to
        LLM_DEFAULT_MODEL; any other provider has no configured default."""
        settings = get_settings()
        if name == "ollama":
            return get_ollama_config().model
        if name == settings.llm_default_provider:
            return settings.llm_default_model
        return None

    async def generate(
        self,
        *,
        response_schema: type[T],
        system: str | None,
        messages: list[LLMMessage],
        task: LLMTask | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> LLMResult[T]:
        settings = get_settings()
        policy_provider, policy_model = resolve_task_route(
            task,
            task_models_raw=settings.llm_task_models,
            default_provider=settings.llm_default_provider,
            default_model=settings.llm_default_model,
        )

        # Provider precedence: explicit call override > task policy > global.
        chosen_provider = provider or policy_provider or settings.llm_default_provider

        if chosen_provider not in ALLOWED_LLM_PROVIDERS:
            raise ValueError(f"Disallowed LLM provider: {chosen_provider!r}")

        # Model is resolved FOR the chosen provider (Phase 7.19B) — an explicit
        # provider override never silently inherits another provider's default
        # model. Raises ProviderModelResolutionError if the provider has no model.
        chosen_model = resolve_model_for_provider(
            chosen_provider,
            explicit_model=model,
            policy_provider=policy_provider,
            policy_model=policy_model,
            default_provider=settings.llm_default_provider,
            provider_default_model=self._provider_default_model,
        )

        call: dict[str, Any] = dict(
            system=system,
            messages=messages,
            response_schema=response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Local Ollama routing is capability-gated + fallback-aware (Phase 7.19);
        # every other provider keeps the exact prior behaviour.
        if chosen_provider == "ollama":
            return await self._generate_via_ollama(task=task, model=chosen_model, call=call)

        return await self._provider(chosen_provider).generate_structured(
            model=chosen_model, **call
        )

    async def _generate_via_ollama(
        self, *, task: str | None, model: str, call: dict[str, Any]
    ) -> LLMResult[Any]:
        """Run a task on the local Ollama provider with the Phase 7.19 safety
        gates: only eligible tasks may route locally, Ollama is skipped when
        disabled, and any failure applies the per-task fallback / local-only
        policy."""
        cfg = get_ollama_config()

        # Capability gate: high-stakes tasks must never run on the local model.
        if task is not None and task not in OLLAMA_ELIGIBLE_TASKS:
            raise ValueError(
                f"LLM task {task!r} is not eligible for local Ollama routing; "
                f"keep it on an external provider."
            )

        if not cfg.enabled:
            return await self._ollama_fallback_or_error(
                task=task, call=call, reason="disabled"
            )

        try:
            return await self._provider("ollama").generate_structured(
                model=model or cfg.model, **call
            )
        except OllamaError as e:
            # Never log the prompt or business data — only the task + failure type.
            log.warning(
                "llm.ollama.generation_failed", task=task, error=type(e).__name__
            )
            return await self._ollama_fallback_or_error(
                task=task, call=call, reason=type(e).__name__
            )

    async def _ollama_fallback_or_error(
        self, *, task: str | None, call: dict[str, Any], reason: str
    ) -> LLMResult[Any]:
        """Apply the explicit per-task fallback policy. External fallback runs
        ONLY for a task the operator opted into via OLLAMA_FALLBACK_TASKS;
        otherwise this is local-only and raises a controlled error rather than
        silently sending prompt data to an external provider."""
        cfg = get_ollama_config()
        if task is not None and task in cfg.fallback_tasks:
            settings = get_settings()
            ext_provider = settings.llm_default_provider
            ext_model = settings.llm_default_model
            log.info(
                "llm.ollama.fallback_to_external",
                task=task,
                provider=ext_provider,
                reason=reason,
            )
            return await self._provider(ext_provider).generate_structured(
                model=ext_model, **call
            )
        raise OllamaUnavailableError(
            f"Ollama unavailable for task {task!r} (reason={reason}) and no external "
            f"fallback is configured for this task; refusing to egress data."
        )


@lru_cache
def get_llm_router() -> LLMRouter:
    return LLMRouter()
