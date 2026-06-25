"""Phase 10.2a — Stub providers must raise on OAuth methods.

These tests pin the contract that Phase 11 reads: until a concrete
implementation overrides the abstract methods, every OAuth/sync call
raises `NotYetAvailable`. That's what makes the framework safe to
ship without real connectors — the catalog renders, but you can't
accidentally call a half-built provider.
"""

from __future__ import annotations

import uuid

import pytest

from aicmo.modules.integrations.providers.stubs import (
    NotYetAvailable,
    StubProvider,
)
from aicmo.modules.integrations.registry import IntegrationRegistry


PHASE_10_2_SLUGS = [
    "meta_ads",
    "google_ads",
    "linkedin_ads",
    "tiktok_ads",
    "hubspot",
    "salesforce",
]


@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
def test_provider_has_required_static_identity(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    assert p.slug == slug
    assert p.display_name, "must have a display name"
    assert p.category in {"ads", "crm", "analytics"}
    assert p.icon_id, "must have an icon_id for the frontend"
    assert p.description, "must have founder-facing description copy"
    assert isinstance(p.scopes, list)


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
async def test_authorize_url_raises_not_yet_available(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    with pytest.raises(NotYetAvailable, match="Phase 11|not implemented"):
        await p.authorize_url(state="x", redirect_uri="http://x/cb")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
async def test_exchange_code_raises(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    with pytest.raises(NotYetAvailable):
        await p.exchange_code("code", "http://x/cb")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
async def test_refresh_raises(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    with pytest.raises(NotYetAvailable):
        await p.refresh("refresh-token")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
async def test_fetch_account_info_raises(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    with pytest.raises(NotYetAvailable):
        await p.fetch_account_info("access-token")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", PHASE_10_2_SLUGS)
async def test_sync_raises(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    with pytest.raises(NotYetAvailable):
        await p.sync(connection_id=uuid.uuid4(), access_token="x")


def test_info_projects_static_identity() -> None:
    """`provider.info()` returns the Pydantic ProviderInfo shape the
    catalog endpoint serialises — pin it stays in sync with the
    underlying attributes."""
    meta = IntegrationRegistry.get("meta_ads")
    info = meta.info()
    assert info.slug == "meta_ads"
    assert info.display_name == "Meta Ads"
    assert info.category == "ads"
    assert info.icon_id == "meta"
    assert info.available is False
    assert "ads_read" in info.scopes


def test_not_yet_available_is_a_not_implemented_error() -> None:
    """The service layer catches `NotImplementedError` to surface 501s.
    Pin the inheritance so a future refactor can't accidentally make
    `NotYetAvailable` a plain Exception."""
    assert issubclass(NotYetAvailable, NotImplementedError)
