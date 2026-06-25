"""HubSpot provider — Phase 10.2a stub."""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class HubSpotProvider(StubProvider):
    slug = "hubspot"
    display_name = "HubSpot"
    category = "crm"
    icon_id = "hubspot"
    description = (
        "Pull contacts, deals, and lifecycle stages so the engine can "
        "attribute revenue back to creatives."
    )
    scopes = ["crm.objects.contacts.read", "crm.objects.deals.read"]


IntegrationRegistry.register(HubSpotProvider())
