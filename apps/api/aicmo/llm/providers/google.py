"""Google Gemini provider.

Gemini 2.5 Flash is the cost-optimised default for this provider — ~40x
cheaper than Claude Sonnet on input tokens. We use the new google-genai
SDK with native response_schema support for structured outputs.
"""

from __future__ import annotations

import json
from typing import TypeVar, cast

from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from aicmo.config import get_settings
from aicmo.llm.providers.base import LLMMessage, LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


def _inline_refs(node, defs: dict) -> object:
    """Recursively replace {"$ref": "#/$defs/X"} with the inlined X.

    Pydantic emits `$ref` whenever a BaseModel contains another BaseModel.
    Gemini's `response_schema` accepts plain JSON Schema, so we resolve refs
    against the top-level $defs before sending.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/")[-1], {})
            return _inline_refs(target, defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _strip_unsupported_keys(schema):
    """Drop JSON Schema keywords Gemini doesn't accept.

    `title` is tricky: Pydantic emits it as metadata ({"title": "MyModel",
    "type": "object", ...}) AND it's a legitimate property NAME when a
    schema has a field called "title". Distinguish by value type:
      - title: str   → metadata (drop)
      - title: dict  → property definition under `properties` (keep)
    """
    drop_always = {"additionalProperties", "$defs", "$ref", "definitions"}
    if isinstance(schema, dict):
        out: dict = {}
        for k, v in schema.items():
            if k in drop_always:
                continue
            if k == "title" and isinstance(v, str):
                # Metadata — Gemini doesn't use it.
                continue
            out[k] = _strip_unsupported_keys(v)
        return out
    if isinstance(schema, list):
        return [_strip_unsupported_keys(v) for v in schema]
    return schema


def _prepare_schema(model: type[BaseModel]) -> dict:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline_refs(raw, defs)
    return _strip_unsupported_keys(inlined)  # type: ignore[arg-type]


def _safe_finish_reason(resp) -> str | None:
    """Pull the finish_reason off a Gemini response without crashing if the
    SDK shape shifts. Returns the enum name (e.g. 'STOP', 'MAX_TOKENS')
    or None when unavailable."""
    try:
        candidate = resp.candidates[0]
        reason = candidate.finish_reason
        return getattr(reason, "name", str(reason))
    except (AttributeError, IndexError, TypeError):
        return None


class GoogleProvider(LLMProvider):
    name = "google"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        self._client = genai.Client(api_key=settings.google_api_key)

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
        # Gemini expects a single prompt or a list of Contents.
        contents = [
            genai_types.Content(role=m.role, parts=[genai_types.Part(text=m.content)])
            for m in messages
            if m.role in ("user", "model", "assistant")
        ]
        for c in contents:
            if c.role == "assistant":
                c.role = "model"  # Gemini calls assistant turns "model"

        schema = _prepare_schema(response_schema)

        config = genai_types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=schema,
        )

        resp = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        raw = resp.text or ""
        # Distinguish truncation (hit max_output_tokens mid-stream) from a
        # genuine non-JSON response. The former produces a much clearer
        # signal so callers can decide to bump max_tokens or retry, and
        # the friendly-error layer on the frontend can show the right copy.
        finish_reason = _safe_finish_reason(resp)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            if finish_reason == "MAX_TOKENS":
                raise RuntimeError(
                    "Gemini response was truncated — the schema is too large "
                    "for the current max_tokens. Increase max_tokens and retry."
                ) from e
            raise RuntimeError(f"Gemini returned non-JSON: {raw[:200]}") from e

        data = response_schema.model_validate(payload)
        usage = resp.usage_metadata
        return LLMResult(
            data=cast(T, data),
            model=model,
            usage=LLMUsage(
                input_tokens=(usage.prompt_token_count if usage else 0) or 0,
                output_tokens=(usage.candidates_token_count if usage else 0) or 0,
            ),
        )
