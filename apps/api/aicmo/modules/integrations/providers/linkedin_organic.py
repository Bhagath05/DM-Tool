"""LinkedIn organic — OAuth, company page sync, and UGC posting."""

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

_AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_API_BASE = "https://api.linkedin.com"
_LINKEDIN_VERSION = "202401"
_SCOPES = "r_organization_social,w_organization_social"


class LinkedInOrganicProvider(IntegrationProvider):
    slug = "linkedin_organic"
    display_name = "LinkedIn"
    category = "social"  # type: ignore[assignment]
    icon_id = "linkedin"
    description = "Publish to your LinkedIn company page and sync engagement metrics."
    scopes = ["r_organization_social", "w_organization_social"]

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = getattr(settings, "linkedin_client_id", "") or ""
        self._client_secret = getattr(settings, "linkedin_client_secret", "") or ""

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
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": _SCOPES,
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
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
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
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    },
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
        org_id, org_name = await _resolve_primary_organization(access_token)
        return AccountInfo(
            external_account_id=org_id,
            external_account_name=org_name or "LinkedIn Organization",
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
        org_id = external_account_id
        if not org_id:
            org_id, _ = await _resolve_primary_organization(access_token)

        if not org_id:
            return SyncResult(
                rows_pulled=0,
                started_at=started,
                finished_at=datetime.now(UTC),
                error_message="No LinkedIn organization found for this account.",
            )

        metrics: dict[str, float] = {}
        raw: dict[str, dict] = {}
        headers = _api_headers(access_token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await with_retry(
                lambda: client.get(
                    f"{_API_BASE}/rest/organizationalEntityFollowerStatistics"
                    f"?q=organizationalEntity&organizationalEntity={org_id}",
                    headers=headers,
                )
            )
            if resp.status_code == 200:
                elements = resp.json().get("elements") or []
                if elements:
                    follower_counts = elements[0].get("followerCounts") or {}
                    organic = follower_counts.get("organicFollowerCount", 0)
                    metrics["followers"] = float(organic)
                    raw["followers"] = {"source": "linkedin_api"}

        finished = datetime.now(UTC)
        return SyncResult(
            rows_pulled=len(metrics),
            started_at=started,
            finished_at=finished,
            metrics=metrics,
            metric_raw=raw,
            period_end=finished,
        )


def _api_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": _LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


async def _resolve_primary_organization(access_token: str) -> tuple[str, str]:
    headers = _api_headers(access_token)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await with_retry(
            lambda: client.get(
                f"{_API_BASE}/rest/organizationAcls?q=roleAssignee&role=ADMINISTRATOR",
                headers=headers,
            )
        )
        resp.raise_for_status()
        elements = resp.json().get("elements") or []
        if not elements:
            return "", ""

        org_urn = elements[0].get("organization", "")
        org_id = org_urn if org_urn.startswith("urn:") else f"urn:li:organization:{org_urn}"

        name_resp = await client.get(
            f"{_API_BASE}/rest/organizations/{org_id.split(':')[-1]}",
            headers=headers,
        )
        org_name = ""
        if name_resp.status_code == 200:
            org_name = name_resp.json().get("localizedName", "")
        return org_id, org_name
