"""Phase 7.19 — Ollama local-inference configuration.

Read from the process environment directly rather than ``aicmo.config``: the
latter is a protected file this phase must not modify, and the Ollama settings
are a self-contained, opt-in local-provider concern.

Safe-by-default:
  * ``OLLAMA_ENABLED`` is false unless explicitly turned on — Ollama is never a
    hard startup dependency and never the global provider default.
  * ``OLLAMA_BASE_URL`` must be a loopback endpoint (default
    ``http://127.0.0.1:11434``). A non-loopback endpoint is rejected unless the
    operator explicitly sets ``OLLAMA_ALLOW_NON_LOOPBACK=true`` (the documented,
    deliberate path for a secured self-hosted inference server). The endpoint is
    never accepted from an HTTP request — it is server configuration only.
  * ``OLLAMA_FALLBACK_TASKS`` opts specific tasks into external fallback on an
    Ollama failure. Empty by default, so a task routed locally stays local — a
    failure returns a controlled error instead of silently egressing prompt data
    to an external provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from aicmo.llm.tasks import KNOWN_LLM_TASKS

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3:latest"

# Hostnames that resolve to the local loopback interface.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class OllamaConfigError(ValueError):
    """Malformed or disallowed Ollama configuration — fail closed."""


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_base_url(url: str, *, allow_non_loopback: bool) -> str:
    """Validate + normalise an Ollama base URL. Loopback-only unless explicitly
    allowed. Raises ``OllamaConfigError`` on anything unsafe or malformed."""
    text = (url or "").strip()
    if not text:
        raise OllamaConfigError("OLLAMA_BASE_URL is empty")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise OllamaConfigError(
            f"OLLAMA_BASE_URL must be http(s): {text!r}"
        )
    host = (parsed.hostname or "").lower()
    if not host:
        raise OllamaConfigError(f"OLLAMA_BASE_URL has no host: {text!r}")
    if not allow_non_loopback and host not in _LOOPBACK_HOSTS:
        raise OllamaConfigError(
            f"OLLAMA_BASE_URL host {host!r} is not loopback. Local inference binds "
            f"to 127.0.0.1; to point at a secured self-hosted server set "
            f"OLLAMA_ALLOW_NON_LOOPBACK=true."
        )
    return text.rstrip("/")


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    """Resolved, validated Ollama settings. Never carries secrets (local
    inference needs no API key)."""

    enabled: bool
    base_url: str
    model: str
    fallback_tasks: frozenset[str]


def get_ollama_config() -> OllamaConfig:
    """Read + validate Ollama settings from the environment. Raises
    ``OllamaConfigError`` on a malformed endpoint or unknown fallback task."""
    enabled = _truthy(os.environ.get("OLLAMA_ENABLED"))
    allow_non_loopback = _truthy(os.environ.get("OLLAMA_ALLOW_NON_LOOPBACK"))
    base_url = validate_base_url(
        os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL,
        allow_non_loopback=allow_non_loopback,
    )
    model = (os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL).strip()
    if not model:
        raise OllamaConfigError("OLLAMA_MODEL is empty")

    raw_fallback = (os.environ.get("OLLAMA_FALLBACK_TASKS") or "").strip()
    fallback = frozenset(t.strip() for t in raw_fallback.split(",") if t.strip())
    unknown = fallback - KNOWN_LLM_TASKS
    if unknown:
        raise OllamaConfigError(
            f"Unknown task(s) in OLLAMA_FALLBACK_TASKS: {sorted(unknown)}"
        )

    return OllamaConfig(
        enabled=enabled, base_url=base_url, model=model, fallback_tasks=fallback
    )
