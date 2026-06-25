"""TenantContext — the resolved identity bundle for an authenticated request.

Every protected route receives one of these. It carries:

- user identity (both Clerk's `sub` and our UUID)
- the active organization
- the active brand (None for org-level routes like /settings/team)
- the member's role slug + computed permission set

The frozen dataclass discipline keeps it impossible to mutate mid-request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TenantContext:
    # Clerk subject — the legacy string id. Kept for audit + back-compat
    # with the existing `user_id` columns on business tables.
    user_id: str

    # Our canonical user UUID. The FK target for all new FKs.
    user_uuid: uuid.UUID

    # Active tenant scope.
    organization_id: uuid.UUID
    brand_id: uuid.UUID | None       # None on org-level endpoints
    member_id: uuid.UUID

    # Authorisation envelope. Computed by tenancy.dependencies.require_tenant
    # via a single JOIN through member_roles → role_permissions → permissions.
    role_slugs: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has_permission(self, slug: str) -> bool:
        return slug in self.permissions
