"""YouTube channel — OAuth, channel metrics sync, video publishing."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import structlog

from aicmo.config import get_settings
from aicmo.modules.integrations.http_retry import with_retry
from aicmo.modules.integrations.providers.base import (
    AccountInfo,
    IntegrationProvider,
    OAuthTokens,
    SyncResult,
)

log = structlog.get_logger()

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
_SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"


class YouTubeProvider(IntegrationProvider):
    slug = "youtube"
    display_name = "YouTube"
    category = "social"  # type: ignore[assignment]
    icon_id = "youtube"
    description = "Connect your YouTube channel to publish videos and sync channel stats."
    scopes = ["youtube.upload", "youtube.readonly"]

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = getattr(settings, "youtube_client_id", "") or ""
        self._client_secret = getattr(settings, "youtube_client_secret", "") or ""

    def _credentials_configured(self) -> bool:
        return bool(
            self._client_id
            and self._client_secret
            and not self._client_id.endswith("replace_me")
        )

    def info(self):
        from aicmo.modules.integrations.schemas import ProviderInfo

        return ProviderInfo(
            slug=self.slug,
            display_name=self.display_name,
            category=self.category,  # type: ignore[arg-type]
            icon_id=self.icon_id,
            description=self.description,
            scopes=list(self.scopes),
            available=self._credentials_configured(),
        )

    async def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.post(
                    _TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
            )
            resp.raise_for_status()
            payload = resp.json()

        expires_in = int(payload.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=expires_at,
            raw_response=json.dumps(payload),
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            )
            resp.raise_for_status()
            payload = resp.json()

        expires_in = int(payload.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or refresh_token,
            expires_at=expires_at,
            raw_response=json.dumps(payload),
        )

    async def fetch_account_info(self, access_token: str) -> AccountInfo:
        channel_id, title = await _resolve_primary_channel(access_token)
        return AccountInfo(
            external_account_id=channel_id,
            external_account_name=title or "YouTube Channel",
            scopes_granted=[_SCOPE],
        )

    async def sync(
        self,
        *,
        connection_id: uuid.UUID,
        access_token: str,
        external_account_id: str | None = None,
    ) -> SyncResult:
        started = datetime.now(UTC)
        channel_id = external_account_id
        if not channel_id:
            channel_id, _ = await _resolve_primary_channel(access_token)

        if not channel_id:
            return SyncResult(
                rows_pulled=0,
                started_at=started,
                finished_at=datetime.now(UTC),
                error_message="No YouTube channel found for this Google account.",
            )

        metrics: dict[str, float] = {}
        raw: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.get(
                    f"{_YOUTUBE_API}/channels",
                    params={
                        "part": "statistics",
                        "id": channel_id,
                    },
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            )
            if resp.status_code == 200:
                items = resp.json().get("items") or []
                if items:
                    stats = items[0].get("statistics") or {}
                    for key in ("viewCount", "subscriberCount", "videoCount"):
                        if stats.get(key) is not None:
                            metric_key = key.replace("Count", "").lower() + "s"
                            if key == "viewCount":
                                metric_key = "views"
                            elif key == "subscriberCount":
                                metric_key = "subscribers"
                            elif key == "videoCount":
                                metric_key = "videos"
                            metrics[metric_key] = float(stats[key])
                            raw[metric_key] = {"source": "youtube_data_api"}

        finished = datetime.now(UTC)
        return SyncResult(
            rows_pulled=len(metrics),
            started_at=started,
            finished_at=finished,
            metrics=metrics,
            metric_raw=raw,
            period_end=finished,
        )


async def _resolve_primary_channel(access_token: str) -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await with_retry(
            lambda: client.get(
                f"{_YOUTUBE_API}/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            return "", ""
        ch = items[0]
        return ch.get("id", ""), ch.get("snippet", {}).get("title", "")
