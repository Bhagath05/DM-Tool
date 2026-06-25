"""Google Business Profile — OAuth + real metrics sync.

Pulls location performance (views, calls, directions, website clicks)
and review summary from Google's Business Profile APIs. No placeholder
data — if the API returns nothing or credentials are missing, sync
reports zero rows and surfaces the error.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from aicmo.config import get_settings
from aicmo.modules.integrations.providers.base import (
    AccountInfo,
    IntegrationProvider,
    OAuthTokens,
    SyncResult,
)

log = structlog.get_logger()

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/business.manage"

_ACCOUNTS_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
_LOCATIONS_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
_PERFORMANCE_BASE = "https://businessprofileperformance.googleapis.com/v1"
_REVIEWS_BASE = "https://mybusiness.googleapis.com/v4"

# Performance API daily metric enums → connector_metrics keys
_DAILY_METRICS: list[tuple[str, str]] = [
    ("BUSINESS_IMPRESSIONS_DESKTOP_MAPS", "profile_views_maps_desktop"),
    ("BUSINESS_IMPRESSIONS_MOBILE_MAPS", "profile_views_maps_mobile"),
    ("BUSINESS_IMPRESSIONS_DESKTOP_SEARCH", "profile_views_search_desktop"),
    ("BUSINESS_IMPRESSIONS_MOBILE_SEARCH", "profile_views_search_mobile"),
    ("CALL_CLICKS", "call_clicks"),
    ("WEBSITE_CLICKS", "website_clicks"),
    ("BUSINESS_DIRECTION_REQUESTS", "direction_requests"),
]


class GoogleBusinessProfileProvider(IntegrationProvider):
    slug = "google_business_profile"
    display_name = "Google Business Profile"
    category = "local"
    icon_id = "google"
    description = (
        "Sync reviews, calls, directions, website clicks, and profile views."
    )
    scopes = ["business.manage"]

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = getattr(settings, "google_gbp_client_id", "") or ""
        self._client_secret = getattr(settings, "google_gbp_client_secret", "") or ""

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
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
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
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
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
        location_name, title = await _resolve_primary_location(access_token)
        return AccountInfo(
            external_account_id=location_name,
            external_account_name=title or "Google Business Profile",
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
        metrics: dict[str, float] = {}
        raw_by_key: dict[str, dict] = {}
        rows = 0

        location_name = external_account_id
        if not location_name:
            location_name, _ = await _resolve_primary_location(access_token)

        if not location_name:
            return SyncResult(
                rows_pulled=0,
                started_at=started,
                finished_at=datetime.now(UTC),
                error_message=(
                    "No Google Business Profile location found — "
                    "verify the account has a verified listing."
                ),
            )

        end = datetime.now(UTC).date()
        start = end - timedelta(days=28)

        perf_metrics, perf_raw = await _fetch_performance_metrics(
            access_token,
            location_name=location_name,
            start_date=start,
            end_date=end,
        )
        metrics.update(perf_metrics)
        raw_by_key.update(perf_raw)
        rows += len(perf_metrics)

        review_metrics, review_raw = await _fetch_reviews_summary(
            access_token,
            location_name=location_name,
        )
        metrics.update(review_metrics)
        raw_by_key.update(review_raw)
        rows += len(review_metrics)

        # Aggregates for intelligence layer
        profile_views = sum(
            metrics.get(k, 0)
            for k in (
                "profile_views_maps_desktop",
                "profile_views_maps_mobile",
                "profile_views_search_desktop",
                "profile_views_search_mobile",
            )
        )
        if profile_views > 0:
            metrics["profile_views"] = profile_views
            raw_by_key["profile_views"] = {"source": "sum_of_impression_metrics"}

        finished = datetime.now(UTC)
        return SyncResult(
            rows_pulled=rows,
            started_at=started,
            finished_at=finished,
            metrics=metrics,
            metric_raw=raw_by_key,
            period_end=datetime.combine(end, datetime.min.time(), tzinfo=UTC),
        )


async def _resolve_primary_location(access_token: str) -> tuple[str, str]:
    """Return (location_resource_name, title) for the first location."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        acct_resp = await client.get(f"{_ACCOUNTS_BASE}/accounts", headers=headers)
        acct_resp.raise_for_status()
        accounts = acct_resp.json().get("accounts") or []
        if not accounts:
            return "", ""

        account_name = accounts[0].get("name", "")
        if not account_name:
            return "", ""

        loc_resp = await client.get(
            f"{_LOCATIONS_BASE}/{account_name}/locations",
            headers=headers,
            params={"readMask": "name,title", "pageSize": 10},
        )
        loc_resp.raise_for_status()
        locations = loc_resp.json().get("locations") or []
        if not locations:
            return "", ""

        loc = locations[0]
        return loc.get("name", ""), loc.get("title", "")


