"""Salesforce provider — Phase 10.2a stub."""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class SalesforceProvider(StubProvider):
    slug = "salesforce"
    display_name = "Salesforce"
    category = "crm"
    icon_id = "salesforce"
    description = (
        "Closed-won revenue feeds the engine's ROAS calculation — "
        "the closest thing to the real number."
    )
    scopes = ["api", "refresh_token"]


IntegrationRegistry.register(SalesforceProvider())
