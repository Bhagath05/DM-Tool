"""LinkedIn Ads provider — Phase 10.2a stub."""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class LinkedInAdsProvider(StubProvider):
    slug = "linkedin_ads"
    display_name = "LinkedIn Ads"
    category = "ads"
    icon_id = "linkedin"
    description = (
        "B2B campaigns analysed alongside everything else. Track "
        "lead-form fills back to source."
    )
    scopes = ["r_ads", "r_ads_reporting", "r_organization_social"]


IntegrationRegistry.register(LinkedInAdsProvider())
