"""Tenancy — the layer that turns an authenticated Clerk user into a
fully-resolved (org, brand, role, permissions) context for every request.

Composable via FastAPI dependencies:

    require_user          (existing — Clerk JWT verify)
        ↓
    require_tenant        (resolves org + brand + role + perms)
        ↓
    require_permission    (asserts a specific permission slug)

Nothing in business modules should hardcode role checks. They depend on
require_permission(slug) and the policy in the DB.
"""

from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission, require_tenant
from aicmo.tenancy.exceptions import (
    BrandInactive,
    BrandNotInOrg,
    MissingTenant,
    NotAuthorized,
    OrganizationInactive,
    TenantMismatch,
)

__all__ = [
    "TenantContext",
    "require_tenant",
    "require_permission",
    "TenantMismatch",
    "MissingTenant",
    "NotAuthorized",
    "OrganizationInactive",
    "BrandInactive",
    "BrandNotInOrg",
]
