"""Metric normalization — provider-specific mapping + semantic honesty."""

from __future__ import annotations

from aicmo.modules.marketing_analytics import normalize
from aicmo.modules.marketing_analytics.normalize import MetricKind, normalize_metric


def test_instagram_reach_is_rolling_reach():
    m = normalize_metric("reach_28d")
    assert m.canonical == normalize.REACH
    assert m.kind == MetricKind.ROLLING
    assert m.comparable_across_platforms is True


def test_engagement_rate_is_a_rate_never_summed():
    m = normalize_metric("engagement_rate")
    assert m.canonical == normalize.ENGAGEMENT_RATE
    assert m.kind == MetricKind.RATE
    assert m.unit == "ratio"


def test_youtube_views_is_cumulative_and_not_reach():
    """YouTube lifetime `views` must NOT be conflated with Instagram reach."""
    yt = normalize_metric("views")
    ig_reach = normalize_metric("reach_28d")
    assert yt.canonical == normalize.LIFETIME_VIEWS
    assert yt.kind == MetricKind.CUMULATIVE
    assert yt.canonical != ig_reach.canonical
    # cumulative lifetime totals are not comparable across accounts
    assert yt.comparable_across_platforms is False


def test_ig_video_views_differ_from_youtube_lifetime_views():
    assert normalize_metric("views_28d").canonical == normalize.VIDEO_VIEWS
    assert normalize_metric("views").canonical == normalize.LIFETIME_VIEWS
    assert normalize_metric("views_28d").canonical != normalize_metric("views").canonical


def test_subscribers_and_followers_share_audience_family():
    """Audience size is comparable across platforms even under different names."""
    for key in ("followers", "page_followers", "page_fans", "subscribers"):
        m = normalize_metric(key)
        assert m.canonical == normalize.AUDIENCE
        assert m.kind == MetricKind.LEVEL
        assert m.comparable_across_platforms is True


def test_followers_level_vs_reach_rolling_are_distinct_kinds():
    assert normalize_metric("followers").kind == MetricKind.LEVEL
    assert normalize_metric("reach_28d").kind == MetricKind.ROLLING


def test_gbp_local_action_metrics():
    assert normalize_metric("call_clicks").canonical == normalize.CALL_CLICKS
    assert normalize_metric("website_clicks").canonical == normalize.WEBSITE_CLICKS
    assert normalize_metric("direction_requests").canonical == normalize.DIRECTION_REQUESTS
    assert normalize_metric("reviews_average_rating").kind == MetricKind.RATE


def test_unknown_metric_passes_through_and_is_not_comparable():
    """An unknown key must never masquerade as a known family."""
    m = normalize_metric("some_new_provider_metric")
    assert m.canonical == "some_new_provider_metric"
    assert m.comparable_across_platforms is False
    assert m.label == "Some New Provider Metric"
    assert not normalize.is_known_metric("some_new_provider_metric")
    assert normalize.is_known_metric("reach_28d")


def test_per_content_metrics_are_not_invented():
    """Likes/comments/shares/saves are per-content — we don't have them at the
    account level, so they must NOT resolve to a known account-level family."""
    for key in ("likes", "comments", "shares", "saves"):
        assert not normalize.is_known_metric(key)


def test_provider_labels_are_plain_language():
    assert normalize.provider_label("google_business_profile") == "Google Business Profile"
    assert normalize.provider_label("instagram_organic") == "Instagram"
    assert normalize.provider_label("brand_new_provider") == "Brand New Provider"
