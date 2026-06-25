"""Stub provider base — fills in the abstract methods with explicit
`NotImplementedError` raisers so concrete stubs (meta_ads, google_ads,
etc.) only need to declare their static identity.

Phase 11 stops inheriting from `StubProvider` for whichever providers
get implemented and inherits directly from `IntegrationProvider`
instead — at which point the concrete `authorize_url`/`exchange_code`/
`refresh`/`fetch_account_info`/`sync` override the stub raisers.
"""

from __future__ import annotations

import uuid

from aicmo.modules.integrations.providers.base import (
    AccountInfo,
    IntegrationProvider,
    OAuthTokens,
    SyncResult,
)


class NotYetAvailable(NotImplementedError):
    """Raised by a stub provider's OAuth methods. The service layer
    catches this and returns a clean 501 with a founder-friendly
    message instead of a stacktrace."""


class StubProvider(IntegrationProvider):
    """Mix-in that makes a provider catalog-visible but un-connectable.

    Subclass + set the static identity attributes; you get a fully
    registered provider whose `available=False` and whose OAuth
    methods explain why they're not callable.
    """

    available = False

    async def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        raise NotYetAvailable(
            f"{self.display_name} OAuth is not implemented yet — "
            "the connector lights up in Phase 11."
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        raise NotYetAvailable(
            f"{self.display_name} OAuth is not implemented yet."
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        raise NotYetAvailable(
            f"{self.display_name} OAuth is not implemented yet."
        )

    async def fetch_account_info(self, access_token: str) -> AccountInfo:
        raise NotYetAvailable(
            f"{self.display_name} account discovery is not implemented yet."
        )

    async def sync(
        self,
        *,
        connection_id: uuid.UUID,
        access_token: str,
        external_account_id: str | None = None,
    ) -> SyncResult:
        raise NotYetAvailable(
            f"{self.display_name} sync is not implemented yet."
        )
