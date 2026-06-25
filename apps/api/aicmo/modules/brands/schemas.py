"""Pydantic schemas for brands."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


SLUG_RX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


class BrandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BrandList(BaseModel):
    items: list[BrandResponse]


class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must be lowercase letters, digits, hyphens (no leading/trailing hyphen)"
            )
        return v


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


# =====================================================================
#  Phase 10.2f — Brand profile + default flag + activation
# =====================================================================
#
# Additive schemas for Settings → Brands. The pre-10.2f `BrandResponse`
# stays unchanged so every existing caller keeps working; new endpoints
# return `BrandProfileRead`, which is a superset with the new fields.
#
# `active` on the read schema is DERIVED from `status` — the existing
# `status` column remains the single source of truth (dozen+ services
# already filter on `status == 'active'`). Adding a separate `active`
# column would duplicate the invariant and invite drift.

_URL_PREFIXES = ("https://", "http://")


def _validate_url_or_blank(v: str | None) -> str | None:
    if v is None or v == "":
        return v
    if not any(v.startswith(p) for p in _URL_PREFIXES):
        raise ValueError("URL must start with http:// or https://")
    return v


class BrandProfileUpdate(BaseModel):
    """PATCH body for Settings → Brand → profile.

    Same null-semantics as `OrganizationProfileUpdate`: an absent key
    leaves the field unchanged; an empty string clears it (service
    layer normalises "" → NULL).
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = Field(default=None, max_length=512)
    website: str | None = Field(default=None, max_length=512)

    @field_validator("logo_url", "website")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        return _validate_url_or_blank(v)


class BrandProfileRead(BaseModel):
    """Extended GET projection — superset of BrandResponse with the
    10.2f profile fields, default flag, and the derived `active` bool.

    `active` is computed from `status` on the way out, never persisted.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    status: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Phase 10.2f additions
    logo_url: str | None
    website: str | None
    is_default: bool
    active: bool


class BrandSetDefaultResult(BaseModel):
    """Returned by `POST /brands/{id}/default`.

    Carries the newly-default brand id and the prior-default id (if any)
    so the UI can update both rows in one round-trip without re-fetching
    the full brand list.
    """

    model_config = ConfigDict(extra="forbid")

    organization_id: uuid.UUID
    brand_id: uuid.UUID
    previous_default_brand_id: uuid.UUID | None = None


class BrandActivateResult(BaseModel):
    """Returned by `POST /brands/{id}/activate`.

    Persists the caller's `OrganizationMember.last_active_brand_id` so
    a returning user lands back on the same brand without re-selecting.
    NOT the same as `is_default` (which is org-wide).
    """

    model_config = ConfigDict(extra="forbid")

    member_id: uuid.UUID
    organization_id: uuid.UUID
    brand_id: uuid.UUID
    previous_active_brand_id: uuid.UUID | None = None
