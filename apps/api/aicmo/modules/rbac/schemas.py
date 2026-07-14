"""Pydantic schemas for RBAC reads + management."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RX = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

# Reserved system-role slugs — a custom role may never claim one of these.
# `owner` is internal-only (surfaced as "Admin" in the UI); the rest are the
# seeded default roles from migration 0067.
_SYSTEM_SLUGS = frozenset(
    {
        "owner",
        "admin",
        "marketing_manager",
        "performance_marketer",
        "content_creator",
        "designer",
        "crm_manager",
        "sales",
        "analyst",
        "editor",
        "viewer",
    }
)


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
    UI needs).

    `permission_slugs` is the ALLOW set (kept for backward compatibility —
    every existing consumer reads it as "the permissions this role
    grants"). `deny_slugs` is the explicit-DENY set introduced in Slice 2;
    a permission that appears in neither is INHERIT. `priority`, `color`
    and `member_count` power the Role Management UI.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    slug: str
    name: str
    description: str | None
    is_system: bool
    priority: int = 0
    color: str | None = None
    permission_slugs: list[str] = Field(default_factory=list)
    deny_slugs: list[str] = Field(default_factory=list)
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class RoleList(BaseModel):
    items: list[RoleResponse]


class RoleCreate(BaseModel):
    """Create a custom role within an organization.

    System roles (owner/admin/editor/viewer/…) are seeded by migration and
    cannot be created via this endpoint. `permission_slugs` (ALLOW) and
    `deny_slugs` (DENY) are both optional — a role may start empty and be
    configured in the editor; anything in neither list is INHERIT.
    """

    slug: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: int = Field(default=0, ge=0, le=1000)
    color: str | None = Field(default=None, max_length=16)
    permission_slugs: list[str] = Field(default_factory=list)
    deny_slugs: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must start with a letter and contain only lowercase "
                "letters, digits, underscores"
            )
        if v in _SYSTEM_SLUGS:
            raise ValueError("slug conflicts with a system role — pick a unique slug")
        return v


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    priority: int | None = Field(default=None, ge=0, le=1000)
    # color: absent → unchanged; "" → clear; "#rrggbb" → set.
    color: str | None = Field(default=None, max_length=16)
    permission_slugs: list[str] | None = None
    deny_slugs: list[str] | None = None


class RoleReorderItem(BaseModel):
    role_id: uuid.UUID
    priority: int = Field(ge=0, le=1000)


class RoleReorder(BaseModel):
    """Bulk priority update from a drag-to-reorder gesture. Only custom
    org-scoped roles are repriced — system role priorities are global and
    fixed, so items pointing at a system role are ignored server-side."""

    items: list[RoleReorderItem] = Field(min_length=1)


class RoleDuplicate(BaseModel):
    """Clone an existing role (system or custom) into a new custom role,
    copying its ALLOW + DENY grants, color and priority."""

    slug: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not SLUG_RX.match(v):
            raise ValueError(
                "slug must start with a letter and contain only lowercase "
                "letters, digits, underscores"
            )
        if v in _SYSTEM_SLUGS:
            raise ValueError("slug conflicts with a system role — pick a unique slug")
        return v


# ---------------------------------------------------------------------
#  Member permissions lookup
# ---------------------------------------------------------------------


class MemberPermissionsResponse(BaseModel):
    member_id: uuid.UUID
    role_slugs: list[str]
    permission_slugs: list[str]


# ---------------------------------------------------------------------
#  Role audit (read of the existing audit trail, scoped to one role)
# ---------------------------------------------------------------------


class RoleAuditEvent(BaseModel):
    """One audit row relevant to a role — either a direct role.* mutation
    or a member.role_assigned / member.role_removed touching this role."""

    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID
    actor_email: str | None = None
    actor_name: str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    summary: str | None = None
    occurred_at: datetime


class RoleAuditList(BaseModel):
    items: list[RoleAuditEvent]
