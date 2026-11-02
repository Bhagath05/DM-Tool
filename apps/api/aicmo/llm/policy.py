"""Task → (provider, model) policy resolution.

No SDK imports. No API keys. Only answers: given a trusted task id (and
optional server config), which provider name + model string should the
router use before falling back to global defaults.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aicmo.llm.tasks import ALLOWED_LLM_PROVIDERS, KNOWN_LLM_TASKS, LLMTask


@dataclass(frozen=True, slots=True)
class LLMTaskPolicy:
    """Resolved routing target for one task. Never carries secrets."""

    task: str
    provider: str
    model: str


class LLMTaskPolicyError(ValueError):
    """Invalid task id or malformed LLM_TASK_MODELS configuration."""


class ProviderModelResolutionError(ValueError):
    """A provider was selected (explicitly or by policy) but no model could be
    paired with it without silently borrowing another provider's default model.
    A clear, typed configuration error — never a silent cross-provider pairing."""


def parse_llm_task_models(raw: str) -> dict[str, tuple[str, str]]:
    """Parse ``LLM_TASK_MODELS`` into ``{task: (provider, model)}``.

    Format (comma-separated entries)::

        business_research:google/gemini-2.5-flash,intelligence:openai/gpt-5.6

    Empty / whitespace → no overrides (all tasks fall through to global
    defaults when a task is requested but unmapped).

    Raises ``LLMTaskPolicyError`` on malformed entries, unknown tasks, or
    disallowed providers — fail closed at settings load / resolve time.
    """
    text = (raw or "").strip()
    if not text:
        return {}

    out: dict[str, tuple[str, str]] = {}
    for part in text.split(","):
        entry = part.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise LLMTaskPolicyError(
                f"Malformed LLM_TASK_MODELS entry (expected task:provider/model): {entry!r}"
            )
        task_name, rest = entry.split(":", 1)
        task_name = task_name.strip()
        rest = rest.strip()
        if not task_name or task_name not in KNOWN_LLM_TASKS:
            raise LLMTaskPolicyError(f"Unknown or empty LLM task in LLM_TASK_MODELS: {task_name!r}")
        if "/" not in rest:
            raise LLMTaskPolicyError(
                f"Malformed LLM_TASK_MODELS target (expected provider/model): {rest!r}"
            )
        provider, model = rest.split("/", 1)
        provider = provider.strip()
        model = model.strip()
        if provider not in ALLOWED_LLM_PROVIDERS:
            raise LLMTaskPolicyError(f"Disallowed LLM provider in LLM_TASK_MODELS: {provider!r}")
        if not model or any(ch.isspace() for ch in model):
            raise LLMTaskPolicyError(
                f"Invalid model name in LLM_TASK_MODELS for task {task_name!r}"
            )
        if len(model) > 128:
            raise LLMTaskPolicyError(
                f"Model name too long in LLM_TASK_MODELS for task {task_name!r}"
            )
        out[task_name] = (provider, model)
    return out


def resolve_task_route(
    task: LLMTask | str | None,
    *,
    task_models_raw: str,
    default_provider: str,
    default_model: str,
) -> tuple[str | None, str | None]:
    """Return ``(provider, model)`` overrides from task policy, or ``(None, None)``.

    - ``task is None`` → ``(None, None)`` (caller uses global defaults).
    - Unknown task → raises ``LLMTaskPolicyError`` (never silent fallback).
    - Known task with no config entry → ``(default_provider, default_model)``
      so supplying a task without LLM_TASK_MODELS stays deterministic and
      equivalent to today's global default.
    - Known task with config entry → configured pair.

    Does not apply explicit call-site overrides — the router does that.
    """
    if task is None:
        return None, None

    task_name = str(task).strip()
    if task_name not in KNOWN_LLM_TASKS:
        raise LLMTaskPolicyError(f"Unknown LLM task: {task_name!r}")

    mapping = parse_llm_task_models(task_models_raw)
    if task_name in mapping:
        provider, model = mapping[task_name]
        return provider, model

    # Unmapped known task → explicit global default (not "unsafe" invention).
    if default_provider not in ALLOWED_LLM_PROVIDERS:
        raise LLMTaskPolicyError(f"Disallowed default LLM provider: {default_provider!r}")
    if not (default_model or "").strip():
        raise LLMTaskPolicyError("LLM_DEFAULT_MODEL is empty")
    return default_provider, default_model.strip()


def resolve_model_for_provider(
    chosen_provider: str,
    *,
    explicit_model: str | None,
    policy_provider: str | None,
    policy_model: str | None,
    default_provider: str,
    provider_default_model: Callable[[str], str | None],
) -> str:
    """Resolve the model to use WITH ``chosen_provider`` — never another
    provider's default model (Phase 7.19B).

    Precedence:
      1. An explicit ``model`` override is always honoured — the caller owns the
         pairing, and the provider validates compatibility at call time (an
         incompatible pair surfaces a typed provider error, e.g. model-not-found).
      2. Otherwise the task-policy model is used ONLY when it belongs to the
         chosen provider (the chosen provider equals the provider the policy /
         global default produced that model for).
      3. Otherwise the chosen provider's OWN configured default model is used,
         if it has one (e.g. OLLAMA_MODEL for ``ollama``; LLM_DEFAULT_MODEL for
         the global default provider).
      4. Otherwise raise ``ProviderModelResolutionError`` — we never fall back to
         a different provider's default model (the 7.19A edge case that sent an
         OpenAI model name to Ollama).
    """
    if explicit_model is not None:
        return explicit_model

    policy_source_provider = policy_provider or default_provider
    if chosen_provider == policy_source_provider and policy_model is not None:
        return policy_model

    own_default = provider_default_model(chosen_provider)
    if own_default:
        return own_default

    raise ProviderModelResolutionError(
        f"Provider {chosen_provider!r} was selected without a model and has no "
        f"configured default model. Specify a model explicitly (e.g. via "
        f"LLM_TASK_MODELS as '{chosen_provider}/<model>')."
    )


def describe_task_policy(
    task: LLMTask | str,
    *,
    task_models_raw: str,
    default_provider: str,
    default_model: str,
) -> LLMTaskPolicy:
    """Resolved policy for introspection/tests — never includes API keys."""
    provider, model = resolve_task_route(
        task,
        task_models_raw=task_models_raw,
        default_provider=default_provider,
        default_model=default_model,
    )
    assert provider is not None and model is not None
    return LLMTaskPolicy(task=str(task), provider=provider, model=model)
