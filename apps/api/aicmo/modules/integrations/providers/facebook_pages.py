"""Facebook Pages — OAuth, sync, and publish via Graph API."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
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

_GRAPH_VERSION = "v18.0"
_AUTHORIZE_URL = f"https://www.facebook.com/{_GRAPH_VERSION}/dialog/oauth"
_TOKEN_URL = f"https://graph.facebook.com/{_GRAPH_VERSION}/oauth/access_token"
_GRAPH_BASE = f"https://graph.facebook.com/{_GRAPH_VERSION}"
_SCOPES = ",".join(
    [
        "pages_manage_posts",
        "pages_read_engagement",
        "pages_show_list",
        "pages_manage_metadata",
    ]
)


class FacebookPagesProvider(IntegrationProvider):
    slug = "facebook_pages"
    display_name = "Facebook"
    category = "social"  # type: ignore[assignment]
    icon_id = "facebook"
    description = "Connect a Facebook Page to publish posts and sync engagement."
    scopes = [
        "pages_manage_posts",
        "pages_read_engagement",
        "pages_show_list",
    ]

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = (
            getattr(settings, "fb_client_id", "") or settings.ig_client_id or ""
        )
        self._client_secret = (
            getattr(settings, "fb_client_secret", "") or settings.ig_client_secret or ""
        )

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
            "scope": _SCOPES,
            "response_type": "code",
            "state": state,
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=30.0) as client:
            short_resp = await with_retry(
                lambda: client.get(
                    _TOKEN_URL,
                    params={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                )
            )
            short_resp.raise_for_status()
            short_token = short_resp.json()["access_token"]

            long_resp = await with_retry(
                lambda: client.get(
                    _TOKEN_URL,
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "fb_exchange_token": short_token,
                    },
                )
            )
            long_resp.raise_for_status()
            payload = long_resp.json()

        expires_in = int(payload.get("expires_in", 60 * 24 * 60 * 60))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=None,
            expires_at=expires_at,
            raw_response=json.dumps(payload),
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        raise RuntimeError(
            "Facebook long-lived tokens must be refreshed via token exchange — reconnect."
        )

    async def fetch_account_info(self, access_token: str) -> AccountInfo:
        page_id, page_name, page_token = await _resolve_primary_page(access_token)
        return AccountInfo(
            external_account_id=page_id,
            external_account_name=page_name or "Facebook Page",
            scopes_granted=list(self.scopes),
        )

    async def sync(
        self,
        *,
        connection_id: uuid.UUID,
        access_token: str,
        external_account_id: str | None = None,
    ) -> SyncResult:
        started = datetime.now(UTC)
        page_id = external_account_id
        page_token = access_token
        if not page_id:
            page_id, _, page_token = await _resolve_primary_page(access_token)

        if not page_id:
            return SyncResult(
                rows_pulled=0,
                started_at=started,
                finished_at=datetime.now(UTC),
                error_message="No Facebook Page found — link a Page to your account.",
            )

        metrics: dict[str, float] = {}
        raw: dict[str, dict] = {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.get(
                    f"{_GRAPH_BASE}/{page_id}",
                    params={
                        "access_token": page_token,
                        "fields": "fan_count,followers_count,name",
                    },
                )
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("fan_count") is not None:
                    metrics["page_fans"] = float(data["fan_count"])
                    raw["page_fans"] = {"source": "graph_api"}
                if data.get("followers_count") is not None:
                    metrics["page_followers"] = float(data["followers_count"])
                    raw["page_followers"] = {"source": "graph_api"}

            insights_resp = await with_retry(
                lambda: client.get(
                    f"{_GRAPH_BASE}/{page_id}/insights",
                    params={
                        "access_token": page_token,
                        "metric": "page_impressions,page_engaged_users",
                        "period": "days_28",
                    },
                )
            )
            if insights_resp.status_code == 200:
                for entry in insights_resp.json().get("data", []):
                    name = entry.get("name")
                    values = entry.get("values") or [{}]
                    val = values[0].get("value") if values else 0
                    if name == "page_impressions":
                        metrics["impressions_28d"] = float(val or 0)
                        raw["impressions_28d"] = {"period": "days_28"}
                    elif name == "page_engaged_users":
                        metrics["engaged_users_28d"] = float(val or 0)
                        raw["engaged_users_28d"] = {"period": "days_28"}

        finished = datetime.now(UTC)
        return SyncResult(
            rows_pulled=len(metrics),
            started_at=started,
            finished_at=finished,
            metrics=metrics,
            metric_raw=raw,
            period_end=finished,
        )


async def _resolve_primary_page(
    access_token: str,
) -> tuple[str, str, str]:
    """Return (page_id, page_name, page_access_token)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await with_retry(
            lambda: client.get(
                f"{_GRAPH_BASE}/me/accounts",
                params={
                    "access_token": access_token,
                    "fields": "id,name,access_token",
                },
            )
        )
        resp.raise_for_status()
        pages = resp.json().get("data", [])
        if not pages:
            return "", "", access_token
        page = pages[0]
        return (
            str(page.get("id", "")),
            str(page.get("name", "")),
            str(page.get("access_token") or access_token),
        )


async def get_page_access_token(user_access_token: str, page_id: str) -> str:
    """Resolve page-scoped token for publishing."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{_GRAPH_BASE}/me/accounts",
            params={
                "access_token": user_access_token,
                "fields": "id,access_token",
            },
        )
        resp.raise_for_status()
        for page in resp.json().get("data", []):
            if str(page.get("id")) == str(page_id):
                return str(page.get("access_token") or user_access_token)
    return user_access_token
