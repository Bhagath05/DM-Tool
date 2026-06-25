"""Phase 10.2f — Org profile schema invariants.

Covers the new 10.2f schemas in `aicmo.modules.orgs.schemas`:

  - `OrganizationProfileUpdate` — country, timezone, URL validators
  - `OrganizationProfileRead`   — superset of the existing response
  - `OrganizationAnalytics`     — counts surface for Settings overview

Plus the reflection guard that prevents any new schema from leaking a
secret-shaped field (token / secret / api_key / etc).
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, ValidationError

from aicmo.modules.orgs import schemas


FORBIDDEN_FIELD_SUBSTRINGS = (
    "token",
    "secret",
    "credential",
    "password",
    "api_key",
    "client_secret",
    "private_key",
)


def _public_schemas() -> list[type[BaseModel]]:
    return [
        obj
        for _name, obj in inspect.getmembers(schemas)
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == schemas.__name__
    ]


def test_no_schema_exposes_secrets() -> None:
    found = _public_schemas()
    assert found, "expected at least one schema in orgs.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r}."
                )


# ---------------------------------------------------------------------
#  OrganizationProfileUpdate — validators
# ---------------------------------------------------------------------


class TestCountryValidator:
    def test_accepts_uppercase_iso2(self) -> None:
        m = schemas.OrganizationProfileUpdate(country="US")
        assert m.country == "US"

    def test_lowercases_uppercased(self) -> None:
        m = schemas.OrganizationProfileUpdate(country="in")
        assert m.country == "IN"

    def test_rejects_three_letter(self) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(country="USA")

    def test_rejects_one_letter(self) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(country="U")

    def test_rejects_digits(self) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(country="U1")

    def test_none_is_passthrough(self) -> None:
        m = schemas.OrganizationProfileUpdate(country=None)
        assert m.country is None

    def test_empty_string_passes_through(self) -> None:
        """Empty string is the explicit 'clear this field' signal —
        service layer normalises to NULL. Validator must let it through."""
        m = schemas.OrganizationProfileUpdate(country="")
        assert m.country == ""


class TestTimezoneValidator:
    @pytest.mark.parametrize(
        "tz",
        ["UTC", "America/New_York", "Asia/Kolkata", "Etc/GMT+5", "Europe/London"],
    )
    def test_accepts_valid_iana_shapes(self, tz: str) -> None:
        m = schemas.OrganizationProfileUpdate(timezone=tz)
        assert m.timezone == tz

    @pytest.mark.parametrize(
        "tz",
        ["", None],
    )
    def test_accepts_empty_and_none(self, tz: str | None) -> None:
        m = schemas.OrganizationProfileUpdate(timezone=tz)
        assert m.timezone == tz

    @pytest.mark.parametrize(
        "tz",
        ["not a timezone", "/leading-slash", "trailing/", "spaces in/middle"],
    )
    def test_rejects_garbage(self, tz: str) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(timezone=tz)


class TestUrlValidator:
    def test_accepts_https(self) -> None:
        m = schemas.OrganizationProfileUpdate(
            logo_url="https://example.com/x.png"
        )
        assert m.logo_url == "https://example.com/x.png"

    def test_accepts_http(self) -> None:
        m = schemas.OrganizationProfileUpdate(website="http://x.local")
        assert m.website == "http://x.local"

    def test_rejects_bare_domain(self) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(website="example.com")

    def test_rejects_ftp(self) -> None:
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(website="ftp://x.test")

    def test_empty_string_passes(self) -> None:
        m = schemas.OrganizationProfileUpdate(logo_url="", website="")
        assert m.logo_url == ""
        assert m.website == ""


class TestExtraForbid:
    def test_unknown_field_rejected(self) -> None:
        """`extra='forbid'` — a typo from the frontend (e.g. `tz` instead
        of `timezone`) must 422 instead of silently being ignored."""
        with pytest.raises(ValidationError):
            schemas.OrganizationProfileUpdate(tz="UTC")  # type: ignore[call-arg]


# ---------------------------------------------------------------------
#  OrganizationProfileRead — field-set pin
# ---------------------------------------------------------------------


def test_profile_read_field_set_stable() -> None:
    expected = {
        "id",
        "slug",
        "name",
        "owner_user_id",
        "status",
        "member_count",
        "brand_count",
        "created_at",
        "updated_at",
        "logo_url",
        "website",
        "industry",
        "timezone",
        "country",
    }
    actual = set(schemas.OrganizationProfileRead.model_fields.keys())
    assert actual == expected, (
        f"OrganizationProfileRead schema drifted. Missing: "
        f"{expected - actual}; extra: {actual - expected}"
    )


# ---------------------------------------------------------------------
#  OrganizationAnalytics — field-set pin
# ---------------------------------------------------------------------


def test_analytics_field_set_stable() -> None:
    expected = {
        "organization_id",
        "brand_count",
        "active_brand_count",
        "member_count",
        "pending_invite_count",
        "created_at",
        "last_activity_at",
    }
    actual = set(schemas.OrganizationAnalytics.model_fields.keys())
    assert actual == expected, (
        f"OrganizationAnalytics schema drifted. Missing: "
        f"{expected - actual}; extra: {actual - expected}"
    )


def test_analytics_extra_forbid() -> None:
    """If a caller sneaks in an extra field, the response shape would
    leak whatever-the-backend-happens-to-pass. Pin extra=forbid."""
    import uuid
    from datetime import datetime, timezone

    with pytest.raises(ValidationError):
        schemas.OrganizationAnalytics(
            organization_id=uuid.uuid4(),
            brand_count=0,
            active_brand_count=0,
            member_count=0,
            pending_invite_count=0,
            created_at=datetime.now(timezone.utc),
            last_activity_at=None,
            sneaky="value",  # type: ignore[call-arg]
        )
