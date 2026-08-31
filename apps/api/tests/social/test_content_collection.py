"""Phase 5 — per-content collection into SocialAsset + PerformanceSignal."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from aicmo.modules.integrations.providers.base import ContentMetricResult
from aicmo.modules.social import content_metrics
from aicmo.modules.social.models import PerformanceSignal, SocialAsset

NOW = datetime.now(UTC)
BRAND = uuid.uuid4()


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Sess:
    """Routes scheduled_posts vs social_assets reads by the compiled SQL."""

    def __init__(self, scheduled=None, assets=None):
        self._scheduled = scheduled or []
        self._assets = assets or []
        self.added: list = []
        self.committed = False
        self.captured: dict[str, object] = {}

    async def execute(self, stmt):
        s = str(stmt)
        if "scheduled_posts" in s:
            self.captured["scheduled"] = stmt
            return _Res(self._scheduled)
        if "social_assets" in s:
            self.captured["assets"] = stmt
            return _Res(self._assets)
        return _Res([])

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.committed = True

    async def flush(self):
        pass


def _conn(provider="youtube"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        provider_slug=provider,
        brand_id=BRAND,
        external_account_id="acct",
        state="ACTIVE",
    )


def _post(post_id="v1", day=1):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id="u1",
        organization_id=uuid.uuid4(),
        brand_id=BRAND,
        platform="youtube",
        platform_post_id=post_id,
        publish_status="published",
        published_at=NOW - timedelta(days=day),
        updated_at=NOW - timedelta(days=day),
    )


def _fake_provider(results, supported=True):
    prov = SimpleNamespace(content_metrics_supported=supported)
    prov.fetch_content_metrics = AsyncMock(return_value=results)
    return prov


def _patch_registry(monkeypatch, provider):
    monkeypatch.setattr(
        content_metrics.IntegrationRegistry, "get", staticmethod(lambda slug: provider)
    )
    monkeypatch.setattr(
        content_metrics, "ensure_access_token", AsyncMock(return_value="SECRET-TOKEN")
    )


# ---------------- collection writes ----------------


@pytest.mark.asyncio
async def test_collect_writes_socialasset_and_signal(monkeypatch):
    post = _post("v1")
    result = ContentMetricResult(
        platform_post_id="v1",
        asset_type="video",
        metrics={"views": 1000.0, "likes": 50.0, "comments_count": 10.0},
        raw={"source": "youtube_data_api"},
    )
    provider = _fake_provider([result])
    _patch_registry(monkeypatch, provider)
    conn = _conn("youtube")
    sess = _Sess(scheduled=[post], assets=[])

    written = await content_metrics.collect_for_connection(sess, connection=conn)

    assert written == 1
    assert sess.committed is True
    socialassets = [r for r in sess.added if isinstance(r, SocialAsset)]
    signals = [r for r in sess.added if isinstance(r, PerformanceSignal)]
    assert len(socialassets) == 1 and len(signals) == 1
    a = socialassets[0]
    assert a.connection_id is None  # integration provider — no social connection
    assert a.provider_slug == "youtube"
    assert a.integration_connection_id == conn.id
    assert a.brand_id == BRAND and a.platform == "youtube" and a.platform_post_id == "v1"
    # signal carries the real numbers + records which metrics were provided
    assert signals[0].views == 1000 and signals[0].likes == 50
    assert signals[0].raw_json["metrics"] == result.metrics


@pytest.mark.asyncio
async def test_collect_updates_existing_no_duplicate_asset(monkeypatch):
    post = _post("v1")
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        platform_post_id="v1",
        asset_type="video",
        permalink=None,
        raw_json={},
        provider_slug=None,
        integration_connection_id=None,
        updated_at=NOW - timedelta(days=5),  # stale → eligible
    )
    provider = _fake_provider(
        [ContentMetricResult("v1", "video", {"views": 5.0}, {"source": "yt"})]
    )
    _patch_registry(monkeypatch, provider)
    sess = _Sess(scheduled=[post], assets=[existing])

    written = await content_metrics.collect_for_connection(sess, connection=_conn())

    assert written == 1
    assert not [r for r in sess.added if isinstance(r, SocialAsset)]  # updated, not inserted
    assert len([r for r in sess.added if isinstance(r, PerformanceSignal)]) == 1
    assert existing.provider_slug == "youtube"  # linkage backfilled


@pytest.mark.asyncio
async def test_incremental_skips_recently_collected(monkeypatch):
    post = _post("v1")
    fresh = SimpleNamespace(
        id=uuid.uuid4(),
        platform_post_id="v1",
        asset_type="video",
        permalink=None,
        raw_json={},
        provider_slug="youtube",
        integration_connection_id=uuid.uuid4(),
        updated_at=NOW,  # just collected → skip
    )
    provider = _fake_provider([])
    _patch_registry(monkeypatch, provider)
    sess = _Sess(scheduled=[post], assets=[fresh])

    written = await content_metrics.collect_for_connection(sess, connection=_conn())

    assert written == 0
    provider.fetch_content_metrics.assert_not_awaited()  # nothing due → no API call


@pytest.mark.asyncio
async def test_missing_platform_post_id_is_ignored(monkeypatch):
    good = _post("v1")
    bad = _post(None)  # never published a real id
    provider = _fake_provider([ContentMetricResult("v1", "video", {"views": 3.0}, {})])
    _patch_registry(monkeypatch, provider)
    sess = _Sess(scheduled=[good, bad], assets=[])

    written = await content_metrics.collect_for_connection(sess, connection=_conn())

    # only the post with a real id is measured
    assert written == 1
    refs = provider.fetch_content_metrics.await_args.kwargs["posts"]
    assert [r.platform_post_id for r in refs] == ["v1"]


@pytest.mark.asyncio
async def test_unsupported_provider_collects_nothing(monkeypatch):
    provider = _fake_provider([], supported=False)
    _patch_registry(monkeypatch, provider)
    sess = _Sess(scheduled=[_post("v1")], assets=[])

    written = await content_metrics.collect_for_connection(sess, connection=_conn())

    assert written == 0
    provider.fetch_content_metrics.assert_not_awaited()


# ---------------- tenant isolation ----------------


@pytest.mark.asyncio
async def test_queries_are_scoped_to_the_brand(monkeypatch):
    provider = _fake_provider([ContentMetricResult("v1", "video", {"views": 1.0}, {})])
    _patch_registry(monkeypatch, provider)
    sess = _Sess(scheduled=[_post("v1")], assets=[])

    await content_metrics.collect_for_connection(sess, connection=_conn())

    sched_sql = sess.captured["scheduled"].compile(dialect=postgresql.dialect())
    assert "brand_id" in str(sched_sql) and BRAND in sched_sql.params.values()
    asset_sql = sess.captured["assets"].compile(dialect=postgresql.dialect())
    assert "brand_id" in str(asset_sql) and BRAND in asset_sql.params.values()


# ---------------- failure isolation + token safety (cron) ----------------


@pytest.mark.asyncio
async def test_connection_failure_is_isolated_and_never_logs_token(monkeypatch):
    conn = _conn("youtube")

    class _CtxSess:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _model, _id):
            return conn

    monkeypatch.setattr(content_metrics, "SessionLocal", lambda: _CtxSess())
    secret = "ya29.SUPER-SECRET"
    monkeypatch.setattr(
        content_metrics,
        "collect_for_connection",
        AsyncMock(side_effect=RuntimeError(f"boom token={secret}")),
    )
    calls: list = []
    monkeypatch.setattr(
        content_metrics,
        "log",
        SimpleNamespace(warning=lambda *a, **k: calls.append((a, k)), info=lambda *a, **k: None),
    )

    out = await content_metrics._collect_one(conn.id)

    assert out == 0  # failure isolated — returns 0, never raises
    blob = repr(calls)
    assert secret not in blob  # token from the exception is NOT logged
    assert "youtube" in blob  # provider slug is safe to log
    assert any(kw.get("error_type") == "RuntimeError" for _, kw in calls)
