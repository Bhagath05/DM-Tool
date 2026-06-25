"""/api/v1/users/me — the frontend's identity + tenant bootstrap call.

Designed to NEVER 4xx for an authenticated user. If the user has 0
memberships, the response carries `suggested_route='/onboarding'`
rather than an error. The frontend treats the response uniformly and
routes off `suggested_route`.

Tenant resolution here is best-effort: we *try* to resolve a tenant
from the headers, but failure (missing headers, no memberships) is fine
— it just leaves `active = null`.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.auth.clerk import AuthContext, require_user
from aicmo.auth.clerk_profile import (
    fetch_clerk_user_profile,
    is_placeholder_email,
)
from aicmo.db.session import get_db
from aicmo.modules.users.schemas import MeResponse
from aicmo.modules.users.service import build_me_response, get_or_create_from_clerk
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.exceptions import TenantError
from aicmo.tenancy.dependencies import require_tenant

log = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    request: Request,
    auth: AuthContext = Depends(require_user),
    session: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return the user + their memberships + the resolved active tenant
    (if headers carried one). Never errors for an authenticated user.
    """
    # Always reconcile the user row.
    email = auth.email
    display_name = auth.display_name
    avatar_url = auth.avatar_url

    if auth.user_id != "dev-user" and is_placeholder_email(email):
        fetched = await fetch_clerk_user_profile(auth.user_id)
        email = email or fetched[0]
        display_name = display_name or fetched[1]
        avatar_url = avatar_url or fetched[2]

    user = await get_or_create_from_clerk(
        session,
        clerk_user_id=auth.user_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
    )

    # Best-effort tenant resolution. We invoke require_tenant manually
    # because Depends would 4xx and our /me contract is "never 4xx".
    active: TenantContext | None = None
    try:
        resolver = require_tenant(brand_optional=True)
        active = await resolver(
            request=request, auth=auth, session=session
        )
    except TenantError:
        active = None  # legitimate — no headers yet, or no memberships

    response = await build_me_response(
        session, user=user, active=active
    )
    await session.commit()
    return response
