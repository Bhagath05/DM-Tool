"""Social intelligence service. Post W1-12: brand-scoped."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aicmo.modules.brands.models import Brand
from aicmo.modules.orgs.models import OrganizationMember
from aicmo.modules.social.models import (
    AudiencePattern,
    PerformanceSignal,
    SocialAsset,
    SocialConnection,
    WinningPattern,
)
from aicmo.modules.social.token_crypto import seal, unseal
from aicmo.modules.users.models import User
from aicmo.tenancy.permissions import (
    compute_permissions_for_member,
    compute_role_slugs_for_member,
)
from aicmo.modules.social.schemas import (
    AudiencePatternResponse,
    ImportResult,
    ManualImportPayload,
    PerformanceSignalResponse,
    SocialAssetResponse,
    SocialConnectionResponse,
    WinningPatternResponse,
)
from aicmo.tenancy.context import TenantContext

log = structlog.get_logger()


async def list_connections(
    session: AsyncSession, *, brand_id: uuid.UUID
) -> list[SocialConnectionResponse]:
    stmt = (
        select(SocialConnection)
        .where(SocialConnection.brand_id == brand_id)
        .order_by(SocialConnection.platform)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [SocialConnectionResponse.model_validate(r) for r in rows]


async def _get_or_create_connection(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    platform: str,
    source: str,
    metadata: dict | None = None,
) -> SocialConnection:
    stmt = select(SocialConnection).where(
        SocialConnection.brand_id == tenant.brand_id,
        SocialConnection.platform == platform,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        if metadata:
            row.metadata_json = {**(row.metadata_json or {}), **metadata}
        return row

    row = SocialConnection(
        id=uuid.uuid4(),
        user_id=tenant.user_id,
        organization_id=tenant.organization_id,
        brand_id=tenant.brand_id,
        platform=platform,
        source=source,
        metadata_json=metadata or {},
    )
    session.add(row)
    await session.flush()
    return row


async def manual_import(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    payload: ManualImportPayload,
) -> ImportResult:
    """Insert / update assets from a pasted JSON payload."""
    connection = await _get_or_create_connection(
        session,
        tenant=tenant,
        platform=payload.platform,
        source="manual_import",
        metadata={"handle": payload.handle} if payload.handle else None,
    )

    inserted = 0
    updated = 0
    signals_inserted = 0

    for spec in payload.assets:
        existing = await session.execute(
            select(SocialAsset).where(
                SocialAsset.brand_id == tenant.brand_id,
                SocialAsset.platform == payload.platform,
                SocialAsset.platform_post_id == spec.platform_post_id,
            )
        )
        asset = existing.scalar_one_or_none()

        if asset is None:
            asset = SocialAsset(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                connection_id=connection.id,
                platform=payload.platform,
                platform_post_id=spec.platform_post_id,
                asset_type=spec.asset_type,
                caption=spec.caption,
                thumbnail_url=spec.thumbnail_url,
                permalink=spec.permalink,
                hashtags=list(spec.hashtags),
                posted_at=spec.posted_at,
                raw_json=spec.raw_json,
            )
            session.add(asset)
            inserted += 1
        else:
            asset.asset_type = spec.asset_type
            asset.caption = spec.caption
            asset.thumbnail_url = spec.thumbnail_url
            asset.permalink = spec.permalink
            asset.hashtags = list(spec.hashtags)
            asset.posted_at = spec.posted_at
            asset.raw_json = {**(asset.raw_json or {}), **spec.raw_json}
            updated += 1

        await session.flush()

        has_signal = any(
            [
                spec.impressions, spec.reach, spec.likes,
                spec.comments_count, spec.saves, spec.shares,
                spec.views, spec.watch_time_seconds, spec.ctr,
            ]
        )
        if has_signal:
            denom = max(spec.impressions or spec.reach or spec.views or 1, 1)
            engagement = (
                spec.likes + spec.comments_count + spec.saves + spec.shares
            )
            engagement_rate = round(engagement / denom, 4)
            session.add(
                PerformanceSignal(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    impressions=spec.impressions,
                    reach=spec.reach,
                    likes=spec.likes,
                    comments_count=spec.comments_count,
                    saves=spec.saves,
                    shares=spec.shares,
                    engagement_rate=engagement_rate,
                    views=spec.views,
                    watch_time_seconds=spec.watch_time_seconds,
                    ctr=spec.ctr,
                    raw_json={},
                    captured_at=datetime.now(UTC),
                )
            )
            signals_inserted += 1

    now = datetime.now(UTC)
    connection.last_synced_at = now

    if signals_inserted > 0:
        from aicmo.modules.advisor.connectors import upsert_metric

        totals = {
            "reach": 0,
            "impressions": 0,
            "engagement": 0,
            "views": 0,
        }
        for spec in payload.assets:
            totals["reach"] += spec.reach or 0
            totals["impressions"] += spec.impressions or 0
            totals["views"] += spec.views or 0
            totals["engagement"] += (
                spec.likes + spec.comments_count + spec.saves + spec.shares
            )
        denom = max(totals["reach"] or totals["impressions"] or totals["views"] or 1, 1)
        engagement_rate = round(totals["engagement"] / denom, 4)
        provider_slug = f"{payload.platform}_organic"
        account_metrics = {
            "reach_28d": float(totals["reach"]),
            "impressions_28d": float(totals["impressions"]),
            "engagement_rate": engagement_rate,
            "accounts_engaged": float(totals["engagement"]),
        }
        if totals["views"]:
            account_metrics["views_28d"] = float(totals["views"])
        for key, value in account_metrics.items():
            await upsert_metric(
                session,
                brand_id=tenant.brand_id,
                provider_slug=provider_slug,
                metric_key=key,
                metric_value=value,
                period_end=now,
                raw_json={"source": "manual_import"},
            )

    await session.commit()

    return ImportResult(
        connection_id=connection.id,
        inserted_assets=inserted,
        updated_assets=updated,
        inserted_signals=signals_inserted,
    )


async def list_assets(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    platform: str | None = None,
    limit: int = 25,
) -> list[SocialAssetResponse]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(SocialAsset)
        .where(SocialAsset.brand_id == brand_id)
        .order_by(
            desc(func.coalesce(SocialAsset.posted_at, SocialAsset.created_at))
        )
        .limit(limit)
    )
    if platform:
        stmt = stmt.where(SocialAsset.platform == platform)
    asset_rows = (await session.execute(stmt)).scalars().all()

    latest_by_asset: dict[uuid.UUID, PerformanceSignal] = {}
    if asset_rows:
        sig_stmt = (
            select(PerformanceSignal)
            .where(
                PerformanceSignal.asset_id.in_([a.id for a in asset_rows])
            )
            .order_by(desc(PerformanceSignal.captured_at))
        )
        for sig in (await session.execute(sig_stmt)).scalars():
            if sig.asset_id not in latest_by_asset:
                latest_by_asset[sig.asset_id] = sig

    out: list[SocialAssetResponse] = []
    for a in asset_rows:
        latest = latest_by_asset.get(a.id)
        out.append(
            SocialAssetResponse(
                id=a.id,
                platform=a.platform,  # type: ignore[arg-type]
                platform_post_id=a.platform_post_id,
                asset_type=a.asset_type,
                caption=a.caption,
                thumbnail_url=a.thumbnail_url,
                permalink=a.permalink,
                hashtags=list(a.hashtags or []),
                posted_at=a.posted_at,
                latest_signal=PerformanceSignalResponse.model_validate(latest)
                if latest
                else None,
            )
        )
    return out


async def list_winning_patterns(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    platform: str | None = None,
    limit: int = 20,
) -> list[WinningPatternResponse]:
    limit = max(1, min(limit, 100))
    stmt = (
        select(WinningPattern)
        .where(WinningPattern.brand_id == brand_id)
        .order_by(
            desc(WinningPattern.performance_score),
            desc(WinningPattern.created_at),
        )
        .limit(limit)
    )
    if platform:
        stmt = stmt.where(WinningPattern.platform == platform)
    rows = (await session.execute(stmt)).scalars().all()
    return [WinningPatternResponse.model_validate(r) for r in rows]


async def list_audience_patterns(
    session: AsyncSession,
    *,
    brand_id: uuid.UUID,
    platform: str | None = None,
) -> list[AudiencePatternResponse]:
    stmt = (
        select(AudiencePattern)
        .where(AudiencePattern.brand_id == brand_id)
        .order_by(desc(AudiencePattern.confidence_score))
    )
    if platform:
        stmt = stmt.where(AudiencePattern.platform == platform)
    rows = (await session.execute(stmt)).scalars().all()
    return [AudiencePatternResponse.model_validate(r) for r in rows]


async def top_winning_patterns_for_context(
    session: AsyncSession, *, brand_id: uuid.UUID, limit: int = 5
) -> list[WinningPattern]:
    """Used by `modules/context/builder.py`."""
    stmt = (
        select(WinningPattern)
        .where(WinningPattern.brand_id == brand_id)
        .order_by(
            desc(WinningPattern.performance_score),
            desc(WinningPattern.created_at),
        )
        .limit(max(1, min(limit, 20)))
    )
    return list((await session.execute(stmt)).scalars().all())


async def resolve_tenant_for_oauth(
    session: AsyncSession,
    *,
    clerk_user_id: str,
    brand_id: uuid.UUID,
) -> TenantContext:
    """Build tenant context from signed OAuth state (unauthenticated callback)."""
    user = (
        await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    brand = await session.get(Brand, brand_id)
    if brand is None or brand.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Brand not found."
        )

    member = (
        await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == brand.organization_id,
                OrganizationMember.status == "active",
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization.",
        )

    permissions = await compute_permissions_for_member(
        session, member_id=member.id
    )
    role_slugs = await compute_role_slugs_for_member(
        session, member_id=member.id
    )
    return TenantContext(
        user_id=clerk_user_id,
        user_uuid=user.id,
        organization_id=brand.organization_id,
        brand_id=brand_id,
        member_id=member.id,
        role_slugs=role_slugs,
        permissions=permissions,
    )


async def require_connection(
    session: AsyncSession, *, brand_id: uuid.UUID, platform: str
) -> SocialConnection:
    stmt = select(SocialConnection).where(
        SocialConnection.brand_id == brand_id,
        SocialConnection.platform == platform,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {platform} connection yet — connect it or import data manually first.",
        )
    return row


async def complete_oauth(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    platform: str,
    code: str,
    redirect_uri: str,
) -> SocialConnectionResponse:
    from aicmo.providers.social.registry import get_social_provider

    provider = get_social_provider(platform)
    result = await provider.complete_oauth(code=code, redirect_uri=redirect_uri)

    stmt = select(SocialConnection).where(
        SocialConnection.brand_id == tenant.brand_id,
        SocialConnection.platform == platform,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = SocialConnection(
            id=uuid.uuid4(),
            user_id=tenant.user_id,
            organization_id=tenant.organization_id,
            brand_id=tenant.brand_id,
            platform=platform,
            source="oauth",
        )
        session.add(row)

    row.access_token = seal(result.access_token)
    row.refresh_token = seal(result.refresh_token)
    row.expires_at = result.expires_at
    row.metadata_json = {**(row.metadata_json or {}), **result.metadata}
    row.source = "oauth"
    await session.commit()
    await session.refresh(row)
    return SocialConnectionResponse.model_validate(row)


async def sync_platform(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    platform: str,
    limit: int = 25,
) -> ImportResult:
    """Pull live data from connected platform and persist assets + metrics."""
    from aicmo.modules.advisor.connectors import upsert_metric
    from aicmo.providers.social.registry import get_social_provider

    connection = await require_connection(
        session, brand_id=tenant.brand_id, platform=platform
    )
    if not connection.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No access token — reconnect the platform via OAuth.",
        )

    provider = get_social_provider(platform)
    sync_result = await provider.sync(
        access_token=unseal(connection.access_token),
        metadata=connection.metadata_json or {},
        limit=limit,
    )

    inserted = 0
    updated = 0
    signals_inserted = 0

    for spec in sync_result.assets:
        existing = await session.execute(
            select(SocialAsset).where(
                SocialAsset.brand_id == tenant.brand_id,
                SocialAsset.platform == platform,
                SocialAsset.platform_post_id == spec.platform_post_id,
            )
        )
        asset = existing.scalar_one_or_none()

        if asset is None:
            asset = SocialAsset(
                id=uuid.uuid4(),
                user_id=tenant.user_id,
                organization_id=tenant.organization_id,
                brand_id=tenant.brand_id,
                connection_id=connection.id,
                platform=platform,
                platform_post_id=spec.platform_post_id,
                asset_type=spec.asset_type,
                caption=spec.caption,
                thumbnail_url=spec.thumbnail_url,
                permalink=spec.permalink,
                hashtags=list(spec.hashtags),
                posted_at=spec.posted_at,
                raw_json=spec.raw_asset_json,
            )
            session.add(asset)
            inserted += 1
        else:
            asset.asset_type = spec.asset_type
            asset.caption = spec.caption
            asset.thumbnail_url = spec.thumbnail_url
            asset.permalink = spec.permalink
            asset.hashtags = list(spec.hashtags)
            asset.posted_at = spec.posted_at
            asset.raw_json = {**(asset.raw_json or {}), **spec.raw_asset_json}
            updated += 1

        await session.flush()

        denom = max(spec.impressions or spec.reach or spec.views or 1, 1)
        engagement = spec.likes + spec.comments_count + spec.saves + spec.shares
        engagement_rate = round(engagement / denom, 4)
        session.add(
            PerformanceSignal(
                id=uuid.uuid4(),
                asset_id=asset.id,
                impressions=spec.impressions,
                reach=spec.reach,
                likes=spec.likes,
                comments_count=spec.comments_count,
                saves=spec.saves,
                shares=spec.shares,
                engagement_rate=engagement_rate,
                views=spec.views,
                watch_time_seconds=spec.watch_time_seconds,
                ctr=spec.ctr,
                raw_json=spec.raw_signal_json,
                captured_at=sync_result.synced_at,
            )
        )
        signals_inserted += 1

    now = sync_result.synced_at
    for key, value in sync_result.account_metrics.items():
        await upsert_metric(
            session,
            brand_id=tenant.brand_id,
            provider_slug=f"{platform}_organic",
            metric_key=key,
            metric_value=float(value),
            period_end=now,
            raw_json={"source": "oauth_sync"},
        )

    connection.last_synced_at = now
    await session.commit()

    return ImportResult(
        connection_id=connection.id,
        inserted_assets=inserted,
        updated_assets=updated,
        inserted_signals=signals_inserted,
    )


async def disconnect_platform(
    session: AsyncSession,
    *,
    tenant: TenantContext,
    platform: str,
) -> None:
    """Remove OAuth tokens for a platform connection (tenant-scoped)."""
    row = (
        await session.execute(
            select(SocialConnection).where(
                SocialConnection.brand_id == tenant.brand_id,
                SocialConnection.platform == platform,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No {platform} connection found.",
        )
    row.access_token = None
    row.refresh_token = None
    row.expires_at = None
    row.metadata_json = {}
    row.source = "manual_import"
    await session.commit()
    log.info(
        "social.disconnected",
        platform=platform,
        brand_id=str(tenant.brand_id),
        organization_id=str(tenant.organization_id),
    )
