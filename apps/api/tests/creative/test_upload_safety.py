"""Brand-asset upload safety — declared content-type allowlist + size bound."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from aicmo.modules.creative.design.router import (
    MAX_BRAND_ASSET_BYTES,
    validate_brand_asset_type,
)


@pytest.mark.parametrize(
    "bad",
    [
        "image/svg+xml",  # can carry <script> — XSS on direct navigation
        "text/html",
        "text/javascript",
        "application/xml",
        "application/octet-stream",
        None,
        "",
    ],
)
def test_rejects_unsafe_or_unknown_types(bad):
    with pytest.raises(HTTPException) as ei:
        validate_brand_asset_type(bad)
    assert ei.value.status_code == 415


@pytest.mark.parametrize(
    "good,expected",
    [
        ("image/png", "image/png"),
        ("IMAGE/PNG", "image/png"),
        ("image/jpeg; charset=binary", "image/jpeg"),
        ("image/webp", "image/webp"),
        ("font/woff2", "font/woff2"),
    ],
)
def test_accepts_and_normalizes_safe_types(good, expected):
    assert validate_brand_asset_type(good) == expected


def test_size_limit_is_bounded():
    assert MAX_BRAND_ASSET_BYTES == 10 * 1024 * 1024
