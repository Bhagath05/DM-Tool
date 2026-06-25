"""Organic platform connectors — OAuth + metrics sync."""

from __future__ import annotations

from aicmo.modules.integrations.providers.facebook_pages import FacebookPagesProvider
from aicmo.modules.integrations.providers.google_business_profile import (
    GoogleBusinessProfileProvider,
)
from aicmo.modules.integrations.providers.linkedin_organic import LinkedInOrganicProvider
from aicmo.modules.integrations.providers.pinterest import PinterestProvider
from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.providers.youtube import YouTubeProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class InstagramOrganicProvider(StubProvider):
    """Instagram OAuth lives in the Social module — this catalog entry
    surfaces metrics when bridged from social_connections sync."""

    slug = "instagram_organic"
    display_name = "Instagram"
    category = "social"  # type: ignore[assignment]
    icon_id = "instagram"
    description = "Sync Instagram reach, impressions, and engagement metrics."
    scopes = ["instagram_basic", "instagram_manage_insights"]


IntegrationRegistry.register(InstagramOrganicProvider())
IntegrationRegistry.register(FacebookPagesProvider())
IntegrationRegistry.register(GoogleBusinessProfileProvider())
IntegrationRegistry.register(LinkedInOrganicProvider())
IntegrationRegistry.register(YouTubeProvider())
IntegrationRegistry.register(PinterestProvider())
