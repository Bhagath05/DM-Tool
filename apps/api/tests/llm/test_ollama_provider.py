"""Phase 7.19 — Ollama local-inference provider + routing.

Covers: provider registration, enabled/disabled states, model selection,
structured JSON output, Pydantic validation, malformed output, timeout,
connection-refused, missing model, invalid endpoint, explicit external fallback,
local-only privacy enforcement, existing-provider selection regression, and the
task-eligibility (authorization) invariant. Unit tests mock HTTP via
``httpx.MockTransport``; one real integration test runs against a locally
installed ``llama3:latest`` when the Ollama server is reachable.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field

from aicmo.llm.ollama_config import (
    OllamaConfigError,
    get_ollama_config,
    validate_base_url,
)
from aicmo.llm.providers.base import LLMMessage, LLMResult, LLMUsage
from aicmo.llm.providers.ollama import (
    OllamaConnectionError,
    OllamaInvalidOutputError,
    OllamaModelNotFoundError,
    OllamaProvider,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from aicmo.llm.router import LLMRouter
from aicmo.llm.tasks import ALLOWED_LLM_PROVIDERS


class Sentiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sentiment: str
    confidence: int = Field(ge=0, le=100)


class SentimentLoose(BaseModel):
    sentiment: str
    confidence: int


def _msgs() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="Classify: I love this coffee.")]


def _provider_with(handler) -> OllamaProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="http://127.0.0.1:11434", transport=transport)
    return OllamaProvider(client=client)


def _ok_response(content: dict, *, model: str = "llama3:latest") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "message": {"role": "assistant", "content": json.dumps(content)},
            "prompt_eval_count": 28,
            "eval_count": 15,
            "done": True,
        },
    )


# ---------------------------------------------------------------------
#  Configuration + endpoint validation
# ---------------------------------------------------------------------


def test_config_defaults_disabled_and_loopback(monkeypatch):
    for k in ("OLLAMA_ENABLED", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_FALLBACK_TASKS", "OLLAMA_ALLOW_NON_LOOPBACK"):
        monkeypatch.delenv(k, raising=False)
    cfg = get_ollama_config()
    assert cfg.enabled is False
    assert cfg.base_url == "http://127.0.0.1:11434"
    assert cfg.model == "llama3:latest"
    assert cfg.fallback_tasks == frozenset()


@pytest.mark.parametrize("raw,expected", [("true", True), ("1", True), ("YES", True), ("on", True), ("false", False), ("", False), ("0", False)])
def test_config_enabled_truthiness(monkeypatch, raw, expected):
    monkeypatch.setenv("OLLAMA_ENABLED", raw)
    assert get_ollama_config().enabled is expected


def test_validate_base_url_loopback_ok():
    assert validate_base_url("http://127.0.0.1:11434/", allow_non_loopback=False) == "http://127.0.0.1:11434"
    assert validate_base_url("http://localhost:11434", allow_non_loopback=False).endswith(":11434")


def test_validate_base_url_rejects_non_loopback():
    with pytest.raises(OllamaConfigError):
        validate_base_url("http://evil.example.com:11434", allow_non_loopback=False)
    with pytest.raises(OllamaConfigError):
        validate_base_url("http://10.0.0.5:11434", allow_non_loopback=False)


def test_validate_base_url_allows_non_loopback_when_opted_in():
    assert validate_base_url("https://ollama.internal:11434", allow_non_loopback=True).startswith("https://")


def test_validate_base_url_rejects_bad_scheme_and_empty():
    with pytest.raises(OllamaConfigError):
        validate_base_url("ftp://127.0.0.1", allow_non_loopback=True)
    with pytest.raises(OllamaConfigError):
        validate_base_url("", allow_non_loopback=True)


def test_config_invalid_endpoint_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://attacker.example")
    monkeypatch.delenv("OLLAMA_ALLOW_NON_LOOPBACK", raising=False)
    with pytest.raises(OllamaConfigError):
        get_ollama_config()


def test_config_rejects_unknown_fallback_task(monkeypatch):
    monkeypatch.setenv("OLLAMA_FALLBACK_TASKS", "creative_generation,not_a_task")
    with pytest.raises(OllamaConfigError):
        get_ollama_config()


# ---------------------------------------------------------------------
#  Provider — structured output, validation, failure modes (mocked HTTP)
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_output_validated_and_usage_mapped():
    def handler(_req):
        return _ok_response({"sentiment": "positive", "confidence": 80})

    res = await _provider_with(handler).generate_structured(
        model="llama3:latest", system="be terse", messages=_msgs(),
        response_schema=Sentiment, temperature=0, max_tokens=100,
    )
    assert isinstance(res, LLMResult)
    assert res.data.sentiment == "positive" and res.data.confidence == 80
    assert res.model == "llama3:latest"
    assert res.usage == LLMUsage(input_tokens=28, output_tokens=15)


@pytest.mark.asyncio
async def test_sends_native_json_schema_format_not_plain_json():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        return _ok_response({"sentiment": "neutral", "confidence": 50})

    await _provider_with(handler).generate_structured(
        model="llama3:latest", system=None, messages=_msgs(),
        response_schema=Sentiment, temperature=0.2, max_tokens=64,
    )
    fmt = seen["body"]["format"]
    # Native structured output: a JSON Schema object, not the string "json".
    assert isinstance(fmt, dict) and fmt.get("type") == "object"
    assert "sentiment" in fmt.get("properties", {})
    assert seen["body"]["stream"] is False
    assert seen["body"]["options"]["num_predict"] == 64


@pytest.mark.asyncio
async def test_malformed_json_raises_invalid_output():
    def handler(_req):
        return httpx.Response(200, json={"model": "llama3:latest", "message": {"content": "not-json-at-all"}})

    with pytest.raises(OllamaInvalidOutputError):
        await _provider_with(handler).generate_structured(
            model="llama3:latest", system=None, messages=_msgs(),
            response_schema=Sentiment, temperature=0, max_tokens=100,
        )


@pytest.mark.asyncio
async def test_schema_invalid_value_raises_invalid_output():
    # Valid JSON, but confidence violates ge/le — the grammar does not enforce
    # value constraints; Pydantic does. Unvalidated output is never returned.
    def handler(_req):
        return _ok_response({"sentiment": "positive", "confidence": 500})

    with pytest.raises(OllamaInvalidOutputError):
        await _provider_with(handler).generate_structured(
            model="llama3:latest", system=None, messages=_msgs(),
            response_schema=Sentiment, temperature=0, max_tokens=100,
        )


@pytest.mark.asyncio
async def test_timeout_mapped():
    def handler(_req):
        raise httpx.TimeoutException("timed out")

    with pytest.raises(OllamaTimeoutError):
        await _provider_with(handler).generate_structured(
            model="llama3:latest", system=None, messages=_msgs(),
            response_schema=Sentiment, temperature=0, max_tokens=100,
        )


@pytest.mark.asyncio
async def test_connection_refused_mapped():
    def handler(_req):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(OllamaConnectionError):
        await _provider_with(handler).generate_structured(
            model="llama3:latest", system=None, messages=_msgs(),
            response_schema=Sentiment, temperature=0, max_tokens=100,
        )


@pytest.mark.asyncio
async def test_missing_model_mapped():
    def handler(_req):
        return httpx.Response(404, json={"error": "model 'llama3:latest' not found"})

    with pytest.raises(OllamaModelNotFoundError):
        await _provider_with(handler).generate_structured(
            model="llama3:latest", system=None, messages=_msgs(),
            response_schema=Sentiment, temperature=0, max_tokens=100,
        )


# ---------------------------------------------------------------------
#  Router — registration, eligibility gate, fallback + privacy
# ---------------------------------------------------------------------


class _FakeProvider:
    """Structurally satisfies the LLMProvider protocol for router tests."""

    name = "fake"

    def __init__(self, *, result: Any = None, exc: BaseException | None = None) -> None:
        self._result: Any = result
        self._exc = exc
        self.calls = 0

    async def generate_structured(
        self, *, model, system, messages, response_schema, temperature=0.7, max_tokens=2048
    ) -> LLMResult[Any]:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result


def _result() -> LLMResult[Sentiment]:
    return LLMResult(data=Sentiment(sentiment="positive", confidence=70), model="x", usage=LLMUsage(0, 0))


def test_provider_registration():
    assert "ollama" in ALLOWED_LLM_PROVIDERS
    r = LLMRouter()
    prov = r._provider("ollama")
    assert isinstance(prov, OllamaProvider)


async def _run(router: LLMRouter, **kw):
    return await router.generate(
        response_schema=Sentiment, system=None, messages=_msgs(),
        temperature=0, max_tokens=64, **kw,
    )


@pytest.mark.asyncio
async def test_enabled_eligible_task_routes_to_ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    r = LLMRouter()
    fake = _FakeProvider(result=_result())
    r._providers["ollama"] = fake
    res = await _run(r, provider="ollama", task="creative_generation")
    assert res.data.sentiment == "positive"
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_ineligible_task_to_ollama_is_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    r = LLMRouter()
    r._providers["ollama"] = _FakeProvider(result=_result())
    # strategy_reasoning must stay external — fail closed.
    with pytest.raises(ValueError, match="not eligible"):
        await _run(r, provider="ollama", task="strategy_reasoning")


@pytest.mark.asyncio
async def test_disabled_local_only_raises_and_does_not_egress(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "false")
    monkeypatch.delenv("OLLAMA_FALLBACK_TASKS", raising=False)
    from aicmo.config import get_settings

    r = LLMRouter()
    ollama = _FakeProvider(result=_result())
    external = _FakeProvider(result=_result())
    r._providers["ollama"] = ollama
    r._providers[get_settings().llm_default_provider] = external
    with pytest.raises(OllamaUnavailableError):
        await _run(r, provider="ollama", task="creative_generation")
    # Privacy: nothing was sent to the external provider.
    assert external.calls == 0
    assert ollama.calls == 0


@pytest.mark.asyncio
async def test_failure_without_fallback_is_local_only(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.delenv("OLLAMA_FALLBACK_TASKS", raising=False)
    from aicmo.config import get_settings

    r = LLMRouter()
    external = _FakeProvider(result=_result())
    r._providers["ollama"] = _FakeProvider(exc=OllamaConnectionError("refused"))
    r._providers[get_settings().llm_default_provider] = external
    with pytest.raises(OllamaUnavailableError):
        await _run(r, provider="ollama", task="creative_generation")
    assert external.calls == 0  # no silent external egress


@pytest.mark.asyncio
async def test_explicit_fallback_to_external_when_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_FALLBACK_TASKS", "creative_generation")
    from aicmo.config import get_settings

    r = LLMRouter()
    external = _FakeProvider(result=_result())
    r._providers["ollama"] = _FakeProvider(exc=OllamaConnectionError("refused"))
    r._providers[get_settings().llm_default_provider] = external
    res = await _run(r, provider="ollama", task="creative_generation")
    assert res.data.sentiment == "positive"
    assert external.calls == 1  # explicit, configured fallback


@pytest.mark.asyncio
async def test_existing_provider_selection_unaffected(monkeypatch):
    # Regression: a non-ollama provider path is unchanged by the ollama branch.
    r = LLMRouter()
    external = _FakeProvider(result=_result())
    r._providers["openai"] = external
    res = await _run(r, provider="openai", model="gpt-4o-mini")
    assert res.data.confidence == 70
    assert external.calls == 1


# ---------------------------------------------------------------------
#  Real local integration — runs only if Ollama is reachable
# ---------------------------------------------------------------------


def _ollama_reachable() -> bool:
    try:
        return httpx.get("http://127.0.0.1:11434/api/version", timeout=3).status_code == 200
    except Exception:
        return False


@pytest.mark.asyncio
async def test_real_ollama_structured_output():
    if not _ollama_reachable():
        pytest.skip("Ollama server not reachable on 127.0.0.1:11434")
    prov = OllamaProvider()  # real loopback client
    res = await prov.generate_structured(
        model="llama3:latest",
        system="You are a precise classifier. Reply only with the schema.",
        messages=[LLMMessage(role="user", content="Sentiment of: 'I absolutely love this place.'")],
        response_schema=SentimentLoose,
        temperature=0,
        max_tokens=100,
    )
    assert isinstance(res.data, SentimentLoose)
    assert res.data.sentiment.strip() != ""
    assert res.model.startswith("llama3")
    assert res.usage.output_tokens >= 0
