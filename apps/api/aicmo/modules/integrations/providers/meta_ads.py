"""Meta Ads provider — Phase 10.2a stub.

Phase 11 promotes this from StubProvider to IntegrationProvider and
implements:
  - authorize_url    (Facebook Login dialog URL with `ads_read` scope)
  - exchange_code    (POST /oauth/access_token, then exchange short-
                      lived token for a long-lived one)
  - refresh          (Meta long-lived tokens last ~60 days; we re-mint
                      via /oauth/access_token before expiry)
  - fetch_account_info (GET /me/adaccounts to surface the friendly name)
  - sync             (GET /act_{id}/insights, normalise into our
                      `performance_events` shape and feed the existing
                      Phase 9.1 ingest path)
"""

from __future__ import annotations

from aicmo.modules.integrations.providers.stubs import StubProvider
from aicmo.modules.integrations.registry import IntegrationRegistry


class MetaAdsProvider(StubProvider):
    slug = "meta_ads"
    display_name = "Meta Ads"
    category = "ads"
    icon_id = "meta"
    description = (
        "Pull Facebook + Instagram ad performance directly. No CSV "
        "uploads, no manual exports."
    )
    scopes = ["ads_read", "business_management", "pages_read_engagement"]


IntegrationRegistry.register(MetaAdsProvider())