async def _fetch_performance_metrics(
    access_token: str,
    *,
    location_name: str,
    start_date,
    end_date,
) -> tuple[dict[str, float], dict[str, dict]]:
    """Fetch 28-day totals from Business Profile Performance API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "dailyMetrics": [m[0] for m in _DAILY_METRICS],
        "dailyRange": {
            "startDate": {
                "year": start_date.year,
                "month": start_date.month,
                "day": start_date.day,
            },
            "endDate": {
                "year": end_date.year,
                "month": end_date.month,
                "day": end_date.day,
            },
        },
    }

    # Performance API expects locations/{id} not full accounts/... path
    loc_id = location_name.split("/")[-1]
    url = f"{_PERFORMANCE_BASE}/locations/{loc_id}:fetchMultiDailyMetricsTimeSeries"

    metrics: dict[str, float] = {}
    raw: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            log.warning(
                "gbp.performance_api_error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            return metrics, raw
        payload = resp.json()

    for series in payload.get("multiDailyMetricTimeSeries") or []:
        for daily_series in series.get("dailyMetricTimeSeries") or []:
            api_metric = daily_series.get("dailyMetric", "")
            key = _metric_key(api_metric)
            if not key:
                continue
            total = 0.0
            for dated in daily_series.get("timeSeries", {}).get("datedValues") or []:
                val = dated.get("value")
                if val is not None:
                    total += float(val)
            if total > 0:
                metrics[key] = total
                raw[key] = {"api_metric": api_metric, "period_days": 28}

    return metrics, raw


def _metric_key(api_metric: str) -> str | None:
    for enum_val, key in _DAILY_METRICS:
        if enum_val == api_metric:
            return key
    return None


async def _fetch_reviews_summary(
    access_token: str,
    *,
    location_name: str,
) -> tuple[dict[str, float], dict[str, dict]]:
    """Fetch review count + average rating via My Business v4 reviews API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{_REVIEWS_BASE}/{location_name}/reviews"
    metrics: dict[str, float] = {}
    raw: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params={"pageSize": 50})
        if resp.status_code >= 400:
            log.warning(
                "gbp.reviews_api_error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            return metrics, raw
        payload = resp.json()

    reviews = payload.get("reviews") or []
    total_count = float(payload.get("totalReviewCount") or len(reviews))
    if total_count <= 0 and not reviews:
        return metrics, raw

    ratings = [
        float(r.get("starRating", 0))
        for r in reviews
        if r.get("starRating") is not None
    ]
    # starRating may be enum string ONE..FIVE — map if needed
    if not ratings:
        ratings = [_star_enum_to_int(r.get("starRating")) for r in reviews]
        ratings = [r for r in ratings if r > 0]

    metrics["reviews_count"] = total_count
    raw["reviews_count"] = {"sample_size": len(reviews)}

    if ratings:
        avg = sum(ratings) / len(ratings)
        metrics["reviews_average_rating"] = round(avg, 2)
        raw["reviews_average_rating"] = {"sample_size": len(ratings)}

    return metrics, raw


def _star_enum_to_int(value: Any) -> float:
    mapping = {
        "ONE": 1,
        "TWO": 2,
        "THREE": 3,
        "FOUR": 4,
        "FIVE": 5,
    }
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value in mapping:
            return float(mapping[value])
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
