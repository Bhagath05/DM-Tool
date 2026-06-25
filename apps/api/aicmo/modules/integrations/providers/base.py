"""Abstract base class for an integration provider.

A provider knows:
  - Its static identity (slug, display name, category, scopes, icon).
  - How to start an OAuth dance (authorize_url).
  - How to exchange a callback code for tokens.
  - How to refresh tokens.
  - How to read its own account info (for nice display).
  - How to perform a sync (pull data, returning a SyncResult).

Phase 10.2a ships six providers that fill in the static identity but
raise `NotImplementedError` on the OAuth/sync methods. Phase 11 (and
later) implements the methods on real providers without touching the
framework or the database.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from aicmo.modules.integrations.schemas import (
    ProviderCategory,
    ProviderInfo,
)


# ---------------------------------------------------------------------
#  DTOs used by the provider methods. Plain dataclasses (not Pydantic)
#  because these are internal — they never cross the API boundary.
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthTokens:
    """Result of an OAuth code exchange or refresh. Tokens are
    plaintext here — the service layer encrypts them before persisting."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    raw_response: str | None = None  # JSON-encoded provider response


@dataclass(frozen=True)
class AccountInfo:
    """What we learn about the connected account after OAuth completes.
    Stored on the connection row so the founder sees a real name
    instead of an opaque id."""

    external_account_id: str
    external_account_name: str
    scopes_granted: list[str]


@dataclass(frozen=True)
class SyncResult:
    """Outcome of a single sync run."""

    rows_pulled: int
    started_at: datetime
    finished_at: datetime
    error_message: str | None = None
    metrics: dict[str, float] | None = None
    metric_raw: dict[str, dict] | None = None
    period_end: datetime | None = None


# ---------------------------------------------------------------------
#  Provider abstract base
# ---------------------------------------------------------------------


class IntegrationProvider(ABC):
    """One implementation per third-party platform we connect to.

    Concrete providers MUST set the class-level identity attributes
    (slug, display_name, category, icon_id, description) and implement
    the four abstract methods. Phase 10.2a's stub providers inherit
    from `StubProvider` (in stubs.py) which fills in the abstract
    methods with `NotImplementedError` raisers — that way the catalog
    endpoint works today and Phase 11 only needs to override the
    methods on `MetaAdsProvider`.
    """

    # ---- Static identity (must be overridden) ----
    slug: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    category: ClassVar[ProviderCategory] = "ads"
    icon_id: ClassVar[str] = ""  # frontend maps to inline SVG
    description: ClassVar[str] = ""
    scopes: ClassVar[list[str]] = []
    # `available` flips to True when the OAuth methods are
    # implemented. Stubs keep it False and the catalog surfaces them
    # as "Coming soon".
    available: ClassVar[bool] = False

    # ---- OAuth flow ----

    @abstractmethod
    async def authorize_url(
        self,
        *,
        state: str,
        redirect_uri: str,
    ) -> str:
        """Build the OAuth authorize URL the founder is redirected to.
        `state` is a signed token the service generates per attempt;
        the callback handler verifies it."""

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """Exchange an OAuth callback code for tokens."""

    @abstractmethod
    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Refresh an access token using the stored refresh token.
        Provider should raise if the refresh token itself has expired —
        the service then flips the connection to EXPIRED."""

    @abstractmethod
    async def fetch_account_info(self, access_token: str) -> AccountInfo:
        """Read the connected account's identity from the platform.
        Called once after `exchange_code` so we can render a friendly
        name on the connection row."""

    # ---- Data sync ----

    @abstractmethod
    async def sync(
        self,
        *,
        connection_id: uuid.UUID,
        access_token: str,
        external_account_id: str | None = None,
    ) -> SyncResult:
        """Pull whatever this provider pulls. Concrete implementation
        decides what `rows_pulled` means — for an ad platform it's
        performance events; for a CRM it's deals; for analytics it
        might be sessions. The service layer doesn't care."""

    # ---- Derived helpers — not abstract ----

    def info(self) -> ProviderInfo:
        """Project the static identity into the API-shaped schema."""
        return ProviderInfo(
            slug=self.slug,
            display_name=self.display_name,
            category=self.category,
            icon_id=self.icon_id,
            description=self.description,
            scopes=list(self.scopes),
            available=self.available,
        )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<{self.__class__.__name__} slug={self.slug!r} available={self.available}>"
