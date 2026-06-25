"""Instagram Graph API provider — read-only.

Wires the real OAuth + Graph API endpoints. Gated on `IG_CLIENT_ID` /
`IG_CLIENT_SECRET` in env — when those are missing, `available()` returns
False and the UI politely tells the user to configure their Facebook App
before OAuth can complete. The rest of the system (manual import, analyzer,
context inheritance) keeps working regardless.

For Phase 1-A we DO NOT implement automatic background sync. The user
clicks "Sync now" and we pull on demand.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from aicmo.config import get_settings
from aicmo.providers.social.base import (
    OAuthCallbackResult,
    OAuthInitResult,
    SocialProvider,
    SyncedAsset,
    SyncResult,
)

log = structlog.get_logger()

_AUTHORIZE_URL = "https://www.facebook.com/v18.0/dialog/oauth"
_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
_GRAPH_BASE = "https://graph.facebook.com/v18.0"

#: Scopes for reading Instagram Business / Creator accounts.
#: Each requires Facebook App Review for production.
_SCOPES = ",".join(
    [
        "instagram_basic",
        "instagram_manage_insights",
        "pages_show_list",
        "pages_read_engagement",
    ]
)


class InstagramProvider(SocialProvider):
    name = "instagram"
    display_name = "Instagram"

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = getattr(settings, "ig_client_id", "") or ""
        self._client_secret = getattr(settings, "ig_client_secret", "") or ""

    # ----- availability -----

    def available(self) -> bool:
        return bool(
            self._client_id
            and self._client_secret
            and not self._client_id.endswith("replace_me")
        )

    # ----- OAuth -----

    def init_oauth(
        self, *, user_id: str, redirect_uri: str
    ) -> OAuthInitResult:
        # Random state — caller stores keyed to user_id so the callback
        # can verify it came from a flow we initiated.
        state = secrets.token_urlsafe(24)
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": _SCOPES,
            "response_type": "code",
            "state": state,
        }
        return OAuthInitResult(
            authorize_url=f"{_AUTHORIZE_URL}?{urlencode(params)}",
            state=state,
        )

    async def complete_oauth(
        self, *, code: str, redirect_uri: str
    ) -> OAuthCallbackResult:
        # 1) Exchange short-lived code for short-lived token.
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                _TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            short = resp.json()
            short_token = short["access_token"]

            # 2) Upgrade to a long-lived (60 day) token.
            resp = await client.get(
                _TOKEN_URL,
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "fb_exchange_token": short_token,
                },
            )
            resp.raise_for_status()
            long_payload = resp.json()
            long_token = long_payload["access_token"]
            expires_in = long_payload.get("expires_in", 60 * 24 * 60 * 60)

            # 3) Find the user's first Facebook Page that has an IG
            # Business account linked. We store its IG account id in
            # `metadata` so subsequent syncs can target it directly.
            pages_resp = await client.get(
                f"{_GRAPH_BASE}/me/accounts",
                params={
                    "access_token": long_token,
                    "fields": "id,name,instagram_business_account",
                },
            )
            pages_resp.raise_for_status()
            pages = pages_resp.json().get("data", [])

            ig_account_id = None
            page_name = None
            for p in pages:
                ig = p.get("instagram_business_account")
                if ig and ig.get("id"):
                    ig_account_id = ig["id"]
                    page_name = p.get("name")
                    break

            metadata: dict[str, Any] = {
                "ig_business_account_id": ig_account_id,
                "page_name": page_name,
                "scopes": _SCOPES,
            }

        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        return OAuthCallbackResult(
            access_token=long_token,
            refresh_token=None,  # IG long-lived tokens are 60d; refresh is a separate call
            expires_at=expires_at,
            metadata=metadata,
        )

    # ----- sync -----

    async def sync(
        self, *, access_token: str, metadata: dict, limit: int = 25
    ) -> SyncResult:
        ig_id = metadata.get("ig_business_account_id")
        if not ig_id:
            raise RuntimeError(
                "Instagram Business Account ID missing — reconnect Instagram to fix."
            )

        fields = ",".join(
            [
                "id",
                "media_type",
                "media_product_type",
                "caption",
                "permalink",
                "thumbnail_url",
                "media_url",
                "timestamp",
                "like_count",
                "comments_count",
                # Insights are a separate field expansion.
                "insights.metric(impressions,reach,saved,shares,plays,total_interactions)",
            ]
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Account-level metrics (followers, profile views)
            account_metrics: dict[str, int | float] = {}
            acct_resp = await client.get(
                f"{_GRAPH_BASE}/{ig_id}",
                params={
                    "access_token": access_token,
                    "fields": "followers_count,media_count,username",
                },
            )
            if acct_resp.status_code == 200:
                acct = acct_resp.json()
                account_metrics["followers"] = int(acct.get("followers_count", 0) or 0)
                account_metrics["media_count"] = int(acct.get("media_count", 0) or 0)

            insights_resp = await client.get(
                f"{_GRAPH_BASE}/{ig_id}/insights",
                params={
                    "access_token": access_token,
                    "metric": "reach,accounts_engaged",
                    "period": "days_28",
                },
            )
            if insights_resp.status_code == 200:
                for entry in insights_resp.json().get("data", []):
                    name = entry.get("name")
                    values = entry.get("values") or [{}]
                    val = values[0].get("value") if values else 0
                    if name:
                        account_metrics[name] = int(val or 0)

            resp = await client.get(
                f"{_GRAPH_BASE}/{ig_id}/media",
                params={
                    "access_token": access_token,
                    "fields": fields,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        items = payload.get("data", [])
        synced: list[SyncedAsset] = []
        for raw in items:
            ig_media_type = raw.get("media_type", "").upper()
            media_product_type = raw.get("media_product_type", "").upper()
            asset_type = _map_asset_type(ig_media_type, media_product_type)

            insights = _flatten_insights(raw.get("insights", {}))
            impressions = int(insights.get("impressions", 0) or 0)
            reach = int(insights.get("reach", 0) or 0)
            views = int(insights.get("plays", 0) or 0)
            saves = int(insights.get("saved", 0) or 0)
            shares = int(insights.get("shares", 0) or 0)
            likes = int(raw.get("like_count", 0) or 0)
            comments = int(raw.get("comments_count", 0) or 0)
            engagement = likes + comments + saves + shares
            denom = max(impressions or reach or views or 1, 1)
            engagement_rate = round(engagement / denom, 4)

            posted_at: datetime | None = None
            ts = raw.get("timestamp")
            if isinstance(ts, str):
                try:
                    posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    posted_at = None

            synced.append(
                SyncedAsset(
                    platform_post_id=str(raw["id"]),
                    asset_type=asset_type,
                    caption=raw.get("caption"),
                    thumbnail_url=raw.get("thumbnail_url")
                    or raw.get("media_url"),
                    permalink=raw.get("permalink"),
                    hashtags=_extract_hashtags(raw.get("caption") or ""),
                    posted_at=posted_at,
                    impressions=impressions,
                    reach=reach,
                    likes=likes,
                    comments_count=comments,
                    saves=saves,
                    shares=shares,
                    views=views,
                    watch_time_seconds=0.0,
                    ctr=0.0,
                    raw_asset_json=raw,
                    raw_signal_json=raw.get("insights") or {},
                )
            )

        return SyncResult(
            assets=synced,
            synced_at=datetime.now(UTC),
            account_metrics=account_metrics,
        )


# ----- helpers --------------------------------------------------------


def _map_asset_type(media_type: str, product_type: str) -> str:
    if product_type == "REELS":
        return "reel"
    if product_type == "STORY":
        return "story"
    if media_type == "VIDEO":
        return "video"
    if media_type == "CAROUSEL_ALBUM":
        return "carousel"
    return "image"


def _flatten_insights(insights: dict) -> dict[str, Any]:
    """Graph API returns insights as `{ data: [ { name, values: [{value}]} ] }`.
    Flatten to `{ metric_name: value }`."""
    out: dict[str, Any] = {}
    for entry in (insights or {}).get("data", []):
        name = entry.get("name")
        values = entry.get("values") or [{}]
        v = values[0].get("value") if values else None
        if name is not None:
            out[name] = v
    return out


_HASHTAG_RE = None  # lazy compile


def _extract_hashtags(caption: str) -> list[str]:
    global _HASHTAG_RE
    if _HASHTAG_RE is None:
        import re

        _HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
    return [m.group(1) for m in _HASHTAG_RE.finditer(caption)]
