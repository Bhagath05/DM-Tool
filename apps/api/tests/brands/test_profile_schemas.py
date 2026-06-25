"""Phase 10.2f — Brand profile schema invariants.

Covers `aicmo.modules.brands.schemas`:

  - reflection guard (no token / secret / api_key fields)
  - `BrandProfileUpdate` URL validator + extra=forbid
  - `BrandProfileRead` field-set stable
  - `BrandSetDefaultResult` + `BrandActivateResult` extra=forbid
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, ValidationError

from aicmo.modules.brands import schemas


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
    assert found, "expected at least one schema in brands.schemas"
    for model in found:
        for field_name in model.model_fields:
            lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{model.__name__}.{field_name} contains forbidden "
                    f"substring {forbidden!r}."
                )


# ---------------------------------------------------------------------
#  BrandProfileUpdate
# ---------------------------------------------------------------------


class TestBrandProfileUpdate:
    def test_accepts_https(self) -> None:
        m = schemas.BrandProfileUpdate(
            logo_url="https://cdn.example/logo.png",
            website="https://brand.example",
        )
        assert m.logo_url == "https://cdn.example/logo.png"
        assert m.website == "https://brand.example"

    def test_rejects_bare_domain(self) -> None:
        with pytest.raises(ValidationError):
            schemas.BrandProfileUpdate(website="brand.example")

    def test_rejects_ftp(self) -> None:
        with pytest.raises(ValidationError):
            schemas.BrandProfileUpdate(logo_url="ftp://x.test/a.png")

    def test_empty_string_clears(self) -> None:
        m = schemas.BrandProfileUpdate(logo_url="", website="")
        assert m.logo_url == ""
        assert m.website == ""

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            schemas.BrandProfileUpdate(is_default=True)  # type: ignore[call-arg]

    def test_is_default_is_not_settable_via_profile_update(self) -> None:
        """`is_default` is changed only via POST /brands/{id}/default —
        never via PATCH /profile. If a frontend ever tries to flip it
        in a profile update, it must 422 instead of silently winning."""
        assert "is_default" not in schemas.BrandProfileUpdate.model_fields


# ---------------------------------------------------------------------
#  BrandProfileRead field set
# ---------------------------------------------------------------------


def test_profile_read_field_set_stable() -> None:
    expected = {
        "id",
        "organization_id",
        "slug",
        "name",
        "description",
        "status",
        "created_by_user_id",
        "created_at",
        "updated_at",
        "logo_url",
        "website",
        "is_default",
        "active",
    }
    actual = set(schemas.BrandProfileRead.model_fields.keys())
    assert actual == expected, (
        f"BrandProfileRead schema drifted. Missing: "
        f"{expected - actual}; extra: {actual - expected}"
    )


# ---------------------------------------------------------------------
#  Result schemas — extra=forbid
# ---------------------------------------------------------------------


def test_set_default_result_extra_forbid() -> None:
    import uuid

    with pytest.raises(ValidationError):
        schemas.BrandSetDefaultResult(
            organization_id=uuid.uuid4(),
            brand_id=uuid.uuid4(),
            previous_default_brand_id=None,
            sneaky="x",  # type: ignore[call-arg]
        )


def test_activate_result_extra_forbid() -> None:
    import uuid

    with pytest.raises(ValidationError):
        schemas.BrandActivateResult(
            member_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            brand_id=uuid.uuid4(),
            previous_active_brand_id=None,
            sneaky="x",  # type: ignore[call-arg]
        )
