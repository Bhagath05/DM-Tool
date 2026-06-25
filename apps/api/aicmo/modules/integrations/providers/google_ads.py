"""Google Ads provider — Phase 10.2a stub."""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class GoogleAdsProvider(StubProvider):
    slug = "google_ads"
    display_name = "Google Ads"
    category = "ads"
    icon_id = "google"
    description = (
        "Search, Display, YouTube — see what's winning across the "
        "Google network with one connection."
    )
    scopes = ["https://www.googleapis.com/auth/adwords"]


IntegrationRegistry.register(GoogleAdsProvider())
