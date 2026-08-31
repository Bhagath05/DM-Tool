"""Canonical metric normalization.

Different providers report the same idea under different keys — and, critically,
report *different ideas* under similar-looking keys. This module maps each raw
`ConnectorMetric.metric_key` onto a canonical metric that carries:

- a **family** (`canonical`) used to group and compare metrics, and
- a **semantic kind** that says how the number behaves over time, which decides
  how it may honestly be aggregated and compared.

Honesty rules baked in here:
- YouTube ``views`` is a *cumulative lifetime* channel total — it is NOT the same
  measurement as Instagram ``reach_28d`` (a trailing-28-day unique-reach flow) or
  GBP ``profile_views``. They get different canonical families and are never
  cross-compared.
- Followers / page-followers / page-fans / subscribers are all *audience-size
  levels*; they share the ``audience`` family so audience growth can be compared
  across platforms, while each keeps its own human label.
- Anything we do not have a mapping for is surfaced as its own passthrough metric
  (never dropped, never renamed into something it is not) and marked
  non-comparable, so an unknown key can never be silently treated as reach/etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricKind(StrEnum):
    """How a metric behaves over time — decides valid aggregation/comparison."""

    LEVEL = "level"
    """A stock/level measured at a point in time (followers, review count).
    Period change = latest − value-at-start. Never summed across snapshots."""

    ROLLING = "rolling"
    """A trailing-window flow already totalled by the provider (reach_28d,
    impressions_28d, clicks). Compare the latest snapshot vs a prior snapshot.
    NEVER summed across snapshots — that would double-count the window."""

    RATE = "rate"
    """A ratio (engagement_rate, average rating). Compare latest vs prior.
    Never summed, never averaged into a fake total."""

    CUMULATIVE = "cumulative"
    """A monotonic lifetime total (YouTube channel lifetime views). Period
    change = latest − value-at-start; the level itself is not comparable across
    platforms because the accumulation window differs per account."""


@dataclass(frozen=True)
class CanonicalMetric:
    """Normalized description of a provider metric key."""

    canonical: str  # family id used for grouping/rules/cross-platform compare
    label: str  # human label (plain, Simple-Mode friendly)
    kind: MetricKind
    unit: str  # "count" | "ratio" | "rating"
    comparable_across_platforms: bool
    higher_is_better: bool = True


# --- canonical families (stable ids the rules + API refer to) ---------------
REACH = "reach"
IMPRESSIONS = "impressions"
VIDEO_VIEWS = "video_views"
LIFETIME_VIEWS = "lifetime_views"
PROFILE_VIEWS = "profile_views"
ENGAGEMENT_RATE = "engagement_rate"
ENGAGED_ACCOUNTS = "engaged_accounts"
AUDIENCE = "audience"  # followers / subscribers / fans — audience size
WEBSITE_CLICKS = "website_clicks"
CALL_CLICKS = "call_clicks"
DIRECTION_REQUESTS = "direction_requests"
REVIEWS_COUNT = "reviews_count"
REVIEWS_RATING = "reviews_rating"
CONTENT_COUNT = "content_count"
FOLLOWING = "following"


# Raw provider ``metric_key`` → canonical metric. Keys are globally unique in the
# current provider set, so a key-level map is unambiguous; where a provider
# reuses a generic word for a different meaning (YouTube ``views``), the mapping
# encodes the correct semantic kind so it is never conflated.
_RAW_TO_CANONICAL: dict[str, CanonicalMetric] = {
    # --- Instagram (social) ---
    "reach_28d": CanonicalMetric(REACH, "Reach (28 days)", MetricKind.ROLLING, "count", True),
    "impressions_28d": CanonicalMetric(
        IMPRESSIONS, "Impressions (28 days)", MetricKind.ROLLING, "count", True
    ),
    "views_28d": CanonicalMetric(
        VIDEO_VIEWS, "Video views (28 days)", MetricKind.ROLLING, "count", True
    ),
    "engagement_rate": CanonicalMetric(
        ENGAGEMENT_RATE, "Engagement rate", MetricKind.RATE, "ratio", True
    ),
    "accounts_engaged": CanonicalMetric(
        ENGAGED_ACCOUNTS, "Accounts engaged", MetricKind.ROLLING, "count", True
    ),
    # --- Facebook Pages ---
    "engaged_users_28d": CanonicalMetric(
        ENGAGED_ACCOUNTS, "Engaged users (28 days)", MetricKind.ROLLING, "count", True
    ),
    "page_followers": CanonicalMetric(AUDIENCE, "Followers", MetricKind.LEVEL, "count", True),
    "page_fans": CanonicalMetric(AUDIENCE, "Page likes", MetricKind.LEVEL, "count", True),
    # --- LinkedIn / Pinterest ---
    "followers": CanonicalMetric(AUDIENCE, "Followers", MetricKind.LEVEL, "count", True),
    "following": CanonicalMetric(FOLLOWING, "Following", MetricKind.LEVEL, "count", True),
    "pins_sampled": CanonicalMetric(CONTENT_COUNT, "Pins", MetricKind.LEVEL, "count", True),
    # --- YouTube (part=statistics: channel-level totals) ---
    "subscribers": CanonicalMetric(AUDIENCE, "Subscribers", MetricKind.LEVEL, "count", True),
    "views": CanonicalMetric(
        LIFETIME_VIEWS, "Lifetime views", MetricKind.CUMULATIVE, "count", False
    ),
    "videos": CanonicalMetric(CONTENT_COUNT, "Videos published", MetricKind.LEVEL, "count", True),
    # --- Google Business Profile ---
    "profile_views": CanonicalMetric(
        PROFILE_VIEWS, "Profile views", MetricKind.ROLLING, "count", True
    ),
    "call_clicks": CanonicalMetric(CALL_CLICKS, "Phone calls", MetricKind.ROLLING, "count", True),
    "website_clicks": CanonicalMetric(
        WEBSITE_CLICKS, "Website clicks", MetricKind.ROLLING, "count", True
    ),
    "direction_requests": CanonicalMetric(
        DIRECTION_REQUESTS, "Direction requests", MetricKind.ROLLING, "count", True
    ),
    "reviews_count": CanonicalMetric(REVIEWS_COUNT, "Reviews", MetricKind.LEVEL, "count", True),
    "reviews_average_rating": CanonicalMetric(
        REVIEWS_RATING, "Average rating", MetricKind.RATE, "rating", True
    ),
}


# Provider slug → plain display name for the platform-comparison surface.
_PROVIDER_LABELS: dict[str, str] = {
    "instagram_organic": "Instagram",
    "facebook_pages": "Facebook",
    "linkedin_organic": "LinkedIn",
    "linkedin": "LinkedIn",
    "pinterest": "Pinterest",
    "youtube": "YouTube",
    "google_business_profile": "Google Business Profile",
    "tiktok": "TikTok",
    "meta_ads": "Meta Ads",
    "google_ads": "Google Ads",
}


def normalize_metric(metric_key: str) -> CanonicalMetric:
    """Map a raw provider metric key onto its canonical metric.

    An unknown key is passed through as its own non-comparable ``LEVEL`` metric
    with a humanized label — never dropped and never merged into a known family,
    so an unrecognized number can never masquerade as reach/engagement/etc.
    """
    known = _RAW_TO_CANONICAL.get(metric_key)
    if known is not None:
        return known
    label = metric_key.replace("_", " ").strip().title() or metric_key
    return CanonicalMetric(
        canonical=metric_key,
        label=label,
        kind=MetricKind.LEVEL,
        unit="count",
        comparable_across_platforms=False,
    )


def is_known_metric(metric_key: str) -> bool:
    """True only for keys with an explicit canonical mapping."""
    return metric_key in _RAW_TO_CANONICAL


def provider_label(provider_slug: str) -> str:
    """Plain-language platform name for a provider slug."""
    return _PROVIDER_LABELS.get(provider_slug, provider_slug.replace("_", " ").title())
