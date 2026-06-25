"""OpenAI provider.

GPT-4o-mini is the cost-optimised default for this provider — punches
above its weight on structured-output tasks and is ~30x cheaper than
the full GPT-4o on input tokens, which matters because every generator
ships a ~400-token context block ahead of the user prompt.

Structured outputs use the native `response_format={"type": "json_schema",
"strict": True}` path. OpenAI guarantees the response will parse into
the schema, so we don't need the tool-use indirection the Anthropic
provider falls back to.

The strict-mode JSON Schema dialect is a subset of regular JSON Schema:
- `additionalProperties: false` is required on every object node.
- Every property is treated as required — Pydantic Optional fields need
  `"null"` added to their type union, which we do via `_strict_schema`.
- A few keywords aren't supported (`title`, `default`, `format`, etc.).

We normalise the Pydantic JSON Schema once per call. The cost is tiny
and the trade is: callers write Pydantic, the provider deals with
OpenAI's dialect quirks.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, cast

from openai import AsyncOpenAI
from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


# Keys OpenAI's strict JSON Schema dialect doesn't accept.
# `format` is allowed for some string formats but not all — easier to
# strip and let the model handle formatting via the prompt.
_DROP_KEYS = {
    "title",
    "default",
    "format",
    "$defs",
    "definitions",
    "examples",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "multipleOf",
    "pattern",
}


def _inline_refs(node: Any, defs: dict) -> Any:
    """Resolve `$ref` against `$defs`. OpenAI's strict mode accepts refs
    but the corner cases are easier to debug when the schema is flat."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/")[-1], {})
            return _inline_refs(target, defs)
        return {
            k: _inline_refs(v, defs)
            for k, v in node.items()
            if k != "$defs"
        }
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _strict_schema(node: Any) -> Any:
    """Walk the schema and conform it to OpenAI strict JSON Schema rules.

    1. Drop keywords OpenAI strict mode rejects.
    2. On every object node: set `additionalProperties: false` and mark
       all properties as required (strict mode rule).
    3. Pydantic emits Optional fields as `"anyOf": [{"type": "X"}, {"type":
       "null"}]` which OpenAI accepts. Plain `"type": "X"` with a missing
       value would fail — we leave Pydantic's anyOf shape alone.
    """
    if isinstance(node, dict):
        out: dict = {}
        for k, v in node.items():
            if k in _DROP_KEYS:
                continue
            out[k] = _strict_schema(v)

        if out.get("type") == "object":
            props = out.get("properties")
            if isinstance(props, dict):
                out["required"] = list(props.keys())
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict_schema(v) for v in node]
    return node


def _prepare_schema(model: type[BaseModel]) -> dict:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline_refs(raw, defs)
    return _strict_schema(inlined)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

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
        openai_messages: list[dict[str, str]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            if m.role in ("user", "assistant"):
                openai_messages.append({"role": m.role, "content": m.content})

        schema = _prepare_schema(response_schema)

        resp = await self._client.chat.completions.create(
            model=model,
            messages=openai_messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )

        choice = resp.choices[0]
        raw = choice.message.content or ""

        # Strict JSON-schema mode also signals refusals via .refusal.
        # The SDK puts a non-None .refusal on the message when the
        # safety system blocked the request.
        refusal = getattr(choice.message, "refusal", None)
        if refusal:
            raise RuntimeError(f"OpenAI refused the request: {refusal}")

        if choice.finish_reason == "length":
            raise RuntimeError(
                "OpenAI response was truncated — schema too large for the "
                "current max_tokens. Increase max_tokens and retry."
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"OpenAI returned non-JSON despite strict mode: {raw[:200]}"
            ) from e

        data = response_schema.model_validate(payload)
        usage = resp.usage
        return LLMResult(
            data=cast(T, data),
            model=resp.model,
            usage=LLMUsage(
                input_tokens=(usage.prompt_tokens if usage else 0) or 0,
                output_tokens=(usage.completion_tokens if usage else 0) or 0,
            ),
        )
