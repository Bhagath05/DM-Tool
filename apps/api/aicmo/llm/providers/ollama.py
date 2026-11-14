"""Phase 7.19 — Ollama local-inference provider.

Implements the shared ``LLMProvider`` contract against a locally-running Ollama
server (default ``http://127.0.0.1:11434``), so local models plug into the same
router/policy as the external providers — no parallel AI system.

Structured output uses Ollama's NATIVE JSON-Schema enforcement: the Pydantic
model's JSON Schema is sent as ``format`` on ``/api/chat`` (not plain "json"
mode), which constrains generation to the schema. The result is then STILL
validated with ``response_schema.model_validate`` — the schema grammar does not
enforce value constraints (ranges, string formats), so unvalidated model output
is never trusted or returned.

Every failure mode is mapped to a typed ``OllamaError`` subclass so the router
can apply per-task fallback / local-only policy: connection refused, timeout,
missing model, non-2xx, malformed JSON, and schema-validation failure.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, cast

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from aicmo.llm.ollama_config import get_ollama_config
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult, LLMUsage
from aicmo.llm.reliability import LLM_REQUEST_TIMEOUT_SECONDS

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class OllamaError(RuntimeError):
    """Base class for all Ollama provider failures."""


class OllamaConnectionError(OllamaError):
    """Could not reach the local Ollama server (not running / refused)."""


class OllamaTimeoutError(OllamaError):
    """The Ollama request exceeded the bounded timeout."""


class OllamaModelNotFoundError(OllamaError):
    """The requested model is not installed on the Ollama server."""


class OllamaInvalidOutputError(OllamaError):
    """Ollama returned non-JSON or schema-invalid output."""


class OllamaUnavailableError(OllamaError):
    """A task was routed to Ollama but it is disabled or unreachable and the task
    has no external fallback configured — a controlled, local-only failure that
    deliberately does NOT egress prompt data to an external provider."""


def _inline_refs(node: Any, defs: dict) -> Any:
    """Resolve ``$ref`` against ``$defs`` so the schema handed to Ollama is flat.
    Ollama builds a generation grammar from the schema; inlined refs are the most
    robust shape across versions."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return _inline_refs(defs.get(ref.split("/")[-1], {}), defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _schema_for(model: type[BaseModel]) -> dict:
    raw = model.model_json_schema()
    return _inline_refs(raw, raw.get("$defs", {}))


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        cfg = get_ollama_config()
        self._base_url = cfg.base_url
        self._default_model = cfg.model
        # Injectable client for tests; otherwise a bounded-timeout local client.
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=LLM_REQUEST_TIMEOUT_SECONDS
        )

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
        chat_messages: list[dict[str, str]] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        for m in messages:
            if m.role in ("user", "assistant"):
                chat_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": model or self._default_model,
            "stream": False,
            "messages": chat_messages,
            # Native structured output: constrain generation to the schema.
            "format": _schema_for(response_schema),
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        try:
            resp = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as e:
            raise OllamaTimeoutError(
                f"Ollama request timed out after {LLM_REQUEST_TIMEOUT_SECONDS:.0f}s"
            ) from e
        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                "Could not connect to the local Ollama server"
            ) from e
        except httpx.HTTPError as e:
            # Any other transport-level error — do not leak the prompt/body.
            raise OllamaConnectionError(f"Ollama transport error: {type(e).__name__}") from e

        if resp.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Ollama model {payload['model']!r} is not installed (pull it first)"
            )
        if resp.status_code >= 400:
            raise OllamaError(f"Ollama returned HTTP {resp.status_code}")

        try:
            body = resp.json()
        except ValueError as e:
            raise OllamaInvalidOutputError("Ollama response body was not JSON") from e

        content = (body.get("message") or {}).get("content") or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise OllamaInvalidOutputError(
                f"Ollama returned non-JSON content: {content[:200]}"
            ) from e

        try:
            data = response_schema.model_validate(parsed)
        except ValidationError as e:
            # The schema grammar does not enforce value constraints — Pydantic
            # does. A violation here is a controlled, typed failure.
            raise OllamaInvalidOutputError(
                f"Ollama output failed schema validation for {response_schema.__name__}"
            ) from e

        return LLMResult(
            data=cast(T, data),
            model=str(body.get("model") or payload["model"]),
            usage=LLMUsage(
                input_tokens=int(body.get("prompt_eval_count") or 0),
                output_tokens=int(body.get("eval_count") or 0),
            ),
        )
