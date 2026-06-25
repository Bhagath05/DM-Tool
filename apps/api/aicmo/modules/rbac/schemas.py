"""Pydantic schemas for RBAC reads + management."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


SLUG_RX = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


# ---------------------------------------------------------------------
#  Permission
# ---------------------------------------------------------------------


class PermissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    category: str


class PermissionList(BaseModel):
    items: list[PermissionResponse]


# ---------------------------------------------------------------------
#  Role
# ---------------------------------------------------------------------


class RoleResponse(BaseModel):
    """A role with its embedded permission slugs (the read shape every
    UI needs)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    slug: str
    name: str
    description: str | None
    is_system: bool
    permission_slugs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RoleList(BaseModel):
    items: list[RoleResponse]


class RoleCreate(BaseModel):
    """Create a custom role within an organization.

    System roles (owner/admin/editor/viewer) are seeded by migration and
    cannot be created via this endpoint.
    """

    slug: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    permission_slugs: list[str] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must start with a letter and contain only lowercase "
                "letters, digits, underscores"
            )
        if v in ("owner", "admin", "editor", "viewer"):
            raise ValueError(
                "slug conflicts with a system role — pick a unique slug"
            )
        return v


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    permission_slugs: list[str] | None = None


# ---------------------------------------------------------------------
#  Member permissions lookup
# ---------------------------------------------------------------------


class MemberPermissionsResponse(BaseModel):
    member_id: uuid.UUID
    role_slugs: list[str]
    permission_slugs: list[str]
