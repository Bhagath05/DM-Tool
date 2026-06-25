"""Typed HTTPException subclasses for tenant + auth failures.

Distinct classes per failure mode so log dashboards, alerting, and
support can triage cleanly. All inherit from FastAPI's HTTPException.
"""

from __future__ import annotations

from fastapi import HTTPException, status


class TenantError(HTTPException):
    """Base class — never raised directly."""


class MissingTenant(TenantError):
    """The request didn't carry an X-Organization-Id (or required brand)."""

    def __init__(self, *, detail: str = "Missing tenant context") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class TenantMismatch(TenantError):
    """The user is not a member of the requested organization."""

    def __init__(self, *, detail: str = "Not a member of this organization") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class OrganizationInactive(TenantError):
    def __init__(self, *, detail: str = "Organization is not active") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class BrandNotInOrg(TenantError):
    """The X-Brand-Id header refers to a brand that does not belong to
    the active organization. Likely a stale frontend state."""

    def __init__(
        self, *, detail: str = "Brand does not belong to this organization"
    ) -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class BrandInactive(TenantError):
    def __init__(self, *, detail: str = "Brand is archived or deleted") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotAuthorized(TenantError):
    """Permission denied — the caller's role does not grant the required action."""

    def __init__(
        self,
        *,
        action: str | None = None,
        role: str | None = None,
    ) -> None:
        detail = "Not authorized"
        if action:
            detail = f"Not authorized: missing permission '{action}'"
            if role:
                detail += f" (role: {role})"
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
