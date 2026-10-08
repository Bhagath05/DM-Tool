"""OpenAI provider.

GPT-4o-mini is the cost-optimised default for this provider — punches
above its weight on structured-output tasks and is ~30x cheaper than
the full GPT-4o on input tokens, which matters because every generator
ships a ~400-token context block ahead of the user prompt.

Structured outputs use the native `response_format={"type": "json_schema"}`
path. We send `strict: true` when the schema is fully closed (OpenAI then
guarantees schema-conformant output), and `strict: false` when the schema
contains a free-form object OpenAI strict mode cannot represent — e.g. a
tool-call `arguments` map. In BOTH cases the parsed result is validated
against the Pydantic model, so output is never unvalidated; the only thing
strict mode buys is that OpenAI pre-guarantees conformance.

The strict-mode JSON Schema dialect is a subset of regular JSON Schema:
- `additionalProperties: false` is required on every *closed* object node.
- An *open* key-value map (a `dict` field) can't be expressed in strict
  mode at all — it 400s — so such a schema drops to `strict: false`.
- Every property is treated as required — Pydantic Optional fields need
  `"null"` added to their type union, which we leave in Pydantic's anyOf.
- A few keywords aren't supported (`title`, `default`, `format`, etc.).

We normalise the Pydantic JSON Schema once per call. The cost is tiny
and the trade is: callers write Pydantic, the provider deals with
OpenAI's dialect quirks.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, cast

from openai import NOT_GIVEN, AsyncOpenAI
from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


# Keys OpenAI's strict JSON Schema dialect doesn't accept.
# `format` is allowed for some string formats but not all — easier to
# strip and let the model handle formatting via the prompt.
_DROP_KEYS = {
    "title",
    # `description` carries the Pydantic docstring into the schema. In
    # non-strict mode (used when a schema has a free-form object) the model
    # tends to ECHO a top-level `description` back as an output field, which
    # our `extra="forbid"` models then reject as an unexpected key. The field
    # names + the system prompt already convey intent, so we drop descriptions
    # to keep the output clean. Harmless in strict mode too.
    "description",
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


def _conform_schema(node: Any, state: dict[str, bool]) -> Any:
    """Walk the schema and conform it to OpenAI's JSON Schema dialect.

    1. Drop keywords OpenAI's structured-output mode rejects.
    2. On a *closed* object node (one with declared `properties`): set
       `additionalProperties: false` and mark all properties required —
       the strict-mode rules.
    3. On a *free-form* object node (a `dict`/open map with no declared
       properties, e.g. `ProposedToolCall.arguments`): keep it permissive
       (`additionalProperties: true`) so the model can still emit the
       tool's arguments, and record that the schema is NOT strict-mode
       compatible — OpenAI strict mode cannot represent an open key-value
       map (it rejects the whole request with a 400). `state["strict"]`
       flips to False and the caller then sends `strict: false`, which
       OpenAI accepts; the result is still validated against the Pydantic
       model downstream (`model_validate`), so this is a guided-but-
       validated path, never unvalidated JSON.
    4. Pydantic emits Optional fields as `"anyOf": [..., {"type": "null"}]`
       which OpenAI accepts; we leave that shape alone.
    """
    if isinstance(node, dict):
        out: dict = {}
        for k, v in node.items():
            if k in _DROP_KEYS:
                continue
            out[k] = _conform_schema(v, state)

        if out.get("type") == "object":
            props = out.get("properties")
            if isinstance(props, dict):
                out["required"] = list(props.keys())
                out["additionalProperties"] = False
            else:
                # Free-form object: strict mode can't express it.
                out["additionalProperties"] = True
                state["strict"] = False
        return out
    if isinstance(node, list):
        return [_conform_schema(v, state) for v in node]
    return node


def _prepare_schema(model: type[BaseModel]) -> tuple[dict, bool]:
    """Return (schema, strict_ok). ``strict_ok`` is False when the schema
    contains a free-form object OpenAI strict mode can't represent."""
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline_refs(raw, defs)
    state = {"strict": True}
    schema = _conform_schema(inlined, state)
    return schema, state["strict"]


def _model_requires_default_temperature(model: str) -> bool:
    """GPT-5.x rejects a custom `temperature` (only the default value of 1 is
    supported) and returns 400 `unsupported_value`. For those models the
    sampling temperature must be omitted so the API applies its default; other
    OpenAI chat models still accept a caller-supplied temperature."""
    return model.lower().startswith("gpt-5")


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

        schema, strict_ok = _prepare_schema(response_schema)

        # GPT-5.x chat completions reject `max_tokens` (use `max_completion_tokens`)
        # and reject a custom `temperature` (only the default is allowed) — omit it
        # via NOT_GIVEN for those models so the API applies its default. The provider
        # signature is unchanged, so other providers/models keep the caller's values.
        #
        # `strict` is True only when the schema is fully closed; a schema with a
        # free-form object (e.g. a tool-call `arguments` map) uses strict=false,
        # which OpenAI accepts. Either way the parsed result is validated against
        # the Pydantic model below — we never return unvalidated output.
        resp = await self._client.chat.completions.create(
            model=model,
            messages=openai_messages,  # type: ignore[arg-type]
            temperature=(
                NOT_GIVEN if _model_requires_default_temperature(model) else temperature
            ),
            max_completion_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": schema,
                    "strict": strict_ok,
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
