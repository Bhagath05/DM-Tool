"""Tenant header parser — pure-function tests, no DB needed.

These guard the boundary between HTTP and the tenancy resolver. A header
parser bug here means every downstream tenant check operates on the wrong
UUID — or worse, an attacker-controlled string. Belt-and-braces tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import Mock

import pytest

from aicmo.tenancy.exceptions import MissingTenant
from aicmo.tenancy.headers import (
    BRAND_HEADER,
    ORG_HEADER,
    parse_brand_header,
    parse_org_header,
)


def _request_with(**headers: str) -> Mock:
    """Build a stand-in for `starlette.Request` carrying only headers.

    The parser only reads `request.headers.get(name)` so a dict-backed
    Mock is sufficient — avoids spinning up a TestClient for unit tests.
    """
    request = Mock()
    request.headers.get.side_effect = lambda key: headers.get(key)
    return request


class TestParseOrgHeader:
    def test_returns_none_when_header_absent(self) -> None:
        assert parse_org_header(_request_with()) is None

    def test_returns_uuid_when_valid(self) -> None:
        org_id = uuid.uuid4()
        req = _request_with(**{ORG_HEADER: str(org_id)})
        assert parse_org_header(req) == org_id

    def test_raises_on_garbage(self) -> None:
        req = _request_with(**{ORG_HEADER: "not-a-uuid"})
        with pytest.raises(MissingTenant) as exc:
            parse_org_header(req)
        assert "X-Organization-Id" in exc.value.detail

    def test_empty_string_is_treated_as_absent(self) -> None:
        # `not raw` triggers for "" — the parser treats it as no header
        # rather than a 400. Matches what nginx/CDN may set.
        req = _request_with(**{ORG_HEADER: ""})
        assert parse_org_header(req) is None


class TestParseBrandHeader:
    def test_returns_none_when_header_absent(self) -> None:
        assert parse_brand_header(_request_with()) is None

    def test_returns_uuid_when_valid(self) -> None:
        brand_id = uuid.uuid4()
        req = _request_with(**{BRAND_HEADER: str(brand_id)})
        assert parse_brand_header(req) == brand_id

    def test_raises_on_garbage(self) -> None:
        req = _request_with(**{BRAND_HEADER: "{}"})
        with pytest.raises(MissingTenant) as exc:
            parse_brand_header(req)
        assert "X-Brand-Id" in exc.value.detail

    def test_uppercase_uuid_accepted(self) -> None:
        # UUIDs are case-insensitive — accept both casings.
        brand_id = uuid.uuid4()
        req = _request_with(**{BRAND_HEADER: str(brand_id).upper()})
        assert parse_brand_header(req) == brand_id
