"""Tests for production-ready organic platform providers."""

from __future__ import annotations

import pytest

import aicmo.modules.integrations.providers  # noqa: F401 — register providers
from aicmo.modules.integrations.registry import IntegrationRegistry


ORGANIC_SLUGS = [
    "facebook_pages",
    "linkedin_organic",
    "youtube",
    "pinterest",
    "google_business_profile",
]


@pytest.mark.parametrize("slug", ORGANIC_SLUGS)
def test_organic_provider_has_identity(slug: str) -> None:
    p = IntegrationRegistry.get(slug)
    assert p.slug == slug
    assert p.display_name
    assert p.category == "social" or slug == "google_business_profile"
    assert p.icon_id
    assert p.description
    assert isinstance(p.scopes, list)


@pytest.mark.parametrize("slug", ORGANIC_SLUGS)
def test_organic_provider_info_shape(slug: str) -> None:
    info = IntegrationRegistry.get(slug).info()
    assert info.slug == slug
    assert isinstance(info.available, bool)
    assert len(info.scopes) >= 1


def test_facebook_provider_not_stub() -> None:
    p = IntegrationRegistry.get("facebook_pages")
    assert p.__class__.__name__ == "FacebookPagesProvider"


def test_linkedin_provider_not_stub() -> None:
    p = IntegrationRegistry.get("linkedin_organic")
    assert p.__class__.__name__ == "LinkedInOrganicProvider"


def test_youtube_provider_registered() -> None:
    p = IntegrationRegistry.get("youtube")
    assert p.__class__.__name__ == "YouTubeProvider"


def test_pinterest_provider_registered() -> None:
    p = IntegrationRegistry.get("pinterest")
    assert p.__class__.__name__ == "PinterestProvider"
