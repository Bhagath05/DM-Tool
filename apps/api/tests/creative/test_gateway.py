"""CS-1 gateway selection, availability, and job execution."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.config import get_settings
from aicmo.modules.creative.gateway.executor import GenerationError, GenerationOutput, _safe_error
from aicmo.modules.creative.gateway.models import CreativeGenerationJob
from aicmo.modules.creative.gateway.registry import ModelCapability, available_for, catalog
from aicmo.modules.creative.gateway.selection import SelectionError, plan_selection
from aicmo.modules.creative.storage.base import StorageRef
from aicmo.tenancy.context import TenantContext


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_openai_hidden_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    openai = next(model for model in catalog() if model.model_id == "gpt-image-1")
    assert openai.available() is False
    assert available_for("image.generate") == []


def test_openai_available_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    models = available_for("image.generate")
    assert [model.model_id for model in models] == ["gpt-image-1"]
    assert models[0].cost_cents == 4
    assert models[0].cost_unit == "image"


def test_slideshow_and_veo_are_not_selectable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    ids = {model.model_id for model in catalog() if model.available()}
    assert "slideshow" not in ids
    assert "veo-3.0-generate-001" not in ids
    slideshow = next(model for model in catalog() if model.model_id == "slideshow")
    assert slideshow.output_kind == "slideshow"
    assert slideshow.verified is False


def test_auto_explains_single_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    plan = plan_selection(
        mode="auto", task="image.generate", model_ids=None, aspect_ratio="1:1", resolution="standard"
    )
    assert [model.model_id for model in plan.models] == ["gpt-image-1"]
    assert "only verified model" in plan.explanation


def test_manual_rejects_unavailable_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    with pytest.raises(SelectionError, match="not available"):
        plan_selection(
            mode="manual",
            task="image.generate",
            model_ids=["slideshow"],
            aspect_ratio="1:1",
            resolution="standard",
        )


def test_compare_does_not_duplicate_the_only_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    plan = plan_selection(
        mode="compare",
        task="image.generate",
        model_ids=["gpt-image-1", "gpt-image-1"],
        aspect_ratio="1:1",
        resolution="standard",
    )
    assert len(plan.models) == 1
    assert "limited" in plan.explanation
    assert "not generated" in plan.explanation


def test_unsupported_aspect_is_rejected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    with pytest.raises(SelectionError):
        plan_selection(
            mode="auto",
            task="image.generate",
            model_ids=None,
            aspect_ratio="3:2",
            resolution="standard",
        )


def test_job_lookup_filters_by_tenant():
    brand = uuid.uuid4()
    org = uuid.uuid4()
    stmt = select(CreativeGenerationJob).where(
        CreativeGenerationJob.id == uuid.uuid4(),
        CreativeGenerationJob.brand_id == brand,
        CreativeGenerationJob.organization_id == org,
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    compact = str(brand).replace("-", "")
    compact_org = str(org).replace("-", "")
    assert compact in sql.replace("-", "")
    assert compact_org in sql.replace("-", "")
    message = _safe_error(RuntimeError("bad key sk-live-secret Bearer abc"))
    assert "sk-live" not in message
    assert "Bearer" not in message


@pytest.mark.asyncio
async def test_job_is_tenant_scoped_and_records_cost(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()

    from aicmo.modules.creative.gateway import service

    async def fake_generate(model, *, prompt, aspect_ratio, resolution):
        assert model.model_id == "gpt-image-1"
        return GenerationOutput(
            image_bytes=b"png",
            mime="image/png",
            width=1024,
            height=1024,
            cost_cents=4,
            duration_ms=12,
            model="gpt-image-1",
            provider="openai",
        )

    costs = []

    async def fake_cost(session, **kwargs):
        costs.append(kwargs)

    async def fake_audit(session, **kwargs):
        return None

    class Storage:
        name = "local"

        def put(self, *, key, data, content_type):
            assert data == b"png"
            return StorageRef(backend="local", key=key)

    monkeypatch.setattr(service, "generate_image", fake_generate)
    monkeypatch.setattr(service, "record_cost", fake_cost)
    monkeypatch.setattr(service, "record_ai_generation", fake_audit)
    monkeypatch.setattr(service, "get_storage_backend", lambda: Storage())

    class Session:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    org = uuid.uuid4()
    brand = uuid.uuid4()
    tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id="user_1", user_uuid=None)
    job = await service.run_generation(
        cast(AsyncSession, Session()),
        tenant=cast(TenantContext, tenant),
        mode="compare",
        task="image.generate",
        prompt="a red shoe",
        model_ids=["gpt-image-1", "gpt-image-1"],
        aspect_ratio="1:1",
        resolution="standard",
    )
    assert job.organization_id == org
    assert job.brand_id == brand
    assert job.status == "succeeded"
    assert len(job.results) == 1
    assert job.results[0]["cost_cents"] == 4
    assert costs[0]["brand_id"] == brand
    assert "sk-" not in str(job.results)


def test_routes_require_content_permissions():
    from aicmo.modules.creative.gateway.router import router

    def permission_of(path: str, method: str) -> str | None:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path != path or method not in route.methods:
                continue
            for dep in route.dependant.dependencies:
                for cell in getattr(dep.call, "__closure__", None) or []:
                    value = cell.cell_contents
                    if value in {"content.create", "content.read"}:
                        return value
        return None

    assert permission_of("/creative/gateway/generations", "POST") == "content.create"
    assert permission_of("/creative/gateway/models", "GET") == "content.read"
    assert permission_of("/creative/gateway/generations/{job_id}", "GET") == "content.read"


@pytest.mark.asyncio
async def test_timeout_is_retried_then_reported(monkeypatch):
    import asyncio

    from aicmo.modules.creative.gateway import executor
    from aicmo.modules.creative.gateway.executor import GenerationError, generate_image

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    monkeypatch.setattr(executor, "_TIMEOUT_S", 0.01)
    calls = {"n": 0}

    class Slow:
        async def generate(self, request):
            calls["n"] += 1
            await asyncio.sleep(0.2)
            raise AssertionError("should have timed out")

    monkeypatch.setattr(executor, "OpenAIImageGenProvider", lambda: Slow())
    model = next(item for item in catalog() if item.model_id == "gpt-image-1")
    with pytest.raises(GenerationError, match="timed out"):
        await generate_image(model, prompt="shoe", aspect_ratio="1:1", resolution="standard")
    assert calls["n"] == 2


def _controlled_model(model_id: str, display_name: str) -> ModelCapability:
    """A verified image model used only by tests. It is not in the production catalog."""
    return ModelCapability(
        model_id=model_id,
        provider="openai",
        task="image.generate",
        display_name=display_name,
        output_kind="generative_image",
        aspect_ratios=("1:1",),
        resolutions=("standard",),
        max_duration_s=None,
        supports_reference_image=False,
        cost_cents=4,
        cost_unit="image",
        verified=True,
        unavailable_reason=None,
    )


def _controlled_models() -> list[ModelCapability]:
    return [
        _controlled_model("gpt-image-1", "OpenAI Images"),
        _controlled_model("test-image", "Test Image"),
    ]


def test_compare_runs_two_controlled_models_once_each(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    from aicmo.modules.creative.gateway import registry

    monkeypatch.setattr(registry, "catalog", _controlled_models)
    plan = plan_selection(
        mode="compare",
        task="image.generate",
        model_ids=["gpt-image-1", "test-image", "gpt-image-1"],
        aspect_ratio="1:1",
        resolution="standard",
    )
    assert [model.model_id for model in plan.models] == ["gpt-image-1", "test-image"]
    assert "Compare will run 2 models" in plan.explanation
    auto = plan_selection(
        mode="auto",
        task="image.generate",
        model_ids=None,
        aspect_ratio="1:1",
        resolution="standard",
    )
    assert auto.models[0].model_id == "gpt-image-1"
    assert "no quality ranking" in auto.explanation


def test_compare_rejects_an_unavailable_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    with pytest.raises(SelectionError, match="slideshow"):
        plan_selection(
            mode="compare",
            task="image.generate",
            model_ids=["gpt-image-1", "slideshow"],
            aspect_ratio="1:1",
            resolution="standard",
        )


@pytest.mark.asyncio
async def test_compare_records_each_model_success_and_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    from aicmo.modules.creative.gateway import registry, service

    monkeypatch.setattr(registry, "catalog", _controlled_models)
    stored: list[str] = []
    audits: list[dict] = []
    costs: list[dict] = []

    async def fake_generate(model, *, prompt, aspect_ratio, resolution):
        if model.model_id == "test-image":
            raise GenerationError("The image provider rejected the request.")
        return GenerationOutput(
            image_bytes=b"png",
            mime="image/png",
            width=1024,
            height=1024,
            cost_cents=4,
            duration_ms=8,
            model=model.model_id,
            provider="openai",
        )

    class Storage:
        name = "local"

        def put(self, *, key, data, content_type):
            stored.append(key)
            assert data == b"png"
            assert content_type == "image/png"
            return StorageRef(backend="local", key=key)

    monkeypatch.setattr(service, "generate_image", fake_generate)

    async def fake_cost(session, **kwargs):
        costs.append(kwargs)

    async def fake_audit(session, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(service, "record_cost", fake_cost)
    monkeypatch.setattr(service, "record_ai_generation", fake_audit)
    monkeypatch.setattr(service, "get_storage_backend", lambda: Storage())

    class Session:
        def add(self, obj):
            return None

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    brand = uuid.uuid4()
    org = uuid.uuid4()
    tenant = SimpleNamespace(organization_id=org, brand_id=brand, user_id="user_1", user_uuid=None)
    job = await service.run_generation(
        cast(AsyncSession, Session()),
        tenant=cast(TenantContext, tenant),
        mode="compare",
        task="image.generate",
        prompt="a red shoe sk-live-secret",
        model_ids=["gpt-image-1", "test-image"],
        aspect_ratio="1:1",
        resolution="standard",
    )
    assert job.status == "partial"
    assert [row["status"] for row in job.results] == ["succeeded", "failed"]
    assert job.results[0]["storage_key"].startswith(f"gateway/{brand}/{job.id}/gpt-image-1")
    assert job.results[1]["storage_key"] is None
    assert stored == [job.results[0]["storage_key"]]
    assert len(costs) == 1
    assert costs[0]["provider"] == "openai"
    assert "sk-live" not in str(job.results)
    assert "sk-live" not in str(audits)
    assert audits[0]["metadata"]["providers"] == ["openai", "openai"]
    assert "prompt" not in audits[0]["metadata"]


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried(monkeypatch):
    from aicmo.modules.creative.gateway import executor

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    get_settings.cache_clear()
    calls = {"n": 0}

    class Reject:
        async def generate(self, request):
            calls["n"] += 1
            raise RuntimeError("bad key sk-live-secret")

    monkeypatch.setattr(executor, "OpenAIImageGenProvider", lambda: Reject())
    model = next(item for item in catalog() if item.model_id == "gpt-image-1")
    with pytest.raises(GenerationError, match="rejected"):
        await executor.generate_image(model, prompt="shoe", aspect_ratio="1:1", resolution="standard")
    assert calls["n"] == 1


def test_studio_flag_blocks_gateway(monkeypatch):
    from fastapi import HTTPException

    from aicmo.modules.creative.gateway.router import _require_studio

    monkeypatch.setenv("STUDIO_ENABLED", "false")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as caught:
        _require_studio()
    assert caught.value.status_code == 409
