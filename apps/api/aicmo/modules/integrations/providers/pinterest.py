"""Pinterest — OAuth, board sync, and pin publishing."""

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

_AUTHORIZE_URL = "https://www.pinterest.com/oauth/"
_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
_API_BASE = "https://api.pinterest.com/v5"
_SCOPES = "boards:read,pins:read,pins:write,user_accounts:read"


class PinterestProvider(IntegrationProvider):
    slug = "pinterest"
    display_name = "Pinterest"
    category = "social"  # type: ignore[assignment]
    icon_id = "pinterest"
    description = "Publish pins to your Pinterest boards and sync account metrics."
    scopes = ["boards:read", "pins:read", "pins:write", "user_accounts:read"]

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = getattr(settings, "pinterest_app_id", "") or ""
        self._client_secret = getattr(settings, "pinterest_app_secret", "") or ""

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
            "scope": _SCOPES,
            "state": state,
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                    },
                    auth=(self._client_id, self._client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
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
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    auth=(self._client_id, self._client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
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
        board_id, board_name, username = await _resolve_primary_board(access_token)
        display = board_name or username or "Pinterest"
        return AccountInfo(
            external_account_id=board_id or username,
            external_account_name=display,
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
        metrics: dict[str, float] = {}
        raw: dict[str, dict] = {}
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            acct_resp = await with_retry(
                lambda: client.get(f"{_API_BASE}/user_account", headers=headers)
            )
            if acct_resp.status_code == 200:
                data = acct_resp.json()
                if data.get("follower_count") is not None:
                    metrics["followers"] = float(data["follower_count"])
                    raw["followers"] = {"source": "pinterest_api"}
                if data.get("following_count") is not None:
                    metrics["following"] = float(data["following_count"])
                    raw["following"] = {"source": "pinterest_api"}

            pins_resp = await with_retry(
                lambda: client.get(
                    f"{_API_BASE}/pins",
                    headers=headers,
                    params={"page_size": 1},
                )
            )
            if pins_resp.status_code == 200:
                items = pins_resp.json().get("items") or []
                metrics["pins_sampled"] = float(len(items))
                raw["pins_sampled"] = {"source": "pinterest_api"}

        finished = datetime.now(UTC)
        return SyncResult(
            rows_pulled=len(metrics),
            started_at=started,
            finished_at=finished,
            metrics=metrics,
            metric_raw=raw,
            period_end=finished,
        )


async def _resolve_primary_board(access_token: str) -> tuple[str, str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    username = ""
    async with httpx.AsyncClient(timeout=30.0) as client:
        acct_resp = await client.get(f"{_API_BASE}/user_account", headers=headers)
        if acct_resp.status_code == 200:
            username = acct_resp.json().get("username", "")

        boards_resp = await with_retry(
            lambda: client.get(
                f"{_API_BASE}/boards",
                headers=headers,
                params={"page_size": 5},
            )
        )
        if boards_resp.status_code == 200:
            items = boards_resp.json().get("items") or []
            if items:
                board = items[0]
                return board.get("id", ""), board.get("name", ""), username
    return "", "", username
