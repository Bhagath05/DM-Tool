"""Social Intelligence Layer API. Post W1-12: brand-scoped."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.db.session import get_db
from aicmo.modules.social import service
from aicmo.modules.social.analyzer import run_analyzer
from aicmo.modules.social.schemas import (
    AnalyzeRequest,
    AnalyzeResult,
    AudiencePatternList,
    ImportResult,
    ManualImportPayload,
    SocialAssetList,
    SocialConnectionList,
    SocialPlatform,
    WinningPatternList,
)
from aicmo.providers.social.registry import get_social_provider
from aicmo.tenancy.context import TenantContext
from aicmo.tenancy.dependencies import require_permission

router = APIRouter(prefix="/social", tags=["social"])


class ConnectAvailability(BaseModel):
    platform: SocialPlatform
    available: bool
    reason: str | None = None


class ConnectAvailabilityList(BaseModel):
    items: list[ConnectAvailability]


@router.get("/availability", response_model=ConnectAvailabilityList)
async def get_availability() -> ConnectAvailabilityList:
    out: list[ConnectAvailability] = []
    for name in ("instagram",):
        try:
            provider = get_social_provider(name)
            ok = provider.available()
            out.append(
                ConnectAvailability(
                    platform=name,  # type: ignore[arg-type]
                    available=ok,
                    reason=None
                    if ok
                    else "OAuth credentials not configured — use Manual Import below for now.",
                )
            )
        except ValueError:
            continue
    for name in ("facebook", "linkedin", "youtube", "tiktok"):
        out.append(
            ConnectAvailability(
                platform=name,  # type: ignore[arg-type]
                available=False,
                reason="OAuth coming later — manual import is supported today.",
            )
        )
    return ConnectAvailabilityList(items=out)


@router.get("/connections", response_model=SocialConnectionList)
async def list_connections(
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> SocialConnectionList:
    items = await service.list_connections(session, brand_id=tenant.brand_id)
    return SocialConnectionList(items=items)


@router.post(
    "/import",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def manual_import(
    payload: ManualImportPayload,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> ImportResult:
    return await service.manual_import(
        session, tenant=tenant, payload=payload
    )


@router.get("/assets", response_model=SocialAssetList)
async def list_assets(
    platform: SocialPlatform | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> SocialAssetList:
    items = await service.list_assets(
        session, brand_id=tenant.brand_id, platform=platform, limit=limit
    )
    return SocialAssetList(items=items)


@router.get("/patterns", response_model=WinningPatternList)
async def list_patterns(
    platform: SocialPlatform | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> WinningPatternList:
    items = await service.list_winning_patterns(
        session, brand_id=tenant.brand_id, platform=platform
    )
    return WinningPatternList(items=items)


@router.get("/audience-patterns", response_model=AudiencePatternList)
async def list_audience(
    platform: SocialPlatform | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("library.view")),
) -> AudiencePatternList:
    items = await service.list_audience_patterns(
        session, brand_id=tenant.brand_id, platform=platform
    )
    return AudiencePatternList(items=items)


@router.post("/analyze", response_model=AnalyzeResult)
async def analyze(
    payload: AnalyzeRequest,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> AnalyzeResult:
    return await run_analyzer(
        session, tenant=tenant, platform=payload.platform
    )


class OAuthInitResponse(BaseModel):
    authorize_url: str


@router.get(
    "/oauth/{platform}/init",
    response_model=OAuthInitResponse,
)
async def oauth_init(
    platform: SocialPlatform,
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> OAuthInitResponse:
    try:
        provider = get_social_provider(platform)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    if not provider.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{provider.display_name} OAuth isn't configured on this server yet. "
                "Set the platform's client_id / client_secret in .env, "
                "or use Manual Import to test the intelligence loop today."
            ),
        )
    redirect_uri = f"{_public_base_url()}/api/v1/social/oauth/{platform}/callback"
    from aicmo.modules.social.oauth_state import issue

    state = issue(
        user_id=tenant.user_id,
        brand_id=str(tenant.brand_id),
        platform=platform,
    )
    init = provider.init_oauth(
        user_id=tenant.user_id, redirect_uri=redirect_uri
    )
    # Replace provider random state with signed state carrying tenant context
    from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

    parsed = urlparse(init.authorize_url)
    qs = parse_qs(parsed.query)
    qs["state"] = [state]
    authorize_url = urlunparse(
        parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()}))
    )
    return OAuthInitResponse(authorize_url=authorize_url)


@router.get("/oauth/{platform}/callback")
async def oauth_callback(
    platform: SocialPlatform,
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """OAuth callback — completes token exchange and redirects to social page."""
    from aicmo.modules.social.oauth_state import InvalidSocialOAuthState, verify

    try:
        user_id, brand_id_str, expected_platform = verify(state)
    except InvalidSocialOAuthState as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if expected_platform != platform:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Platform mismatch.")

    tenant = await service.resolve_tenant_for_oauth(
        session,
        clerk_user_id=user_id,
        brand_id=uuid.UUID(brand_id_str),
    )

    redirect_uri = f"{_public_base_url()}/api/v1/social/oauth/{platform}/callback"
    await service.complete_oauth(
        session,
        tenant=tenant,
        platform=platform,
        code=code,
        redirect_uri=redirect_uri,
    )
    return RedirectResponse(
        url=f"{_public_base_url()}/settings/integrations?connected={platform}"
    )


@router.post("/sync/{platform}", response_model=ImportResult)
async def sync_platform(
    platform: SocialPlatform,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
    limit: int = Query(default=25, ge=1, le=100),
) -> ImportResult:
    """Pull live metrics and posts from a connected platform."""
    return await service.sync_platform(
        session, tenant=tenant, platform=platform, limit=limit
    )


@router.post("/disconnect/{platform}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_platform(
    platform: SocialPlatform,
    session: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(require_permission("settings.manage")),
) -> None:
    """Disconnect a social platform — clears stored tokens."""
    await service.disconnect_platform(session, tenant=tenant, platform=platform)


def _public_base_url() -> str:
    from aicmo.config import get_settings

    s = get_settings()
    return s.public_base_url or "http://localhost:3000"
