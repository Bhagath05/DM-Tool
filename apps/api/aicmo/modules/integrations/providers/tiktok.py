"""TikTok Ads provider — Phase 10.2a stub."""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class TikTokAdsProvider(StubProvider):
    slug = "tiktok_ads"
    display_name = "TikTok Ads"
    category = "ads"
    icon_id = "tiktok"
    description = (
        "Spark Ads, video formats, creative trends — we'll surface "
        "what's working for your audience."
    )
    scopes = ["user.info.basic", "ad.read"]


IntegrationRegistry.register(TikTokAdsProvider())
