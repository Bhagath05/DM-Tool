"""Phase 6.3 (Gap A) — AI image generation persists the FULL metadata contract.

Spec #2: every generation must persist prompt / negative_prompt / aspect /
style / dimensions / seed / provider / model / cost / time. Runs against the
offline stub provider (no key, no spend) with an in-memory fake session so the
persistence contract is asserted without a DB.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from aicmo.modules.creative.design import image_providers
from aicmo.modules.creative.design import service as design_service
from aicmo.modules.creative.design.models import BrandAsset
from aicmo.modules.creative.models import CreativeCostEvent


@pytest.fixture(autouse=True)
def _force_stub_provider(monkeypatch):
    """Hermetic: never hit a real image provider (no key needed, no spend, no
    latency) regardless of whether OPENAI_API_KEY is set in the environment."""
    monkeypatch.setattr(
        image_providers, "get_image_gen_provider",
        lambda: image_providers.StubImageGenProvider(),
    )

_TENANT = SimpleNamespace(
    organization_id=uuid.uuid4(),
    brand_id=uuid.uuid4(),
    user_id="u-1",
)

_CONTRACT_FIELDS = {
    "prompt", "negative_prompt", "aspect_ratio", "style", "width", "height",
    "seed", "provider", "model", "generation_cost_cents", "generation_time_ms",
}


class _FakeSession:
    def __init__(self):
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


def test_generate_image_asset_persists_full_contract_and_cost_event():
    session = _FakeSession()
    asset = asyncio.run(
        design_service.generate_image_asset(
            session, tenant=_TENANT, prompt="a friendly barista",
            aspect="4:5", negative_prompt="blurry", style="photographic", seed=42,
        )
    )

    # a brand_asset image + a cost event were staged
    assets = [o for o in session.added if isinstance(o, BrandAsset)]
    events = [o for o in session.added if isinstance(o, CreativeCostEvent)]
    assert len(assets) == 1 and assets[0] is asset
    assert asset.kind == "image"

    gen = asset.meta["generation"]
    assert _CONTRACT_FIELDS <= set(gen), f"missing: {_CONTRACT_FIELDS - set(gen)}"
    assert gen["prompt"] == "a friendly barista"
    assert gen["negative_prompt"] == "blurry"
    assert gen["aspect_ratio"] == "4:5"
    assert gen["style"] == "photographic"
    assert gen["seed"] == 42
    assert gen["provider"] == "stub"  # offline default (no key)
    assert gen["model"] == "stub"

    assert len(events) == 1
    ev = events[0]
    assert ev.stage == "image_generate"
    assert ev.provider == "stub"
    assert ev.organization_id == _TENANT.organization_id
    assert ev.brand_id == _TENANT.brand_id


def test_generation_is_tenant_scoped():
    session = _FakeSession()
    asset = asyncio.run(
        design_service.generate_image_asset(
            session, tenant=_TENANT, prompt="x",
        )
    )
    assert asset.organization_id == _TENANT.organization_id
    assert asset.brand_id == _TENANT.brand_id
