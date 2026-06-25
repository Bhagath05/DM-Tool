"""Read-only social provider abstract base.

Three methods per provider:
- `init_oauth()`  → URL to redirect the user to
- `complete_oauth(code, ...)` → exchange code for tokens + metadata
- `sync(connection)` → pull recent assets + perf signals

Providers must be safe to construct even when no credentials are
configured (so the rest of the system imports fine in dev environments).
The `available()` method tells the registry whether to expose this
provider in the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OAuthInitResult:
    """What `init_oauth` returns. The router redirects the user to
    `authorize_url`; `state` is stored server-side keyed to the user so
    we can verify the callback came from a flow we started."""

    authorize_url: str
    state: str


@dataclass
class OAuthCallbackResult:
    """What `complete_oauth` returns. Caller persists onto SocialConnection."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    metadata: dict


@dataclass
class SyncedAsset:
    """One ingested post + its latest performance snapshot."""

    platform_post_id: str
    asset_type: str
    caption: str | None = None
    thumbnail_url: str | None = None
    permalink: str | None = None
    hashtags: list[str] = field(default_factory=list)
    posted_at: datetime | None = None

    # Performance snapshot (flat — same fields as PerformanceSignal cols)
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments_count: int = 0
    saves: int = 0
    shares: int = 0
    views: int = 0
    watch_time_seconds: float = 0.0
    ctr: float = 0.0

    raw_asset_json: dict = field(default_factory=dict)
    raw_signal_json: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    assets: list[SyncedAsset]
    synced_at: datetime
    account_metrics: dict = field(default_factory=dict)


class SocialProvider(ABC):
    """One concrete subclass per platform."""

    #: Stable identifier — also the value persisted on SocialConnection.platform.
    name: str
    #: Human-readable name for the UI ("Instagram", "LinkedIn", …).
    display_name: str

    # ----- availability -----

    @abstractmethod
    def available(self) -> bool:
        """True when the OAuth credentials this provider needs are configured.
        When False, the UI shows a "Coming soon — needs config" state, and
        the manual-import path remains the workable alternative."""

    # ----- OAuth -----

    @abstractmethod
    def init_oauth(self, *, user_id: str, redirect_uri: str) -> OAuthInitResult: ...

    @abstractmethod
    async def complete_oauth(
        self, *, code: str, redirect_uri: str
    ) -> OAuthCallbackResult: ...

    # ----- read-only sync -----

    @abstractmethod
    async def sync(
        self, *, access_token: str, metadata: dict, limit: int = 25
    ) -> SyncResult: ...
