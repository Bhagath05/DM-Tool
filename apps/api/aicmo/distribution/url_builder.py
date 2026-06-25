"""Single source of truth for share URLs + UTM parameters.

Every studio (content / ads / visuals / campaigns) calls this. Centralising
the UTM strategy here means:
- Attribution scheme can evolve without touching feature modules
- UTM values are server-controlled (no reflected user input → no XSS)
- The renderer-output URL exactly matches what the lead-capture endpoint
  expects to find on the landing page

Why pure function (not a class / service): zero state, zero I/O, ~5μs to
build. Easy to unit-test, no DB dependency.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal
from urllib.parse import urlencode

from aicmo.config import get_settings

# Source-asset taxonomy. Lines up with leads.source_asset_type column.
AssetType = Literal["content", "ad", "visual", "campaign"]

# UTM medium per asset type. Follows Google Analytics convention so reports
# downstream of UTM-parsing tools (Looker Studio, GA, Mixpanel) categorise
# the channel correctly without custom rules.
_MEDIUM_BY_ASSET: dict[AssetType, str] = {
    "content": "social",
    "ad": "paid",
    "visual": "social",
    "campaign": "social",
}

# When a more specific medium fits the SUB-type (e.g. a reel = "video"
# medium, a Google Search ad = "cpc" medium), the caller can override via
# `medium_override`. Defaults below.
MEDIUM_BY_CONTENT_TYPE: dict[str, str] = {
    "social_post": "social",
    "reel": "video",
    "carousel": "social",
    "story": "social",
    "live": "video",
    "email": "email",
    "ad_copy": "paid",
}

MEDIUM_BY_AD_TYPE: dict[str, str] = {
    "meta": "paid",
    "google_search": "cpc",
    "instagram_promo": "paid",
    "linkedin": "paid",
}

_SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def _normalize(v: str | None) -> str:
    """Lowercase, strip, replace whitespace with hyphens, truncate.

    Stops UTM-param injection (newlines, special chars) and keeps values
    tidy. Truncation matches the leads-table column length.
    """
    if v is None:
        return ""
    cleaned = re.sub(r"\s+", "-", v.strip().lower())
    cleaned = re.sub(r"[^a-z0-9_\-.]", "", cleaned)
    return cleaned[:128]


def build_share_url(
    *,
    slug: str,
    asset_type: AssetType,
    asset_id: uuid.UUID,
    platform: str | None,
    campaign_id: uuid.UUID | None = None,
    medium_override: str | None = None,
    utm_content_override: str | None = None,
) -> str:
    """Build a tracked share URL for the given asset + landing-page slug.

    The lead-capture endpoint reads `src` + `id` + `utm_*` from query
    params and stores them on the lead row — the closing of the loop.
    """
    if not _SLUG_OK.match(slug):
        raise ValueError(f"Invalid landing-page slug: {slug!r}")

    base = get_settings().public_base_url.rstrip("/")

    params: dict[str, str] = {
        "utm_source": _normalize(platform) or "direct",
        "utm_medium": medium_override or _MEDIUM_BY_ASSET[asset_type],
        "utm_campaign": str(campaign_id) if campaign_id else "organic",
        "utm_content": _normalize(utm_content_override) or asset_type,
        # Polymorphic attribution — leads table reads these into
        # source_asset_type / source_asset_id columns directly.
        "src": asset_type,
        "id": str(asset_id),
    }
    return f"{base}/p/{slug}?{urlencode(params)}"


def maybe_share_url(
    *,
    slug: str | None,
    asset_type: AssetType,
    asset_id: uuid.UUID,
    platform: str | None,
    campaign_id: uuid.UUID | None = None,
    medium_override: str | None = None,
    utm_content_override: str | None = None,
) -> str | None:
    """Nullable wrapper — returns None if no landing page is attached.

    Saves callers from repeating the `if slug is None: return None` check.
    """
    if not slug:
        return None
    return build_share_url(
        slug=slug,
        asset_type=asset_type,
        asset_id=asset_id,
        platform=platform,
        campaign_id=campaign_id,
        medium_override=medium_override,
        utm_content_override=utm_content_override,
    )
