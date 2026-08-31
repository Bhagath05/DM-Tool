"""Phase 5 — per-content metric fetchers (mocked HTTP, no live credentials).

Verifies each provider parses ONLY the metrics its platform returns, omits
unavailable metrics (never fabricates), and isolates per-post failures.
"""

from __future__ import annotations

import httpx
import pytest

from aicmo.modules.integrations.providers.base import ContentRef
from aicmo.modules.integrations.providers.facebook_pages import FacebookPagesProvider
from aicmo.modules.integrations.providers.google_business_profile import (
    GoogleBusinessProfileProvider,
)
from aicmo.modules.integrations.providers.linkedin_organic import LinkedInOrganicProvider
from aicmo.modules.integrations.providers.pinterest import PinterestProvider
from aicmo.modules.integrations.providers.youtube import YouTubeProvider


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]


class _Client:
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        return self._handler(url, params or {})


def _patch(monkeypatch, handler):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client(handler))


# ---------------- YouTube ----------------


@pytest.mark.asyncio
async def test_youtube_parses_only_real_stats(monkeypatch):
    def handler(url, params):
        assert "/videos" in url
        return _Resp(
            200,
            {
                "items": [
                    {
                        "id": "v1",
                        "statistics": {
                            "viewCount": "1000",
                            "likeCount": "50",
                            "commentCount": "10",
                        },
                    }
                ]
            },
        )

    _patch(monkeypatch, handler)
    res = await YouTubeProvider().fetch_content_metrics(
        access_token="tok", external_account_id="ch", posts=[ContentRef("v1", "video")]
    )
    assert len(res) == 1
    assert res[0].metrics == {"views": 1000.0, "likes": 50.0, "comments_count": 10.0}
    # reach / impressions / saves are not in YouTube statistics → never invented
    assert "reach" not in res[0].metrics and "impressions" not in res[0].metrics


@pytest.mark.asyncio
async def test_youtube_skips_posts_without_metrics(monkeypatch):
    def handler(url, params):
        return _Resp(200, {"items": [{"id": "v1"}, {"id": "v2", "statistics": {"viewCount": "5"}}]})

    _patch(monkeypatch, handler)
    res = await YouTubeProvider().fetch_content_metrics(
        access_token="tok", external_account_id="ch", posts=[ContentRef("v1"), ContentRef("v2")]
    )
    assert {r.platform_post_id for r in res} == {"v2"}  # v1 had no stats → skipped


@pytest.mark.asyncio
async def test_youtube_http_error_yields_empty(monkeypatch):
    _patch(monkeypatch, lambda url, params: _Resp(500, {}))
    res = await YouTubeProvider().fetch_content_metrics(
        access_token="tok", external_account_id="ch", posts=[ContentRef("v1")]
    )
    assert res == []


# ---------------- Facebook ----------------


@pytest.mark.asyncio
async def test_facebook_parses_engagement_and_insights(monkeypatch):
    def handler(url, params):
        return _Resp(
            200,
            {
                "likes": {"summary": {"total_count": 12}},
                "comments": {"summary": {"total_count": 3}},
                "shares": {"count": 4},
                "insights": {
                    "data": [
                        {"name": "post_impressions", "values": [{"value": 500}]},
                        {"name": "post_impressions_unique", "values": [{"value": 300}]},
                    ]
                },
            },
        )

    _patch(monkeypatch, handler)
    # external_account_id=None so it skips the page-token call.
    res = await FacebookPagesProvider().fetch_content_metrics(
        access_token="tok", external_account_id=None, posts=[ContentRef("p1", "post")]
    )
    assert res[0].metrics == {
        "likes": 12.0,
        "comments_count": 3.0,
        "shares": 4.0,
        "impressions": 500.0,
        "reach": 300.0,
    }


# ---------------- LinkedIn ----------------


@pytest.mark.asyncio
async def test_linkedin_parses_social_actions(monkeypatch):
    def handler(url, params):
        return _Resp(
            200,
            {"likesSummary": {"totalLikes": 20}, "commentsSummary": {"aggregatedTotalComments": 5}},
        )

    _patch(monkeypatch, handler)
    res = await LinkedInOrganicProvider().fetch_content_metrics(
        access_token="tok", external_account_id=None, posts=[ContentRef("urn:li:share:1", "post")]
    )
    assert res[0].metrics == {"likes": 20.0, "comments_count": 5.0}
    # impressions not available on this endpoint → not fabricated
    assert "impressions" not in res[0].metrics


# ---------------- Pinterest ----------------


@pytest.mark.asyncio
async def test_pinterest_parses_impressions_and_saves(monkeypatch):
    def handler(url, params):
        return _Resp(200, {"all": {"summary_metrics": {"IMPRESSION": 800, "SAVE": 40}}})

    _patch(monkeypatch, handler)
    res = await PinterestProvider().fetch_content_metrics(
        access_token="tok", external_account_id=None, posts=[ContentRef("pin1", "image")]
    )
    assert res[0].metrics == {"impressions": 800.0, "saves": 40.0}


# ---------------- capability default ----------------


def test_supported_flags():
    assert YouTubeProvider.content_metrics_supported is True
    assert FacebookPagesProvider.content_metrics_supported is True
    assert LinkedInOrganicProvider.content_metrics_supported is True
    assert PinterestProvider.content_metrics_supported is True
    # A provider without the capability keeps the honest default.
    assert GoogleBusinessProfileProvider.content_metrics_supported is False


@pytest.mark.asyncio
async def test_unsupported_provider_default_is_empty():
    res = await GoogleBusinessProfileProvider().fetch_content_metrics(
        access_token="tok", external_account_id="x", posts=[ContentRef("p1")]
    )
    assert res == []
